# Zendesk MCP Server

![ci](https://github.com/reminia/zendesk-mcp-server/actions/workflows/ci.yml/badge.svg)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A Model Context Protocol server for Zendesk.

This server provides a comprehensive integration with Zendesk. It offers:

- Tools for retrieving and managing Zendesk tickets and comments
- SLA policy integration and breach detection for proactive support management
- Specialized prompts for ticket analysis and response drafting
- Full access to the Zendesk Help Center articles as knowledge base

![demo](https://res.cloudinary.com/leecy-me/image/upload/v1736410626/open/zendesk_yunczu.gif)

## Setup

- build: `uv venv && uv pip install -e .` or `uv build` in short.
- setup zendesk credentials in `.env` file, refer to [.env.example](.env.example).
- configure in Claude desktop:

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

## Resources

- zendesk://knowledge-base, get access to the whole help center articles.

## Prompts

### analyze-ticket

Analyze a Zendesk ticket and provide a detailed analysis of the ticket.

### draft-ticket-response

Draft a response to a Zendesk ticket.

## Tools

### get_tickets

Fetch the latest tickets with pagination support

- Input:
  - `page` (integer, optional): Page number (defaults to 1)
  - `per_page` (integer, optional): Number of tickets per page, max 100 (defaults to 25)
  - `sort_by` (string, optional): Field to sort by - created_at, updated_at, priority, or status (defaults to created_at)
  - `sort_order` (string, optional): Sort order - asc or desc (defaults to desc)

- Output: Returns a list of tickets with essential fields including id, subject, status, priority, description, timestamps, and assignee information, along with pagination metadata

### get_ticket

Retrieve a Zendesk ticket by its ID

- Input:
  - `ticket_id` (integer): The ID of the ticket to retrieve

### get_ticket_comments

Retrieve all comments for a Zendesk ticket by its ID

- Input:
  - `ticket_id` (integer): The ID of the ticket to get comments for

### create_ticket_comment

Create a new comment on an existing Zendesk ticket

- Input:
  - `ticket_id` (integer): The ID of the ticket to comment on
  - `comment` (string): The comment text/content to add
  - `public` (boolean, optional): Whether the comment should be public (defaults to true)

### create_ticket

Create a new Zendesk ticket

- Input:
  - `subject` (string): Ticket subject
  - `description` (string): Ticket description
  - `requester_id` (integer, optional)
  - `assignee_id` (integer, optional)
  - `priority` (string, optional): one of `low`, `normal`, `high`, `urgent`
  - `type` (string, optional): one of `problem`, `incident`, `question`, `task`
  - `tags` (array[string], optional)
  - `custom_fields` (array[object], optional)

### update_ticket

Update fields on an existing Zendesk ticket (e.g., status, priority, assignee)

- Input:
  - `ticket_id` (integer): The ID of the ticket to update
  - `subject` (string, optional)
  - `status` (string, optional): one of `new`, `open`, `pending`, `on-hold`, `solved`, `closed`
  - `priority` (string, optional): one of `low`, `normal`, `high`, `urgent`
  - `type` (string, optional)
  - `assignee_id` (integer, optional)
  - `requester_id` (integer, optional)
  - `tags` (array[string], optional)
  - `custom_fields` (array[object], optional)
  - `due_at` (string, optional): ISO8601 datetime

### search_tickets

Search for tickets using Zendesk's powerful query syntax (returns up to 1000 results)

- Input:
  - `query` (string, required): Search query using Zendesk syntax
  - `sort_by` (string, optional): Field to sort by - `updated_at`, `created_at`, `priority`, `status`, or `ticket_type`
  - `sort_order` (string, optional): Sort order - `asc` or `desc`
  - `limit` (integer, optional): Maximum results to return (default 100, max 1000)

- Query Syntax Examples:
  - `status:open` - Find open tickets
  - `priority:high status:open` - High priority open tickets
  - `created>2024-01-01` - Tickets created after a date
  - `tags:bug tags:urgent` - Tickets with bug OR urgent tag
  - `assignee:email@example.com` - Tickets assigned to a user
  - `assignee:none` - Unassigned tickets
  - `subject:login*` - Subject containing words starting with "login"
  - `status:pending -tags:spam` - Pending tickets without spam tag
  - `organization:"Company Name"` - Tickets from an organization

- Operators:
  - `:` (equals), `>` (greater than), `<` (less than), `>=`, `<=`
  - `-` (exclude), `*` (wildcard), `" "` (phrase search)

- Output: Returns matching tickets with metadata including count, query info, and pagination status

### search_tickets_export

Search for tickets using the export API for unlimited results (no 1000 limit)

- Input:
  - `query` (string, required): Same query syntax as `search_tickets`
  - `sort_by` (string, optional): Field to sort by
  - `sort_order` (string, optional): Sort order - `asc` or `desc`
  - `max_results` (integer, optional): Optional limit on results (default: unlimited)

- Note: This endpoint can return very large result sets and may take significant time. Use for bulk exports or when you know there are >1000 matching tickets.

- Output: Returns all matching tickets with metadata including total count and query info

### upload_attachment

Upload a file to Zendesk to get an attachment token that can be used when creating or updating tickets

- Input:
  - `file_path` (string, required): Path to the file to upload (absolute or relative)

- Output: Returns upload details including:
  - `token`: The upload token to use in the `uploads` array when creating/updating ticket comments
  - `filename`: The uploaded filename
  - `size`: File size in bytes
  - `content_type`: MIME type of the file
  - `expires_at`: Token expiration information (60 minutes)

- Notes:
  - File size limit is 50 MB
  - Tokens expire after 60 minutes
  - Use the token in `create_ticket_comment` by passing it in the comment body

### get_ticket_attachments

List all attachments from all comments on a ticket

- Input:
  - `ticket_id` (integer, required): The ID of the ticket to get attachments from

- Output: Returns attachment details including:
  - `attachments`: List of all attachments with details:
    - `id`: Attachment ID
    - `filename`: File name
    - `content_url`: Direct download URL
    - `content_type`: MIME type
    - `size`: File size in bytes
    - `comment_id`: ID of the comment containing the attachment
    - `created_at`: When the attachment was added
    - `author_id`: User who added the attachment
  - `total_count`: Total number of attachments
  - `total_size`: Total size of all attachments in bytes
  - `total_size_mb`: Total size in megabytes

### download_attachment

Download an attachment by its ID

- Input:
  - `attachment_id` (integer, required): The ID of the attachment to download
  - `save_path` (string, optional): Path to save the file. If not provided, returns download URL only.

- Output: Returns download details including:
  - `attachment_id`: The attachment ID
  - `filename`: The attachment filename
  - `content_url`: Direct download URL (can be used to download the file)
  - `content_type`: MIME type
  - `size`: File size in bytes
  - `saved_to`: Path where file was saved (only if `save_path` was provided)
  - `downloaded`: Boolean indicating if file was downloaded (only if `save_path` was provided)

- Notes:
  - If `save_path` is not provided, only returns the `content_url` for manual download
  - If `save_path` is provided, automatically downloads and saves the file

### find_related_tickets

Find tickets related to the given ticket by subject similarity, same requester, or same organization

- Input:
  - `ticket_id` (integer, required): The ID of the reference ticket to find related tickets for
  - `limit` (integer, optional): Maximum number of related tickets to return (default 100)

- Output: Returns related tickets with:
  - `related_tickets`: List of related tickets with relevance scores and reasons
  - `count`: Number of related tickets found
  - `reference_ticket`: Basic info about the reference ticket
  - `search_strategy`: Description of how tickets were found

- Notes:
  - Uses Zendesk's search export API for unlimited historical results
  - Searches by similar subjects, same requester, and same organization
  - Results are deduplicated and ranked by relevance
  - Each ticket includes `relevance_score` and `relevance_reason` fields

### find_duplicate_tickets

Identify potential duplicate tickets with highly similar subjects and same requester/organization

- Input:
  - `ticket_id` (integer, required): The ID of the reference ticket to find duplicates for
  - `limit` (integer, optional): Maximum number of duplicate candidates to return (default 100)

- Output: Returns duplicate candidates with:
  - `duplicate_candidates`: List of potential duplicate tickets
  - `count`: Number of duplicate candidates found
  - `reference_ticket`: Basic info about the reference ticket
  - `similarity_threshold`: Minimum similarity score for duplicates (0.7)

- Notes:
  - Uses similarity scoring with 0.7 threshold for duplicate detection
  - Filters by same requester or organization for better precision
  - Each candidate includes `similarity_score` and `duplicate_reason` fields
  - Sorted by similarity score and creation date (older duplicates first)

### find_ticket_thread

Find all tickets in a conversation thread using via_id relationships

- Input:
  - `ticket_id` (integer, required): The ID of the reference ticket to find the thread for

- Output: Returns thread information with:
  - `thread_tickets`: List of all tickets in the thread (chronological order)
  - `count`: Number of tickets in the thread
  - `thread_root`: The root ticket of the thread (if exists)
  - `thread_structure`: Description of the thread structure
  - `reference_ticket_id`: The original ticket ID

- Notes:
  - Discovers parent tickets and child tickets to show complete conversation chain
  - Uses Zendesk's via_id field to track ticket relationships
  - Returns tickets in chronological order with relationship information
  - Each ticket includes a `relationship` field (parent, child, reference)

### get_ticket_relationships

Get parent/child ticket relationships via the via field

- Input:
  - `ticket_id` (integer, required): The ID of the reference ticket to get relationships for

- Output: Returns structured relationship data with:
  - `relationships`: Complete relationship structure
  - `parent_ticket`: Parent ticket info (if exists)
  - `child_tickets`: List of child tickets
  - `sibling_tickets`: List of sibling tickets (same parent)
  - `relationship_type`: Description of the relationship
  - `total_related`: Total number of related tickets

- Notes:
  - Shows structured relationship data including parent, child, and sibling tickets
  - Helps understand ticket hierarchy and conversation flow
  - Each ticket includes relationship type (parent, child, sibling)
  - Relationship types: "Standalone ticket", "Child ticket", "Parent ticket", "Middle ticket in chain", "Sibling ticket"

## Enhanced Search Tools

### get_ticket_fields

Retrieve all ticket fields including custom fields with their definitions

- Input: None (no parameters required)

- Output: Returns field definitions with:
  - `fields`: List of all ticket fields with details
  - `custom_fields`: List of custom fields only
  - `system_fields`: List of system fields only
  - `count`: Total number of fields
  - `custom_count`: Number of custom fields
  - `system_count`: Number of system fields

- Notes:
  - Each field includes ID, title, type, description, required status, and options
  - Custom fields include dropdown options and validation rules
  - Use field IDs to search by custom fields with `custom_field_12345:"value"` syntax

### search_by_source

Search for tickets created via a specific integration source/channel

- Input:
  - `channel` (string, required): Creation channel (email, web, mobile, api, chat, etc.)
  - `sort_by` (string, optional): Field to sort by
  - `sort_order` (string, optional): Sort order (asc or desc)
  - `limit` (integer, optional): Maximum results (default 100, max 1000)

- Output: Returns tickets created via the specified channel

- Notes:
  - Uses Zendesk's `via.channel` field for filtering
  - Common channels: email, web, mobile, api, chat, voice, twitter, facebook
  - Helps analyze ticket volume by creation method

### search_tickets_enhanced

Enhanced ticket search with client-side filtering capabilities

- Input:
  - `query` (string, required): Base Zendesk search query
  - `regex_pattern` (string, optional): Regex pattern to filter results
  - `fuzzy_term` (string, optional): Term for fuzzy matching (handles typos)
  - `fuzzy_threshold` (number, optional): Similarity threshold 0.0-1.0 (default 0.7)
  - `proximity_terms` (array, optional): Terms for proximity search (2+ terms)
  - `proximity_distance` (integer, optional): Max words between terms (default 5)
  - `sort_by` (string, optional): Field to sort by
  - `sort_order` (string, optional): Sort order
  - `limit` (integer, optional): Maximum results (default 100)

- Output: Returns filtered tickets with enhancement metadata

- Notes:
  - **WARNING**: Client-side processing may impact performance with large result sets
  - Regex examples: `\b[A-Z]{2,}\b` for uppercase words, `\d{4}-\d{2}-\d{2}` for dates
  - Fuzzy matching helps find tickets with typos or variations
  - Proximity search finds tickets where terms appear within N words of each other
  - Results include match information (field, score, distance)

### build_search_query

Build a Zendesk search query from structured parameters

- Input:
  - `status` (string, optional): Ticket status (new, open, pending, on-hold, solved, closed)
  - `priority` (string, optional): Priority (low, normal, high, urgent)
  - `assignee` (string, optional): Assignee email or "none" for unassigned
  - `requester` (string, optional): Requester email
  - `organization` (string, optional): Organization name
  - `tags` (array, optional): List of tags to include
  - `tags_logic` (string, optional): Logic for tags (AND or OR, default OR)
  - `exclude_tags` (array, optional): List of tags to exclude
  - `created_after` (string, optional): Created after date (ISO8601)
  - `created_before` (string, optional): Created before date (ISO8601)
  - `updated_after` (string, optional): Updated after date (ISO8601)
  - `updated_before` (string, optional): Updated before date (ISO8601)
  - `solved_after` (string, optional): Solved after date (ISO8601)
  - `solved_before` (string, optional): Solved before date (ISO8601)
  - `due_after` (string, optional): Due after date (ISO8601)
  - `due_before` (string, optional): Due before date (ISO8601)
  - `custom_fields` (object, optional): Custom field IDs to values
  - `subject_contains` (string, optional): Text to search in subject
  - `description_contains` (string, optional): Text to search in description
  - `comment_contains` (string, optional): Text to search in comments

- Output: Returns generated query string and usage examples

- Notes:
  - Helps construct complex queries without knowing Zendesk syntax
  - Returns properly formatted query string ready for use
  - Includes examples and parameter validation

## Search Analytics Tools

### get_search_statistics

Analyze search results and return aggregated statistics

- Input:
  - `query` (string, required): Zendesk search query to analyze
  - `sort_by` (string, optional): Field to sort by
  - `sort_order` (string, optional): Sort order (asc or desc)
  - `limit` (integer, optional): Maximum tickets to analyze (default 1000)

- Output: Returns comprehensive statistics including:
  - `by_status`: Count by ticket status
  - `by_priority`: Count by priority level
  - `by_assignee`: Top assignees
  - `by_requester`: Top requesters
  - `by_organization`: Top organizations
  - `by_tags`: Most common tags
  - `by_month`: Distribution by creation month
  - `resolution_time`: Average, min, max resolution times
  - `summary`: Key insights and top performers

- Notes:
  - Provides insights for reporting and analysis
  - Calculates resolution times for solved tickets
  - Identifies top performers and common patterns
  - Useful for dashboards and management reporting

### get_case_volume_analytics

Comprehensive ticket analytics including volumes, response times, resolution times, channel breakdowns, assignment metrics, status transitions, and satisfaction scores.

- Input:
  - `start_date` (string, optional): Inclusive start date (`YYYY-MM-DD`). Defaults to the earliest date covering the last 13 weeks and 12 months.
  - `end_date` (string, optional): Inclusive end date (`YYYY-MM-DD`). Defaults to today (UTC).
  - `max_results` (integer, optional): Optional cap on the number of tickets analyzed.
  - `include_metrics` (array, optional): Metric types to include. Options: `response_times`, `resolution_times`, `channels`, `forms`, `assignments`, `status_transitions`, `satisfaction`. Defaults to all metrics.
  - `group_by` (array, optional): Dimensions to group by. Options: `channel`, `form`, `priority`, `type`, `group_id`, `tags`, `requester`, `organization`, `custom_fields`.
  - `filter_by_status` (array, optional): Filter tickets to specific statuses (e.g., `['open', 'solved']`).
  - `filter_by_priority` (array, optional): Filter tickets to specific priorities (e.g., `['high', 'urgent']`).
  - `filter_by_tags` (array, optional): Filter tickets to those containing any of the specified tags (e.g., `['bug', 'urgent']`).
  - `time_bucket` (string, optional): Time bucketing granularity. Options: `daily`, `weekly`, `monthly`. Defaults to `weekly`.

- Output: Returns comprehensive analytics payload containing:
  - `time_series`: Ticket counts based on selected time_bucket (daily/weekly/monthly)
  - `weekly_counts`: Ticket counts per ISO week (zero-filled for missing weeks)
  - `monthly_counts`: Ticket counts per month
  - `daily_counts`: Ticket counts per day
  - `technician_weekly_counts`: Weekly breakdown per assignee, including unassigned tickets
  - `requester_weekly_counts`: Weekly breakdown per requester (ticket volume by requester over time)
  - `requester_breakdown`: Total ticket counts by requester ID (sorted by volume)
  - `organization_weekly_counts`: Weekly breakdown per organization (ticket volume by organization over time)
  - `organization_breakdown`: Total ticket counts by organization ID (sorted by volume)
  - `custom_field_breakdown`: Ticket counts by custom field ID and value (top 20 values per field)
  - `custom_field_weekly_counts`: Weekly breakdown per custom field value (top 100 field:value combinations)
  - `totals`: Overall ticket totals, assignment breakdown, status/priority/type distribution
  - `response_time_metrics`: Statistics for reply time, agent wait time, requester wait time (avg, min, max, median)
  - `resolution_time_metrics`: Statistics for first resolution, full resolution, and on-hold times
  - `channel_breakdown`: Ticket counts by creation channel (email, web, mobile, api, chat, etc.)
  - `form_breakdown`: Ticket counts by ticket form ID
  - `group_breakdown`: Ticket counts by group ID
  - `assignment_metrics`: Assignment time statistics
  - `status_transition_metrics`: Status change counts and time-in-status statistics
  - `satisfaction_metrics`: Average satisfaction score, total ratings, and score distribution
  - `tag_breakdown`: Ticket counts by tag (sorted by frequency)
  - `tag_weekly_counts`: Weekly breakdown per tag (top 50 tags by volume)
  - `grouped_breakdowns`: Additional breakdowns when `group_by` is specified
  - `range`: Metadata describing the analyzed date range and bucket counts

- Notes:
  - **Time Metrics**: Response and resolution times are extracted from Zendesk's metric_set object. Not all tickets have complete metric data.
  - **Channel/Source**: Extracted from the `via` object. Common channels include email, web, mobile, api, chat, voice, twitter, facebook.
  - **Satisfaction**: Only includes tickets with satisfaction ratings. Scores range from 1-5 (good) or -1 (bad).
  - **Time Buckets**: 
    - `daily`: Provides day-by-day counts (useful for short-term analysis)
    - `weekly`: ISO week-based buckets (Monday starts), default
    - `monthly`: Calendar month buckets
  - **Filtering**: Filters are applied client-side after fetching tickets. Use Zendesk search queries for server-side filtering when possible.
  - **Grouping**: Multiple dimensions can be grouped simultaneously. Results include separate breakdowns for each dimension.
  - **Tags**: Tag analytics are automatically included. Use `filter_by_tags` to analyze specific tags, or `group_by: ['tags']` to see tag-based groupings. Tag weekly counts show how tag usage trends over time.
  - **Requesters**: Requester analytics track ticket volume by requester over time. Use `group_by: ['requester']` to see requester-based groupings. Helps identify most active requesters and trends.
  - **Organizations**: Organization analytics track ticket volume by organization over time. Use `group_by: ['organization']` to see organization-based groupings. Useful for account management and understanding organizational ticket patterns.
  - **Custom Fields**: Custom field analytics automatically extract and track all custom field values. Breakdowns show ticket counts by field ID and value, with weekly trends for top values. Use `group_by: ['custom_fields']` to see custom field-based groupings. Limited to top 20 values per field and top 100 field:value combinations in weekly counts to manage response size.
  - Useful for capacity planning, workload trend analysis, SLA monitoring, agent performance evaluation, account management, and staffing decisions.

## Advanced Filtering Tools

### search_by_date_range

Search tickets by date range with support for relative dates

- Input:
  - `date_field` (string, optional): Date field (created, updated, solved, due, default created)
  - `range_type` (string, optional): Type (custom or relative, default custom)
  - `start_date` (string, optional): Start date (ISO8601 format)
  - `end_date` (string, optional): End date (ISO8601 format)
  - `relative_period` (string, optional): Relative period (last_7_days, last_30_days, this_month, last_month, this_quarter, last_quarter)
  - `sort_by` (string, optional): Field to sort by
  - `sort_order` (string, optional): Sort order
  - `limit` (integer, optional): Maximum results (default 100)

- Output: Returns tickets in the specified date range

- Notes:
  - Supports both custom date ranges and predefined periods
  - Relative periods automatically calculate start/end dates
  - Useful for time-based analysis and reporting

### search_by_tags_advanced

Advanced tag-based search with AND/OR/NOT logic

- Input:
  - `include_tags` (array, optional): Tags to include in search
  - `exclude_tags` (array, optional): Tags to exclude from search
  - `tag_logic` (string, optional): Logic for include_tags (AND or OR, default OR)
  - `sort_by` (string, optional): Field to sort by
  - `sort_order` (string, optional): Sort order
  - `limit` (integer, optional): Maximum results (default 100)

- Output: Returns tickets matching tag criteria

- Notes:
  - AND logic: tickets must have ALL include_tags
  - OR logic: tickets must have ANY include_tags
  - Exclude tags always use NOT logic
  - Useful for complex tag-based filtering

### batch_search_tickets

Execute multiple searches concurrently and return grouped results

- Input:
  - `queries` (array, required): List of search queries to execute
  - `deduplicate` (boolean, optional): Remove duplicates across queries (default true)
  - `sort_by` (string, optional): Field to sort by
  - `sort_order` (string, optional): Sort order
  - `limit_per_query` (integer, optional): Maximum results per query (default 100)

- Output: Returns grouped results with execution metrics:
  - `queries_executed`: Number of queries executed
  - `total_tickets`: Total tickets found
  - `unique_tickets`: Unique tickets (if deduplication applied)
  - `total_execution_time_ms`: Total execution time
  - `query_results`: Results grouped by query
  - `all_tickets`: Combined unique tickets (if deduplication applied)

- Notes:
  - Executes searches concurrently for better performance
  - Useful for dashboards and multi-criteria reporting
  - Can deduplicate results across queries
  - Provides execution metrics for performance monitoring

### get_sla_policies

Retrieve all SLA policies configured in Zendesk

- Input: None

- Output: Returns all SLA policies with their configurations including targets for first reply time, next reply time, and resolution time

- Notes:
  - Useful for understanding SLA requirements and thresholds
  - See [SLA Functionality Documentation](docs/SLA_FUNCTIONALITY.md) for detailed usage

### get_sla_policy

Retrieve a specific SLA policy by ID

- Input:
  - `policy_id` (integer, required): The ID of the SLA policy to retrieve

- Output: Returns detailed SLA policy configuration including targets, conditions, and business hours settings

### get_ticket_sla_status

Get comprehensive SLA status and breach information for a specific ticket

- Input:
  - `ticket_id` (integer, required): The ID of the ticket to check

- Output: Returns SLA status including:
  - Overall status (ok, at_risk, or breached)
  - List of breaches with timestamps and policy details
  - Active SLA policies
  - At-risk metrics

- Notes:
  - Uses Ticket Metric Events API to determine breach status
  - Tracks first reply time, next reply time, and resolution time breaches
  - See [SLA Functionality Documentation](docs/SLA_FUNCTIONALITY.md) for detailed usage

### search_tickets_with_sla_breaches

Search for tickets that have breached their SLA targets

- Input:
  - `breach_type` (string, optional): Filter by specific breach type (first_reply_time, next_reply_time, resolution_time)
  - `status` (string, optional): Filter by ticket status
  - `priority` (string, optional): Filter by ticket priority
  - `limit` (integer, optional): Maximum number of tickets to return (default 100)

- Output: Returns tickets with SLA breaches, each including detailed breach information

- Notes:
  - Useful for SLA compliance monitoring
  - Can filter by specific breach types
  - Each ticket includes full SLA status details

### get_tickets_at_risk_of_breach

Find tickets that are at risk of breaching their SLA but haven't breached yet

- Input:
  - `status` (string, optional): Filter by ticket status (default: open and pending)
  - `priority` (string, optional): Filter by ticket priority
  - `limit` (integer, optional): Maximum number of tickets to return (default 50)

- Output: Returns tickets at risk of SLA breach with risk details

- Notes:
  - Useful for proactive SLA management
  - Helps identify tickets that need immediate attention
  - Default filters to open/pending tickets for active monitoring

### get_recent_tickets_with_csat

Retrieve recent solved tickets with CSAT (Customer Satisfaction) scores and comments

- Input:
  - `limit` (integer, optional): Maximum number of tickets to return (default 20)

- Output: Returns recent solved tickets with CSAT scores and customer comments, including:
  - Ticket ID, subject, status, priority
  - CSAT score and any customer comments
  - Summary statistics (total with CSAT, total with comments, score distribution)

- Example Output:
  ```json
  {
    "tickets": [
      {
        "ticket_id": 137518,
        "subject": "Dremio Cloud - PowerBI Connection error after enabling SSO",
        "status": "solved",
        "priority": "normal",
        "score": "good",
        "comment": "Great support team!",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-16T14:30:00Z",
        "source": "legacy_satisfaction_rating"
      }
    ],
    "count": 20,
    "summary": {
      "total_with_csat": 20,
      "total_with_comments": 5,
      "score_distribution": {
        "good": 8,
        "offered": 10,
        "unoffered": 2
      }
    }
  }
  ```

- Notes:
  - Retrieves solved tickets with satisfaction ratings
  - Includes both legacy satisfaction ratings and CSAT survey responses
  - Useful for analyzing customer satisfaction trends and feedback
  - Comments are included when available

### get_tickets_with_csat_this_week

Retrieve all tickets with CSAT scores from this week

- Input: None

- Output: Returns all solved tickets updated this week that have CSAT scores, including:
  - Ticket ID, subject, status, priority
  - CSAT score and any customer comments
  - Week start and end dates
  - Summary statistics (total with CSAT, total with comments, score distribution)

- Example Output:
  ```json
  {
    "tickets": [
      {
        "ticket_id": 137518,
        "subject": "Dremio Cloud - PowerBI Connection error after enabling SSO",
        "status": "solved",
        "priority": "normal",
        "score": "good",
        "comment": null,
        "created_at": "2025-10-27T17:14:10Z",
        "updated_at": "2025-10-31T10:19:28Z",
        "source": "legacy_satisfaction_rating"
      }
    ],
    "count": 76,
    "week_start": "2025-10-27",
    "week_end": "2025-11-03",
    "summary": {
      "total_with_csat": 76,
      "total_with_comments": 1,
      "score_distribution": {
        "good": 7,
        "offered": 66,
        "unoffered": 3
      }
    }
  }
  ```

- Notes:
  - Automatically calculates this week's date range (Monday to Sunday)
  - Searches for solved tickets updated during the week
  - Useful for weekly satisfaction tracking and monitoring
  - Includes both legacy satisfaction ratings and CSAT survey responses