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

from zendesk_mcp_server.zendesk_client import ZendeskClient

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
        )
    ]


@server.call_tool()
async def handle_call_tool(
        name: str,
        arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    """Handle Zendesk tool execution requests"""
    try:
        client = get_zendesk_client()
        if name == "get_ticket":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket = await run_client_call(
                client.get_ticket,
                arguments["ticket_id"]
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(ticket)
            )]

        elif name == "create_ticket":
            if not arguments:
                raise ValueError("Missing arguments")
            created = await run_client_call(
                client.create_ticket,
                subject=arguments.get("subject"),
                description=arguments.get("description"),
                requester_id=arguments.get("requester_id"),
                assignee_id=arguments.get("assignee_id"),
                priority=arguments.get("priority"),
                type=arguments.get("type"),
                tags=arguments.get("tags"),
                custom_fields=arguments.get("custom_fields"),
            )
            return [types.TextContent(
                type="text",
                text=json.dumps({"message": "Ticket created successfully", "ticket": created}, indent=2)
            )]

        elif name == "get_tickets":
            page = arguments.get("page", 1) if arguments else 1
            per_page = arguments.get("per_page", 25) if arguments else 25
            sort_by = arguments.get("sort_by", "created_at") if arguments else "created_at"
            sort_order = arguments.get("sort_order", "desc") if arguments else "desc"

            tickets = await run_client_call(
                client.get_tickets,
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                sort_order=sort_order
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(tickets, indent=2)
            )]

        elif name == "get_ticket_comments":
            if not arguments:
                raise ValueError("Missing arguments")
            comments = await run_client_call(
                client.get_ticket_comments,
                arguments["ticket_id"]
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(comments)
            )]

        elif name == "create_ticket_comment":
            if not arguments:
                raise ValueError("Missing arguments")
            public = arguments.get("public", True)
            result = await run_client_call(
                client.post_comment,
                ticket_id=arguments["ticket_id"],
                comment=arguments["comment"],
                public=public
            )
            return [types.TextContent(
                type="text",
                text=f"Comment created successfully: {result}"
            )]

        elif name == "update_ticket":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket_id = arguments.get("ticket_id")
            if ticket_id is None:
                raise ValueError("ticket_id is required")
            update_fields = {k: v for k, v in arguments.items() if k != "ticket_id"}
            updated = await run_client_call(
                client.update_ticket,
                int(ticket_id),
                **update_fields
            )
            return [types.TextContent(
                type="text",
                text=json.dumps({"message": "Ticket updated successfully", "ticket": updated}, indent=2)
            )]

        elif name == "search_tickets":
            if not arguments:
                raise ValueError("Missing arguments")
            query = arguments.get("query")
            if not query:
                raise ValueError("query is required")

            results = await run_client_call(
                client.search_tickets,
                query=query,
                sort_by=arguments.get("sort_by"),
                sort_order=arguments.get("sort_order"),
                limit=arguments.get("limit", 100)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )]

        elif name == "search_tickets_export":
            if not arguments:
                raise ValueError("Missing arguments")
            query = arguments.get("query")
            if not query:
                raise ValueError("query is required")

            results = await run_client_call(
                client.search_tickets_export,
                query=query,
                sort_by=arguments.get("sort_by"),
                sort_order=arguments.get("sort_order"),
                max_results=arguments.get("max_results")
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )]

        elif name == "upload_attachment":
            if not arguments:
                raise ValueError("Missing arguments")
            file_path = arguments.get("file_path")
            if not file_path:
                raise ValueError("file_path is required")

            result = await run_client_call(
                client.upload_attachment,
                file_path
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_ticket_attachments":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket_id = arguments.get("ticket_id")
            if ticket_id is None:
                raise ValueError("ticket_id is required")

            result = await run_client_call(
                client.get_ticket_attachments,
                int(ticket_id)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "download_attachment":
            if not arguments:
                raise ValueError("Missing arguments")
            attachment_id = arguments.get("attachment_id")
            if attachment_id is None:
                raise ValueError("attachment_id is required")

            result = await run_client_call(
                client.download_attachment,
                int(attachment_id),
                save_path=arguments.get("save_path")
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "search_kb_articles":
            if not arguments:
                raise ValueError("Missing arguments")
            query = arguments.get("query")
            if not query:
                raise ValueError("query is required")

            result = await run_client_call(
                client.search_articles,
                query=query,
                label_names=arguments.get("labels"),
                section_id=arguments.get("section_id"),
                per_page=arguments.get("limit", 10),
                sort_by=arguments.get("sort_by", "relevance")
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_kb_article":
            if not arguments:
                raise ValueError("Missing arguments")
            article_id = arguments.get("article_id")
            if article_id is None:
                raise ValueError("article_id is required")

            result = await run_client_call(
                client.get_article_by_id,
                int(article_id)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "search_kb_by_labels":
            if not arguments:
                raise ValueError("Missing arguments")
            labels = arguments.get("labels")
            if not labels:
                raise ValueError("labels is required")

            result = await run_client_call(
                client.search_articles_by_labels,
                label_names=labels,
                per_page=arguments.get("limit", 10)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "list_kb_sections":
            result = await run_client_call(
                client.get_sections_list
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_related_tickets":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket_id = arguments.get("ticket_id")
            if ticket_id is None:
                raise ValueError("ticket_id is required")
            limit = arguments.get("limit", 100)

            result = await run_client_call(
                client.find_related_tickets,
                int(ticket_id),
                limit
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_duplicate_tickets":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket_id = arguments.get("ticket_id")
            if ticket_id is None:
                raise ValueError("ticket_id is required")
            limit = arguments.get("limit", 100)

            result = await run_client_call(
                client.find_duplicate_tickets,
                int(ticket_id),
                limit
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_ticket_thread":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket_id = arguments.get("ticket_id")
            if ticket_id is None:
                raise ValueError("ticket_id is required")

            result = await run_client_call(
                client.find_ticket_thread,
                int(ticket_id)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_ticket_relationships":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket_id = arguments.get("ticket_id")
            if ticket_id is None:
                raise ValueError("ticket_id is required")

            result = await run_client_call(
                client.get_ticket_relationships,
                int(ticket_id)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_ticket_fields":
            result = await run_client_call(
                client.get_ticket_fields
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "search_by_source":
            if not arguments:
                raise ValueError("Missing arguments")
            channel = arguments.get("channel")
            if not channel:
                raise ValueError("channel is required")

            result = await run_client_call(
                client.search_by_integration_source,
                channel=channel,
                sort_by=arguments.get("sort_by"),
                sort_order=arguments.get("sort_order"),
                limit=arguments.get("limit", 100)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "search_tickets_enhanced":
            if not arguments:
                raise ValueError("Missing arguments")
            query = arguments.get("query")
            if not query:
                raise ValueError("query is required")

            result = await run_client_call(
                client.search_tickets_enhanced,
                query=query,
                regex_pattern=arguments.get("regex_pattern"),
                fuzzy_term=arguments.get("fuzzy_term"),
                fuzzy_threshold=arguments.get("fuzzy_threshold", 0.7),
                proximity_terms=arguments.get("proximity_terms"),
                proximity_distance=arguments.get("proximity_distance", 5),
                sort_by=arguments.get("sort_by"),
                sort_order=arguments.get("sort_order"),
                limit=arguments.get("limit", 100)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "build_search_query":
            result = await run_client_call(
                client.build_search_query,
                status=arguments.get("status") if arguments else None,
                priority=arguments.get("priority") if arguments else None,
                assignee=arguments.get("assignee") if arguments else None,
                requester=arguments.get("requester") if arguments else None,
                organization=arguments.get("organization") if arguments else None,
                tags=arguments.get("tags") if arguments else None,
                tags_logic=arguments.get("tags_logic", "OR") if arguments else "OR",
                exclude_tags=arguments.get("exclude_tags") if arguments else None,
                created_after=arguments.get("created_after") if arguments else None,
                created_before=arguments.get("created_before") if arguments else None,
                updated_after=arguments.get("updated_after") if arguments else None,
                updated_before=arguments.get("updated_before") if arguments else None,
                solved_after=arguments.get("solved_after") if arguments else None,
                solved_before=arguments.get("solved_before") if arguments else None,
                due_after=arguments.get("due_after") if arguments else None,
                due_before=arguments.get("due_before") if arguments else None,
                custom_fields=arguments.get("custom_fields") if arguments else None,
                subject_contains=arguments.get("subject_contains") if arguments else None,
                description_contains=arguments.get("description_contains") if arguments else None,
                comment_contains=arguments.get("comment_contains") if arguments else None
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_search_statistics":
            if not arguments:
                raise ValueError("Missing arguments")
            query = arguments.get("query")
            if not query:
                raise ValueError("query is required")

            result = await run_client_call(
                client.get_search_statistics,
                query=query,
                sort_by=arguments.get("sort_by"),
                sort_order=arguments.get("sort_order"),
                limit=arguments.get("limit", 1000)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "search_by_date_range":
            result = await run_client_call(
                client.search_by_date_range,
                date_field=arguments.get("date_field", "created") if arguments else "created",
                range_type=arguments.get("range_type", "custom") if arguments else "custom",
                start_date=arguments.get("start_date") if arguments else None,
                end_date=arguments.get("end_date") if arguments else None,
                relative_period=arguments.get("relative_period") if arguments else None,
                sort_by=arguments.get("sort_by") if arguments else None,
                sort_order=arguments.get("sort_order") if arguments else None,
                limit=arguments.get("limit", 100) if arguments else 100
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "search_by_tags_advanced":
            result = await run_client_call(
                client.search_by_tags_advanced,
                include_tags=arguments.get("include_tags") if arguments else None,
                exclude_tags=arguments.get("exclude_tags") if arguments else None,
                tag_logic=arguments.get("tag_logic", "OR") if arguments else "OR",
                sort_by=arguments.get("sort_by") if arguments else None,
                sort_order=arguments.get("sort_order") if arguments else None,
                limit=arguments.get("limit", 100) if arguments else 100
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_ticket_bundle_zendesk":
            if not arguments:
                raise ValueError("Missing arguments")
            ticket_id = arguments.get("ticket_id")
            if ticket_id is None:
                raise ValueError("ticket_id is required")
            comment_limit = arguments.get("comment_limit", 50)
            audit_limit = arguments.get("audit_limit", 100)

            result = await run_client_call(
                client.get_ticket_bundle,
                int(ticket_id),
                comment_limit,
                audit_limit,
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "batch_search_tickets":
            if not arguments:
                raise ValueError("Missing arguments")
            queries = arguments.get("queries")
            if not queries:
                raise ValueError("queries is required")

            result = await run_client_call(
                client.batch_search_tickets,
                queries=queries,
                deduplicate=arguments.get("deduplicate", True),
                sort_by=arguments.get("sort_by"),
                sort_order=arguments.get("sort_order"),
                limit_per_query=arguments.get("limit_per_query", 100)
            )
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        else:
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
