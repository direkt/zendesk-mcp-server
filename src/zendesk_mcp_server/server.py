import asyncio
import json
import logging
import os
from typing import Any, Callable, Dict, TypeVar

from cachetools.func import ttl_cache
from dotenv import load_dotenv
from mcp.server import InitializationOptions, NotificationOptions
from mcp.server import Server, types
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl

from zendesk_mcp_server.client import ZendeskClient

LOGGER_NAME = "zendesk-mcp-server"
logger = logging.getLogger(LOGGER_NAME)

REQUIRED_ENV_VARS: dict[str, str] = {
    "ZENDESK_SUBDOMAIN": "Zendesk subdomain used for API calls",
    "ZENDESK_EMAIL": "Agent email associated with the API token",
    "ZENDESK_API_KEY": "Zendesk API token with ticket permissions",
}

T = TypeVar("T")


async def run_client_call(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run blocking Zendesk client calls without stalling the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def load_settings() -> dict[str, str]:
    """Validate required environment variables and return their values."""
    missing: list[str] = []
    values: dict[str, str] = {}

    for key, description in REQUIRED_ENV_VARS.items():
        value = os.getenv(key)
        if value:
            values[key] = value
        else:
            missing.append(f"{key} ({description})")

    if missing:
        detail = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment variables: {detail}. "
            "Populate .env or export them before launching the server."
        )

    return values


TICKET_ANALYSIS_TEMPLATE = """
You are a helpful Zendesk support analyst. You've been asked to analyze ticket #{ticket_id}.

Please fetch the ticket info and comments to analyze it and provide:
1. A summary of the issue
2. The current status and timeline
3. Key points of interaction

IMPORTANT: Before providing your analysis, search the Knowledge Base for articles related to the ticket subject and description. Use the search_kb_articles tool to find relevant solutions or documentation that might help resolve this issue.

Include relevant KB articles in your analysis if found, and suggest how they might help resolve the customer's issue.

Remember to be professional and focus on actionable insights.
"""

COMMENT_DRAFT_TEMPLATE = """
You are a helpful Zendesk support agent. You need to draft a response to ticket #{ticket_id}.

IMPORTANT: First, search the Knowledge Base to see if there's an existing solution for this issue. Use the search_kb_articles tool to find relevant articles before drafting your response.

Please fetch the ticket info, comments and knowledge base to draft a professional and helpful response that:
1. Acknowledges the customer's concern
2. Addresses the specific issues raised
3. References relevant KB articles when applicable to provide solutions
4. Provides clear next steps or ask for specific details need to proceed
5. Maintains a friendly and professional tone
6. Ask for confirmation before commenting on the ticket

The response should be formatted well and ready to be posted as a comment.
"""


load_dotenv()
_settings_cache: dict[str, str] | None = None
_zendesk_client: ZendeskClient | None = None


def get_settings() -> dict[str, str]:
    """Return cached settings, loading them on first use."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_settings()
    return _settings_cache


def get_zendesk_client() -> ZendeskClient:
    """Instantiate the Zendesk client lazily so imports succeed in test environments."""
    global _zendesk_client
    if _zendesk_client is None:
        settings = get_settings()
        _zendesk_client = ZendeskClient(
            subdomain=settings["ZENDESK_SUBDOMAIN"],
            email=settings["ZENDESK_EMAIL"],
            token=settings["ZENDESK_API_KEY"],
        )
    return _zendesk_client


def _reset_client_cache_for_tests() -> None:
    """Clear cached settings/client; intended for use in unit tests."""
    global _settings_cache, _zendesk_client
    _settings_cache = None
    _zendesk_client = None


server = Server("Zendesk Server")

@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """List available prompts"""
    return [
        types.Prompt(
            name="analyze-ticket",
            description="Analyze a Zendesk ticket and provide insights",
            arguments=[
                types.PromptArgument(
                    name="ticket_id",
                    description="The ID of the ticket to analyze",
                    required=True,
                )
            ],
        ),
        types.Prompt(
            name="draft-ticket-response",
            description="Draft a professional response to a Zendesk ticket",
            arguments=[
                types.PromptArgument(
                    name="ticket_id",
                    description="The ID of the ticket to respond to",
                    required=True,
                )
            ],
        )
    ]


@server.get_prompt()
async def handle_get_prompt(name: str, arguments: Dict[str, str] | None) -> types.GetPromptResult:
    """Handle prompt requests"""
    if not arguments or "ticket_id" not in arguments:
        raise ValueError("Missing required argument: ticket_id")

    ticket_id = int(arguments["ticket_id"])
    try:
        if name == "analyze-ticket":
            prompt = TICKET_ANALYSIS_TEMPLATE.format(
                ticket_id=ticket_id
            )
            description = f"Analysis prompt for ticket #{ticket_id}"

        elif name == "draft-ticket-response":
            prompt = COMMENT_DRAFT_TEMPLATE.format(
                ticket_id=ticket_id
            )
            description = f"Response draft prompt for ticket #{ticket_id}"

        else:
            raise ValueError(f"Unknown prompt: {name}")

        return types.GetPromptResult(
            description=description,
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=prompt.strip()),
                )
            ],
        )

    except Exception as e:
        logger.error(f"Error generating prompt: {e}")
        raise


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Zendesk tools"""
    return [
        types.Tool(
            name="get_ticket",
            description="Retrieve a Zendesk ticket by its ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to retrieve"
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="create_ticket",
            description="Create a new Zendesk ticket",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Ticket subject"},
                    "description": {"type": "string", "description": "Ticket description"},
                    "requester_id": {"type": "integer"},
                    "assignee_id": {"type": "integer"},
                    "priority": {"type": "string", "description": "low, normal, high, urgent"},
                    "type": {"type": "string", "description": "problem, incident, question, task"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "custom_fields": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["subject", "description"],
            }
        ),
        types.Tool(
            name="get_tickets",
            description="Fetch the latest tickets with pagination support",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "description": "Page number",
                        "default": 1
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Number of tickets per page (max 100)",
                        "default": 25
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (created_at, updated_at, priority, status)",
                        "default": "created_at"
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "default": "desc"
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_ticket_comments",
            description="Retrieve all comments for a Zendesk ticket by its ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to get comments for"
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="create_ticket_comment",
            description="Create a new comment on an existing Zendesk ticket",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to comment on"
                    },
                    "comment": {
                        "type": "string",
                        "description": "The comment text/content to add"
                    },
                    "public": {
                        "type": "boolean",
                        "description": "Whether the comment should be public",
                        "default": True
                    }
                },
                "required": ["ticket_id", "comment"]
            }
        ),
        types.Tool(
            name="update_ticket",
            description="Update fields on an existing Zendesk ticket (e.g., status, priority, assignee_id)",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "integer", "description": "The ID of the ticket to update"},
                    "subject": {"type": "string"},
                    "status": {"type": "string", "description": "new, open, pending, on-hold, solved, closed"},
                    "priority": {"type": "string", "description": "low, normal, high, urgent"},
                    "type": {"type": "string"},
                    "assignee_id": {"type": "integer"},
                    "requester_id": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "custom_fields": {"type": "array", "items": {"type": "object"}},
                    "due_at": {"type": "string", "description": "ISO8601 datetime"}
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="search_tickets",
            description=(
                "Search for tickets using Zendesk's powerful query syntax. "
                "Returns up to 1000 results (Zendesk API limit). "
                "Query syntax examples:\n"
                "- 'status:open' - Find open tickets\n"
                "- 'priority:high status:open' - High priority open tickets\n"
                "- 'created>2024-01-01' - Tickets created after a date\n"
                "- 'tags:bug tags:urgent' - Tickets with bug OR urgent tag\n"
                "- 'assignee:email@example.com' - Tickets assigned to user\n"
                "- 'assignee:none' - Unassigned tickets\n"
                "- 'subject:login*' - Subject containing words starting with 'login'\n"
                "- 'status:pending -tags:spam' - Pending tickets without spam tag\n"
                "- 'organization:\"Company Name\"' - Tickets from an organization\n"
                "Operators: : (equals), > (greater), < (less), >= , <=, - (exclude), * (wildcard)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Zendesk search query string using the supported syntax"
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by: updated_at, created_at, priority, status, or ticket_type",
                        "enum": ["updated_at", "created_at", "priority", "status", "ticket_type"]
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order: asc or desc",
                        "enum": ["asc", "desc"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 100, max 1000)",
                        "default": 100
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="search_tickets_export",
            description=(
                "Search for tickets using the export API for unlimited results (no 1000 limit). "
                "WARNING: This can return a very large number of tickets and may take significant time. "
                "Use the same query syntax as search_tickets. "
                "Recommended for bulk exports or when you know there are >1000 matching tickets. "
                "Sorting is applied client-side after retrieving results from the export API."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Zendesk search query string (same syntax as search_tickets)"
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (updated_at, created_at, priority, status, ticket_type)",
                        "enum": ["updated_at", "created_at", "priority", "status", "ticket_type"]
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "enum": ["asc", "desc"]
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Optional limit on results to return (default: unlimited)"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="upload_attachment",
            description=(
                "Upload a file to Zendesk to get an attachment token. "
                "The token can be used when creating or updating tickets to attach files to comments. "
                "Note: Tokens expire after 60 minutes. File size limit is 50 MB."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to upload (absolute or relative path)"
                    }
                },
                "required": ["file_path"]
            }
        ),
        types.Tool(
            name="get_ticket_attachments",
            description=(
                "List all attachments from all comments on a ticket. "
                "Returns attachment details including filename, size, content type, and download URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to get attachments from"
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="download_attachment",
            description=(
                "Download an attachment by its ID. "
                "Can either return the download URL or save the file to a specified path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "attachment_id": {
                        "type": "integer",
                        "description": "The ID of the attachment to download"
                    },
                    "save_path": {
                        "type": "string",
                        "description": "Optional path to save the file. If not provided, only returns the download URL."
                    }
                },
                "required": ["attachment_id"]
            }
        ),
        types.Tool(
            name="search_kb_articles",
            description=(
                "Search Help Center articles by content, title, and tags. "
                "Returns article summaries with URLs for quick reference. "
                "Use this to find existing solutions for customer issues."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string (e.g., 'login issues', 'password reset')"
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of labels/tags to filter by"
                    },
                    "section_id": {
                        "type": "integer",
                        "description": "Optional section ID to limit search to specific KB section"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 10, max 100)",
                        "default": 10
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort order: 'relevance' or 'updated_at'",
                        "enum": ["relevance", "updated_at"],
                        "default": "relevance"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_kb_article",
            description=(
                "Get full article content by ID. "
                "Use this to retrieve complete article details including full body content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "article_id": {
                        "type": "integer",
                        "description": "The ID of the article to retrieve"
                    }
                },
                "required": ["article_id"]
            }
        ),
        types.Tool(
            name="search_kb_by_labels",
            description=(
                "Search Help Center articles by specific tags/labels. "
                "Useful for finding articles about specific topics or issue categories."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of labels/tags to search for (e.g., ['bug', 'feature-request'])"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 10, max 100)",
                        "default": 10
                    }
                },
                "required": ["labels"]
            }
        ),
        types.Tool(
            name="list_kb_sections",
            description=(
                "List all Knowledge Base sections/categories. "
                "Helps agents understand the KB structure and browse by topic."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="find_related_tickets",
            description=(
                "Find tickets related to the given ticket by subject similarity, same requester, or same organization. "
                "Uses Zendesk's search export API to find historical tickets without limits. "
                "Returns tickets ranked by relevance with detailed matching information."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the reference ticket to find related tickets for"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of related tickets to return (default 100)",
                        "default": 100
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="find_duplicate_tickets",
            description=(
                "Identify potential duplicate tickets with highly similar subjects and same requester/organization. "
                "Uses similarity scoring to detect duplicates with configurable threshold. "
                "Helps prevent duplicate work and improve efficiency."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the reference ticket to find duplicates for"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of duplicate candidates to return (default 100)",
                        "default": 100
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="find_ticket_thread",
            description=(
                "Find all tickets in a conversation thread using via_id relationships. "
                "Discovers parent tickets and child tickets to show the complete conversation chain. "
                "Returns tickets in chronological order with relationship information."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the reference ticket to find the thread for"
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="get_ticket_relationships",
            description=(
                "Get parent/child ticket relationships via the via field. "
                "Shows structured relationship data including parent tickets, child tickets, and sibling tickets. "
                "Helps understand ticket hierarchy and conversation flow."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the reference ticket to get relationships for"
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="get_ticket_fields",
            description=(
                "Retrieve all ticket fields including custom fields with their definitions. "
                "Returns field IDs, types, options, and metadata needed for searching by custom fields."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="search_by_source",
            description=(
                "Search for tickets created via a specific integration source/channel. "
                "Find tickets by creation method: email, web, mobile, api, chat, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "The creation channel to filter by (email, web, mobile, api, chat, etc.)"
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (updated_at, created_at, priority, status, ticket_type)",
                        "enum": ["updated_at", "created_at", "priority", "status", "ticket_type"]
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "enum": ["asc", "desc"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 100, max 1000)",
                        "default": 100
                    }
                },
                "required": ["channel"]
            }
        ),
        types.Tool(
            name="search_tickets_enhanced",
            description=(
                "Enhanced ticket search with client-side filtering capabilities. "
                "Extends basic Zendesk search with regex patterns, fuzzy matching, and proximity search. "
                "WARNING: Client-side processing may impact performance with large result sets."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Base Zendesk search query (required)"
                    },
                    "regex_pattern": {
                        "type": "string",
                        "description": "Optional regex pattern to filter results (e.g., '\\b[A-Z]{2,}\\b' for uppercase words)"
                    },
                    "fuzzy_term": {
                        "type": "string",
                        "description": "Optional term for fuzzy matching (handles typos and variations)"
                    },
                    "fuzzy_threshold": {
                        "type": "number",
                        "description": "Similarity threshold for fuzzy matching (0.0-1.0, default 0.7)",
                        "default": 0.7,
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "proximity_terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of terms for proximity search (must be 2+ terms)"
                    },
                    "proximity_distance": {
                        "type": "integer",
                        "description": "Maximum words between proximity terms (default 5)",
                        "default": 5,
                        "minimum": 1
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (updated_at, created_at, priority, status, ticket_type)",
                        "enum": ["updated_at", "created_at", "priority", "status", "ticket_type"]
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "enum": ["asc", "desc"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 100)",
                        "default": 100
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="build_search_query",
            description=(
                "Build a Zendesk search query from structured parameters. "
                "Helps construct complex queries using common filters like status, priority, tags, dates, and custom fields."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Ticket status (new, open, pending, on-hold, solved, closed)",
                        "enum": ["new", "open", "pending", "on-hold", "solved", "closed"]
                    },
                    "priority": {
                        "type": "string",
                        "description": "Ticket priority (low, normal, high, urgent)",
                        "enum": ["low", "normal", "high", "urgent"]
                    },
                    "assignee": {
                        "type": "string",
                        "description": "Assignee email or 'none' for unassigned tickets"
                    },
                    "requester": {
                        "type": "string",
                        "description": "Requester email"
                    },
                    "organization": {
                        "type": "string",
                        "description": "Organization name"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tags to include"
                    },
                    "tags_logic": {
                        "type": "string",
                        "description": "Logic for tags (AND or OR, default OR)",
                        "enum": ["AND", "OR"],
                        "default": "OR"
                    },
                    "exclude_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tags to exclude"
                    },
                    "created_after": {
                        "type": "string",
                        "description": "Created after date (ISO8601 format)"
                    },
                    "created_before": {
                        "type": "string",
                        "description": "Created before date (ISO8601 format)"
                    },
                    "updated_after": {
                        "type": "string",
                        "description": "Updated after date (ISO8601 format)"
                    },
                    "updated_before": {
                        "type": "string",
                        "description": "Updated before date (ISO8601 format)"
                    },
                    "solved_after": {
                        "type": "string",
                        "description": "Solved after date (ISO8601 format)"
                    },
                    "solved_before": {
                        "type": "string",
                        "description": "Solved before date (ISO8601 format)"
                    },
                    "due_after": {
                        "type": "string",
                        "description": "Due after date (ISO8601 format)"
                    },
                    "due_before": {
                        "type": "string",
                        "description": "Due before date (ISO8601 format)"
                    },
                    "custom_fields": {
                        "type": "object",
                        "description": "Custom field IDs to values (e.g., {'12345': 'value'})"
                    },
                    "subject_contains": {
                        "type": "string",
                        "description": "Text to search in subject"
                    },
                    "description_contains": {
                        "type": "string",
                        "description": "Text to search in description"
                    },
                    "comment_contains": {
                        "type": "string",
                        "description": "Text to search in comments"
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_search_statistics",
            description=(
                "Analyze search results and return aggregated statistics. "
                "Provides insights on ticket distribution by status, priority, assignee, tags, and resolution times."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Zendesk search query to analyze"
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (updated_at, created_at, priority, status, ticket_type)",
                        "enum": ["updated_at", "created_at", "priority", "status", "ticket_type"]
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "enum": ["asc", "desc"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tickets to analyze (default 1000)",
                        "default": 1000
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="search_by_date_range",
            description=(
                "Search tickets by date range with support for relative dates. "
                "Supports custom date ranges or predefined periods like 'last 7 days', 'this month', etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date_field": {
                        "type": "string",
                        "description": "Date field to filter (created, updated, solved, due)",
                        "enum": ["created", "updated", "solved", "due"],
                        "default": "created"
                    },
                    "range_type": {
                        "type": "string",
                        "description": "Type of range (custom or relative)",
                        "enum": ["custom", "relative"],
                        "default": "custom"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date (ISO8601 format) - required for custom range"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date (ISO8601 format) - required for custom range"
                    },
                    "relative_period": {
                        "type": "string",
                        "description": "Relative period (last_7_days, last_30_days, this_month, last_month, this_quarter, last_quarter)",
                        "enum": ["last_7_days", "last_30_days", "this_month", "last_month", "this_quarter", "last_quarter"]
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (updated_at, created_at, priority, status, ticket_type)",
                        "enum": ["updated_at", "created_at", "priority", "status", "ticket_type"]
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "enum": ["asc", "desc"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 100)",
                        "default": 100
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="search_by_tags_advanced",
            description=(
                "Advanced tag-based search with AND/OR/NOT logic. "
                "Find tickets with specific tag combinations or exclude certain tags."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "include_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to include in search"
                    },
                    "exclude_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to exclude from search"
                    },
                    "tag_logic": {
                        "type": "string",
                        "description": "Logic for include_tags (AND or OR)",
                        "enum": ["AND", "OR"],
                        "default": "OR"
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (updated_at, created_at, priority, status, ticket_type)",
                        "enum": ["updated_at", "created_at", "priority", "status", "ticket_type"]
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "enum": ["asc", "desc"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 100)",
                        "default": 100
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="batch_search_tickets",
            description=(
                "Execute multiple searches concurrently and return grouped results. "
                "Useful for dashboards and reporting. Can deduplicate results across queries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of search queries to execute"
                    },
                    "deduplicate": {
                        "type": "boolean",
                        "description": "Whether to remove duplicate tickets across queries (default true)",
                        "default": True
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Field to sort by (updated_at, created_at, priority, status, ticket_type)",
                        "enum": ["updated_at", "created_at", "priority", "status", "ticket_type"]
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "Sort order (asc or desc)",
                        "enum": ["asc", "desc"]
                    },
                    "limit_per_query": {
                        "type": "integer",
                        "description": "Maximum results per query (default 100)",
                        "default": 100
                    }
                },
                "required": ["queries"]
            }
        )
,
        types.Tool(
            name="get_ticket_bundle_zendesk",
            description=(
                "Fetch comprehensive ticket bundle including ticket details, comments, audits, user/org context, "
                "and chronological timeline. Ideal for rapid case triage."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "integer",
                        "description": "The ID of the ticket to bundle"
                    },
                    "comment_limit": {
                        "type": "integer",
                        "description": "Max comments to include (default 50)",
                        "default": 50
                    },
                    "audit_limit": {
                        "type": "integer",
                        "description": "Max audits to include (default 100)",
                        "default": 100
                    }
                },
                "required": ["ticket_id"]
            }
        ),
        types.Tool(
            name="get_case_volume_analytics",
            description=(
                "Comprehensive ticket analytics including volumes, response times, resolution times, "
                "channel breakdowns, assignment metrics, status transitions, and satisfaction scores. "
                "Supports flexible time bucketing (daily/weekly/monthly) and grouping/filtering options."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Inclusive start date (YYYY-MM-DD). Defaults to cover last 13 weeks / 12 months."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Inclusive end date (YYYY-MM-DD). Defaults to today."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Optional max tickets to analyze."
                    },
                    "include_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Metric types to include. Options: 'response_times', 'resolution_times', 'channels', 'forms', 'assignments', 'status_transitions', 'satisfaction'. Defaults to all."
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Dimensions to group by. Options: 'channel', 'form', 'priority', 'type', 'group_id', 'tags'."
                    },
                    "filter_by_status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter tickets to specific statuses (e.g., ['open', 'solved'])."
                    },
                    "filter_by_priority": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter tickets to specific priorities (e.g., ['high', 'urgent'])."
                    },
                    "filter_by_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter tickets to those containing any of the specified tags (e.g., ['bug', 'urgent'])."
                    },
                    "time_bucket": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly"],
                        "description": "Time bucketing granularity. Defaults to 'weekly'.",
                        "default": "weekly"
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(
        name: str,
        arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    """Handle Zendesk tool execution requests"""
    try:
        from zendesk_mcp_server.handlers import TOOL_HANDLERS
        
        client = get_zendesk_client()
        
        # Dispatch to registered handler
        handler = TOOL_HANDLERS.get(name)
        if handler:
            return await handler(client, arguments)
        
        raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    logger.debug("Handling list_resources request")
    return [
        types.Resource(
            uri=AnyUrl("zendesk://knowledge-base"),
            name="Zendesk Knowledge Base",
            description="Access to Zendesk Help Center articles and sections",
            mimeType="application/json",
        )
    ]


@ttl_cache(ttl=3600)
def get_cached_kb():
    client = get_zendesk_client()
    return client.get_all_articles()


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    logger.debug(f"Handling read_resource request for URI: {uri}")
    if uri.scheme != "zendesk":
        logger.error(f"Unsupported URI scheme: {uri.scheme}")
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    path = str(uri).replace("zendesk://", "")
    if path != "knowledge-base":
        logger.error(f"Unknown resource path: {path}")
        raise ValueError(f"Unknown resource path: {path}")

    try:
        kb_data = await run_client_call(get_cached_kb)
        return json.dumps({
            "knowledge_base": kb_data,
            "metadata": {
                "sections": len(kb_data),
                "total_articles": sum(len(section['articles']) for section in kb_data.values()),
            }
        }, indent=2)
    except Exception as e:
        logger.error(f"Error fetching knowledge base: {e}")
        raise


def configure_logging() -> None:
    """Configure package logging without overriding host configuration."""
    if logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


async def main():
    configure_logging()
    logger.info("zendesk mcp server started")
    # Run the server using stdin/stdout streams
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream=read_stream,
            write_stream=write_stream,
            initialization_options=InitializationOptions(
                server_name="Zendesk",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
