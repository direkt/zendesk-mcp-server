# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a **Model Context Protocol (MCP) server** that provides Claude and other AI applications with tools and resources to interact with Zendesk. It offers comprehensive ticket management, knowledge base access, advanced search capabilities, and analytics tools.

## Project Structure

```
zendesk-mcp-server/
├── src/zendesk_mcp_server/
│   ├── __init__.py                 # Entry point for the CLI
│   ├── server.py                   # MCP server setup, tool registration, prompts
│   ├── zendesk_client.py           # Lightweight wrapper for client initialization
│   ├── exceptions.py               # Custom exception hierarchy
│   ├── client/                     # Modular client implementations
│   │   ├── base.py                 # ZendeskClientBase with core utilities and retry logic
│   │   ├── tickets.py              # Ticket CRUD and search operations
│   │   ├── search.py               # Advanced search and analytics (search_tickets, search_tickets_export, etc.)
│   │   ├── attachments.py          # Attachment upload/download operations
│   │   ├── relationships.py        # Ticket relationship discovery (thread, duplicates, related)
│   │   └── kb.py                   # Knowledge base search and caching
│   └── handlers/                   # Tool request handlers
│       ├── tools.py                # Individual async tool handler functions
│       └── __init__.py             # Handler registration
├── tests/                          # Pytest-based test suite
├── pyproject.toml                  # uv/pip package metadata
├── uv.lock                         # Locked dependency versions
└── .env.example                    # Example configuration template
```

## Architecture & Key Patterns

### MCP Integration (server.py)

- **Tool Registration**: Tools are dynamically registered in `server.py` with schema definitions describing input parameters and behavior.
- **Async Handler Pattern**: Each tool request is handled by an async function in `handlers/tools.py` that validates inputs, delegates to the client, and returns JSON responses.
- **Prompt Templates**: Predefined prompts (`TICKET_ANALYSIS_TEMPLATE`, `COMMENT_DRAFT_TEMPLATE`) guide AI behavior for common tasks.
- **Client-as-Singleton**: `get_zendesk_client()` caches the client instance globally to reuse authentication and HTTP connections.

### Client Layer Architecture (src/zendesk_mcp_server/client/)

The client is organized into focused modules:

- **base.py**:
  - `ZendeskClientBase` — core initialization and shared utilities
  - `_urlopen_with_retry()` — module-level helper for HTTP requests with exponential backoff and 429 handling
  - Used by submodule methods when direct API calls are needed (bypassing zenpy)

- **tickets.py**: Ticket CRUD and basic listing (`get_ticket`, `get_tickets`, `create_ticket`, `update_ticket`, `post_comment`)

- **search.py**: Advanced ticket search
  - `search_tickets()` — standard search with 1000-result limit
  - `search_tickets_export()` — export API for unlimited results
  - `search_by_date_range()`, `search_by_tags_advanced()`, `batch_search_tickets()` — specialized queries
  - `get_search_statistics()`, `get_case_volume_analytics()` — analytics and aggregation

- **attachments.py**: File attachment operations (`upload_attachment`, `download_attachment`, `get_ticket_attachments`)

- **relationships.py**: Ticket relationship discovery using `via` field
  - `find_ticket_thread()` — discover parent/child ticket chains
  - `find_related_tickets()` — similarity-based discovery
  - `find_duplicate_tickets()` — threshold-based duplicate detection
  - `get_ticket_relationships()` — structured parent/child/sibling info

- **kb.py**: Zendesk Help Center search with local caching via `cachetools.ttl_cache`

### Error Handling

- **Custom Exception Hierarchy** (`exceptions.py`):
  - `ZendeskError` — base exception
  - `ZendeskAPIError` — HTTP errors with status codes and response bodies
  - `ZendeskNetworkError` — network I/O failures
  - `ZendeskValidationError` — input validation errors

- **Retry Logic**: `_urlopen_with_retry()` in `base.py` implements exponential backoff for transient failures (429, 5xx) with jitter and Retry-After header support.

## Development Setup

### Prerequisites

- **Python 3.12+** (specified in `.python-version` and `pyproject.toml`)
- **uv** package manager (modern, fast replacement for pip/venv)
- Zendesk account with API credentials

### Quick Start

```bash
# Install uv if not already available
# macOS: brew install uv
# or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install in editable mode
uv venv && uv pip install -e .

# Set up credentials
cp .env.example .env
# Edit .env with your Zendesk subdomain, email, and API key

# Run the MCP server (for use with Claude Desktop or MCP CLI)
uv run zendesk

# Quick smoke test (in another terminal)
uv run python -m mcp_cli --list-prompts
```

### Build & Package

```bash
# Build wheel and sdist for distribution
uv build

# Output appears in dist/
```

## Testing

### Run Tests

```bash
# Run all tests with pytest
uv run pytest

# Run a specific test file
uv run pytest tests/test_server_config.py

# Run a specific test function
uv run pytest tests/test_server_config.py::test_get_settings_returns_expected

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=src/zendesk_mcp_server
```

### Test Patterns

- **Fixture-based setup**: The `reset_client_cache` fixture in test files clears cached client/settings state before each test to ensure isolation.
- **Mocking Zendesk responses**: Tests mock Zendesk API responses rather than making live calls. See `test_ticket_bundle.py` for examples.
- **Environment variable control**: Tests use `monkeypatch.setenv()` and `monkeypatch.delenv()` to control configuration.

### Key Test Files

- `test_server_config.py` — Settings loading and environment variable validation
- `test_incremental_apis.py` — Pagination and incremental data fetching
- `test_case_volume_analytics.py` — Complex analytics aggregation and time-series bucketing
- `test_enhanced_search.py` — Advanced search filtering and fuzzy matching
- `test_batch_search_concurrency_limit.py` — Concurrent search with resource limits
- `test_ticket_bundle.py` — Ticket relationship discovery and thread finding

## Common Development Tasks

### Adding a New Tool

1. **Implement the tool logic** in the appropriate `client/*.py` module (or extend existing module):
   ```python
   # In client/tickets.py or new client/custom.py
   def my_new_operation(self, param: str) -> dict:
       """Perform operation and return results."""
       # Use self.zenpy or self._direct_api_call() as needed
       return {"result": "..."}
   ```

2. **Register the tool** in `server.py`:
   ```python
   # Add tool definition to _register_tools()
   server.add_tool(
       name="my_new_tool",
       description="Human-readable description",
       inputSchema={
           "type": "object",
           "properties": {
               "param": {"type": "string", "description": "Parameter description"}
           },
           "required": ["param"]
       }
   )
   ```

3. **Create a handler** in `handlers/tools.py`:
   ```python
   async def handle_my_new_tool(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
       _require_args(arguments, "param")
       result = await run_client_call(client.my_new_operation, arguments["param"])
       return _json_response(result)
   ```

4. **Register the handler** in `handlers/__init__.py` and update the tool dispatcher in `server.py`.

5. **Add tests** in `tests/test_*.py` following existing patterns.

### Modifying Client Behavior

- **For Zenpy-based operations**: Edit the relevant method in `client/*.py` that uses `self.zenpy` (Zenpy client object).
- **For direct API calls**: Use `self._direct_api_call()` helper or `_urlopen_with_retry()` in `base.py` for retry logic.
- **For caching**: Zendesk Help Center results use `@ttl_cache()` from `cachetools` — adjust TTL in `kb.py` as needed.

### Debugging

```bash
# Enable DEBUG logging by setting PYTHONLOGLEVEL
PYTHONLOGLEVEL=DEBUG uv run zendesk

# Or add logging calls in your code
import logging
logger = logging.getLogger("zendesk-mcp-server")
logger.debug("Detailed info: %s", value)
```

## Code Style & Conventions

- **Language**: Python 3.12+ with type hints for public functions
- **Indentation**: 4 spaces
- **Naming**: `snake_case` for functions/variables, `UPPER_SNAKE_CASE` for constants and prompts
- **Async**: Use `async`/`await` in handlers; delegate blocking calls via `run_client_call()` to avoid stalling the event loop
- **Logging**: Create module-level logger: `logger = logging.getLogger(__name__)` or use `LOGGER_NAME` if defined
- **Errors**: Raise custom exceptions from `exceptions.py`; include context (status code, response body) for API errors

## Dependencies & Version Management

- **Runtime**: `mcp`, `python-dotenv`, `zenpy`, `cachetools`
- **Dev**: `pytest`
- **Lock file**: `uv.lock` — commit this to ensure reproducible builds
- **Adding packages**: `uv pip install <package>` automatically updates `pyproject.toml` and `uv.lock`

## Git & Commits

- **Commit style**: Short, lowercase imperative subjects (e.g., `add batch_search_tickets tool`, `fix 429 retry backoff`)
- **Include context**: Reference issue/PR numbers when relevant
- **Never commit**: `.env` file (it contains credentials); use `.env.example` for templates
- **Environment variables**: Store all Zendesk credentials in `.env` — never hardcode them

## Security Notes

- **API Keys**: Store in `.env`; rotate immediately if exposed
- **Credentials in logs**: Avoid logging full ticket payloads or user data; scrub sensitive fields
- **Input validation**: Use `_require_args()` helper in tool handlers to validate required parameters
- **Network safety**: `_urlopen_with_retry()` handles transient errors safely without infinite loops
