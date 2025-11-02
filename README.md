# Zendesk MCP Server

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)

A comprehensive Model Context Protocol (MCP) server for Zendesk providing AI-powered ticket management, analytics, and knowledge base integration.

This server enables Claude and other AI applications to:

- **Manage tickets** - Create, retrieve, update, and search Zendesk tickets
- **Analyze conversations** - Extract relationships, find duplicates, and discover threads
- **Track SLA compliance** - Monitor SLA breaches and ticket metrics
- **Measure satisfaction** - Access CSAT survey responses and analytics
- **Search knowledge base** - Query Help Center articles for solutions
- **Generate insights** - Analyze case volume trends and ticket patterns

## Quick Start

### Prerequisites

- Python 3.12+
- Zendesk account with API credentials

### Installation

```bash
# Clone the repository
git clone https://github.com/direkt/zendesk-mcp-server.git
cd zendesk-mcp-server

# Create virtual environment and install
uv venv && uv pip install -e .

# Set up credentials
cp .env.example .env
# Edit .env with your Zendesk subdomain, email, and API key
```

### Configure in Claude Desktop

Add to your Claude Desktop `settings.json`:

```json
{
  "mcpServers": {
    "zendesk": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/zendesk-mcp-server",
        "run",
        "zendesk"
      ]
    }
  }
}
```

### Docker Deployment

```bash
# Build Docker image
docker build -t zendesk-mcp-server .

# Run with environment file
docker run --rm --env-file .env -i zendesk-mcp-server
```

For Claude Desktop with Docker:

```json
{
  "mcpServers": {
    "zendesk": {
      "command": "/usr/local/bin/docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/path/to/zendesk-mcp-server/.env",
        "zendesk-mcp-server"
      ]
    }
  }
}
```

## Resources

- **zendesk://knowledge-base** - Search across all Help Center articles

## Prompts

### analyze-ticket

Analyze a Zendesk ticket with full context including relationships, SLA status, and knowledge base suggestions.

```
Analyze ticket #{ticket_id} and provide:
1. Issue summary and timeline
2. Related tickets and duplicates
3. SLA compliance status
4. Relevant knowledge base articles
5. Recommended actions
```

### draft-ticket-response

Draft a professional response to a ticket using relevant documentation and best practices.

```
Draft a response to ticket #{ticket_id} that:
1. Addresses customer's issue
2. References relevant KB articles
3. Maintains professional tone
4. Provides actionable next steps
```

## Core Ticket Tools

### get_tickets
Fetch the latest tickets with pagination support

**Input:**
- `page` (integer, optional): Page number (default: 1)
- `per_page` (integer, optional): Results per page, max 100 (default: 25)
- `sort_by` (string, optional): Sort field - `created_at`, `updated_at`, `priority`, `status` (default: `created_at`)
- `sort_order` (string, optional): Order - `asc` or `desc` (default: `desc`)

**Output:** List of tickets with ID, subject, status, priority, timestamps, and assignee info

### get_ticket
Retrieve a single Zendesk ticket by ID

**Input:**
- `ticket_id` (integer, required): The ticket ID

**Output:** Complete ticket details including all custom fields

### create_ticket
Create a new Zendesk ticket

**Input:**
- `subject` (string, required): Ticket subject
- `description` (string, required): Issue description
- `requester_id` (integer, optional): Requester user ID
- `assignee_id` (integer, optional): Assigned agent ID
- `priority` (string, optional): `low`, `normal`, `high`, `urgent`
- `type` (string, optional): `problem`, `incident`, `question`, `task`
- `tags` (array, optional): Tag list
- `custom_fields` (array, optional): Custom field objects

**Output:** Created ticket with ID and full details

### update_ticket
Update ticket fields (status, priority, assignee, etc.)

**Input:**
- `ticket_id` (integer, required): Ticket to update
- `subject` (string, optional): New subject
- `status` (string, optional): `new`, `open`, `pending`, `on-hold`, `solved`, `closed`
- `priority` (string, optional): Priority level
- `assignee_id` (integer, optional): New assignee
- `requester_id` (integer, optional): New requester
- `tags` (array, optional): New tags
- `custom_fields` (array, optional): Updated field values
- `due_at` (string, optional): Due date (ISO8601)

**Output:** Updated ticket details

## Comment & Attachment Tools

### get_ticket_comments
Retrieve all comments for a ticket

**Input:**
- `ticket_id` (integer, required): The ticket ID

**Output:** List of all comments with author, timestamp, and content

### create_ticket_comment
Add a new comment to a ticket

**Input:**
- `ticket_id` (integer, required): Ticket ID
- `comment` (string, required): Comment text
- `public` (boolean, optional): Public or internal comment (default: `true`)

**Output:** Created comment details

### get_ticket_attachments
List all attachments on a ticket

**Input:**
- `ticket_id` (integer, required): Ticket ID

**Output:** All attachments with size, type, download URL, and creation date

### download_attachment
Download an attachment by ID

**Input:**
- `attachment_id` (integer, required): Attachment ID
- `save_path` (string, optional): Local path to save file

**Output:** Download URL and file metadata; optionally saves file locally

## Advanced Search Tools

### search_tickets
Search tickets using Zendesk query language (max 1000 results)

**Input:**
- `query` (string, required): Zendesk search query
- `sort_by` (string, optional): Sort field
- `sort_order` (string, optional): Sort direction
- `limit` (integer, optional): Max results (default: 100, max: 1000)

**Example queries:**
- `status:open priority:high` - Open high-priority tickets
- `created>2024-01-01` - Created after a date
- `assignee:email@example.com` - Assigned to specific agent
- `tags:bug -tags:spam` - Has 'bug' tag but not 'spam'
- `subject:login*` - Subject starting with "login"

**Output:** Matching tickets with count and query metadata

### search_tickets_export
Search with unlimited results using export API

**Input:**
- `query` (string, required): Zendesk search query
- `sort_by` (string, optional): Sort field
- `sort_order` (string, optional): Sort direction
- `max_results` (integer, optional): Limit results (default: unlimited)

**Output:** All matching tickets (may be large datasets)

### search_tickets_enhanced
Advanced search with client-side filtering (regex, fuzzy, proximity)

**Input:**
- `query` (string, required): Base Zendesk search query
- `regex_pattern` (string, optional): Regex to filter results
- `fuzzy_term` (string, optional): Term for fuzzy matching
- `fuzzy_threshold` (number, optional): Similarity threshold 0.0-1.0 (default: 0.7)
- `proximity_terms` (array, optional): Terms for proximity search
- `proximity_distance` (integer, optional): Max words between terms (default: 5)
- `sort_by` (string, optional): Sort field
- `sort_order` (string, optional): Sort direction
- `limit` (integer, optional): Max results (default: 100)

**Output:** Filtered tickets with match metadata

### search_by_date_range
Search by date range with relative period support

**Input:**
- `date_field` (string, optional): Field - `created`, `updated`, `solved`, `due` (default: `created`)
- `range_type` (string, optional): Type - `custom` or `relative` (default: `custom`)
- `start_date` (string, optional): Start date (ISO8601)
- `end_date` (string, optional): End date (ISO8601)
- `relative_period` (string, optional): `last_7_days`, `last_30_days`, `this_month`, `last_month`, `this_quarter`, `last_quarter`
- `sort_by` (string, optional): Sort field
- `sort_order` (string, optional): Sort direction
- `limit` (integer, optional): Max results (default: 100)

**Output:** Tickets within date range

### search_by_tags_advanced
Advanced tag searching with AND/OR/NOT logic

**Input:**
- `include_tags` (array, optional): Tags to include
- `exclude_tags` (array, optional): Tags to exclude
- `tag_logic` (string, optional): `AND` or `OR` for include_tags (default: `OR`)
- `sort_by` (string, optional): Sort field
- `sort_order` (string, optional): Sort direction
- `limit` (integer, optional): Max results (default: 100)

**Output:** Tickets matching tag criteria

### search_by_integration_source
Search tickets by creation channel/source

**Input:**
- `channel` (string, required): Channel - `email`, `web`, `mobile`, `api`, `chat`, `voice`, `twitter`, `facebook`, etc.
- `sort_by` (string, optional): Sort field
- `sort_order` (string, optional): Sort direction
- `limit` (integer, optional): Max results (default: 100)

**Output:** Tickets created via specified channel

## Relationship & Thread Tools

### find_ticket_thread
Find all tickets in a conversation thread

**Input:**
- `ticket_id` (integer, required): Reference ticket ID

**Output:** Complete thread with root ticket, parent/child relationships, and chronological order

### find_related_tickets
Find related tickets by subject similarity, requester, or organization

**Input:**
- `ticket_id` (integer, required): Reference ticket ID
- `limit` (integer, optional): Max results (default: 100)

**Output:** Related tickets with relevance scores and reasons

### find_duplicate_tickets
Identify potential duplicate tickets (similar subject, same requester/org)

**Input:**
- `ticket_id` (integer, required): Reference ticket ID
- `limit` (integer, optional): Max results (default: 100)

**Output:** Duplicate candidates with similarity scores (threshold: 0.7)

### get_ticket_relationships
Get structured parent/child/sibling relationships

**Input:**
- `ticket_id` (integer, required): Reference ticket ID

**Output:** Relationship hierarchy - parent, children, siblings with types

## Ticket Audit & Metrics Tools

### get_ticket_audits
Retrieve audit history for a ticket with pagination

**Input:**
- `ticket_id` (integer, required): Ticket ID
- `limit` (integer, optional): Results per page (default: 100)
- `cursor` (string, optional): Pagination cursor

**Output:** All changes to ticket with timestamps and author info

### get_ticket_bundle
Get ticket with full context - comments, audits, and relationships

**Input:**
- `ticket_id` (integer, required): Ticket ID

**Output:** Complete ticket bundle with timeline, comments, audits, and related tickets

### get_ticket_metric_events
Retrieve metric events for a ticket (created, first response, solved, etc.)

**Input:**
- `ticket_id` (integer, required): Ticket ID

**Output:** Key metric timestamps and agent activity

## SLA Compliance Tools

### get_sla_policies
List all SLA policies in your Zendesk instance

**Input:** None

**Output:** All SLA policies with conditions and targets

### get_sla_policy
Get details for a specific SLA policy

**Input:**
- `policy_id` (integer, required): Policy ID

**Output:** Policy details with conditions, targets, and filter criteria

### get_ticket_sla_status
Get SLA compliance status for a ticket

**Input:**
- `ticket_id` (integer, required): Ticket ID

**Output:** Active SLA policies, breach status, and time remaining

### get_tickets_at_risk_of_breach
Find tickets approaching SLA breach

**Input:**
- `hours_threshold` (integer, optional): Hours until breach considered "at risk" (default: 4)
- `limit` (integer, optional): Max results (default: 100)

**Output:** At-risk tickets with time until breach

### search_tickets_with_sla_breaches
Search for tickets that have breached SLA

**Input:**
- `limit` (integer, optional): Max results (default: 100)
- `sort_order` (string, optional): `asc` or `desc`

**Output:** Breached tickets with breach details

## CSAT & Satisfaction Tools

### get_recent_tickets_with_csat
Get recent tickets with CSAT survey responses

**Input:**
- `limit` (integer, optional): Max results (default: 25)
- `days_back` (integer, optional): Days to look back (default: 7)

**Output:** Recent tickets with CSAT scores and sentiment

### get_tickets_with_csat_this_week
Get this week's tickets with CSAT responses

**Input:** None

**Output:** This week's CSAT-surveyed tickets with scores

### get_ticket_csat_survey_responses
Get CSAT survey response for a specific ticket

**Input:**
- `ticket_id` (integer, required): Ticket ID

**Output:** Survey response with score, comment, and timestamp

### search_csat_survey_responses
Search CSAT responses by score or date range

**Input:**
- `min_score` (integer, optional): Minimum score (1-5)
- `max_score` (integer, optional): Maximum score (1-5)
- `date_field` (string, optional): `created` or `updated`
- `start_date` (string, optional): Start date (ISO8601)
- `end_date` (string, optional): End date (ISO8601)
- `limit` (integer, optional): Max results (default: 100)

**Output:** CSAT responses matching criteria with trends

## Analytics Tools

### get_search_statistics
Analyze search results and return aggregated statistics

**Input:**
- `query` (string, required): Zendesk search query
- `sort_by` (string, optional): Sort field
- `sort_order` (string, optional): Sort direction
- `limit` (integer, optional): Tickets to analyze (default: 1000)

**Output:** Comprehensive statistics including:
- Breakdown by status, priority, assignee
- Top requesters and organizations
- Common tags and creation patterns
- Average resolution times
- Key insights and top performers

### get_case_volume_analytics
Analyze case volume by time period and dimensions

**Input:**
- `query` (string, required): Search query for filtering
- `group_by` (string, optional): Dimension - `day`, `week`, `month`, `priority`, `status`, `assignee` (default: `day`)
- `days_back` (integer, optional): Historical days (default: 30)
- `limit` (integer, optional): Max results (default: 100)

**Output:** Time-series case volume with trends and metrics

## Knowledge Base Tools

### search_articles
Search Help Center articles

**Input:**
- `query` (string, required): Search term

**Output:** Matching articles with titles, snippets, and URLs

### get_article_by_id
Retrieve a specific KB article

**Input:**
- `article_id` (integer, required): Article ID

**Output:** Full article content with metadata

### get_all_articles
List all Help Center articles

**Input:**
- `limit` (integer, optional): Max results (default: 100)

**Output:** All articles with basic info

### get_sections_list
List KB sections/categories

**Input:** None

**Output:** All KB section hierarchies

### search_articles_by_labels
Search articles by label/tag

**Input:**
- `label` (string, required): Label/tag to search

**Output:** Articles matching the label

## Field & Configuration Tools

### get_ticket_fields
Retrieve all ticket field definitions

**Input:** None

**Output:** All system and custom fields with types, options, and validation rules

## Architecture

### Client Modules

- **tickets.py** - Ticket CRUD operations
- **search.py** - Advanced search and analytics
- **relationships.py** - Ticket relationship discovery
- **attachments.py** - File upload/download
- **kb.py** - Knowledge base search with caching
- **sla.py** - SLA compliance and metrics
- **csat.py** - Customer satisfaction tracking
- **base.py** - Core utilities and HTTP retry logic

### Key Features

- **Automatic retry logic** - Exponential backoff with jitter for transient failures
- **429 rate-limit handling** - Respects Retry-After headers
- **Cached KB search** - TTL-based caching for Help Center queries
- **Async handlers** - Non-blocking event loop execution
- **Error context** - Rich error information with HTTP status and response bodies

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test
uv run pytest tests/test_tickets.py

# Run with coverage
uv run pytest --cov=src/zendesk_mcp_server
```

### Build & Package

```bash
# Build wheel and sdist
uv build

# Output in dist/
```

## Security

- **Credentials** - Store API keys in `.env` (never commit)
- **Sensitive data** - Cache files excluded from git (.gitignore)
- **Input validation** - All tool inputs validated before API calls
- **Error handling** - Sensitive data scrubbed from error messages

## Environment Variables

Required `.env` variables:

```bash
ZENDESK_SUBDOMAIN=your-subdomain      # Zendesk instance subdomain
ZENDESK_EMAIL=agent@company.com       # Agent email for API auth
ZENDESK_API_KEY=your-api-token        # Zendesk API key
```

## License

Apache 2.0 - See LICENSE file for details

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Commit with clear messages
5. Submit a pull request

## Support

For issues, feature requests, or questions:
- Open an issue on GitHub
- Check existing documentation in this README
- Review test files for usage examples
