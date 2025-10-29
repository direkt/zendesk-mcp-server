# Code Improvement Suggestions

## Critical Issues

### 1. Missing Dependency Declaration
**Issue**: `cachetools` is imported and used but not declared in `pyproject.toml`.

**Location**: `src/zendesk_mcp_server/server.py:7`

**Fix**: Add `cachetools` to dependencies in `pyproject.toml`:
```toml
dependencies = [
    "mcp>=1.1.2",
    "python-dotenv>=1.0.1",
    "zenpy>=2.0.56",
    "cachetools>=5.5.0",  # Missing dependency
]
```

### 2. Large Monolithic Function
**Issue**: `handle_call_tool` function is extremely long (~500 lines) with 40+ if/elif branches.

**Impact**: Hard to maintain, test, and extend. Violates Single Responsibility Principle.

**Recommendation**: Refactor into a dispatch pattern:
- Create a `ToolHandler` class or module
- Use a registry/mapping pattern: `tool_handlers = {"get_ticket": handle_get_ticket, ...}`
- Split each tool handler into its own function
- Example structure:
  ```python
  async def handle_get_ticket(client, arguments):
      # Handle get_ticket logic
      pass
  
  TOOL_HANDLERS = {
      "get_ticket": handle_get_ticket,
      "create_ticket": handle_create_ticket,
      # ... etc
  }
  ```

### 3. Generic Exception Handling
**Issue**: All exceptions are caught generically and wrapped, losing specific error context.

**Locations**: Throughout `zendesk_client.py` (97 raise Exception statements)

**Problem**: 
- Using `raise Exception(f"Failed to...")` loses original exception type
- Makes debugging harder
- No distinction between validation errors vs API errors

**Recommendation**: Create custom exception hierarchy:
```python
class ZendeskError(Exception):
    """Base exception for Zendesk operations"""
    pass

class ZendeskAPIError(ZendeskError):
    """Errors from Zendesk API"""
    def __init__(self, message, status_code=None, response_body=None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)

class ZendeskValidationError(ZendeskError):
    """Validation errors"""
    pass

class ZendeskNotFoundError(ZendeskAPIError):
    """Resource not found (404)"""
    pass
```

## Code Organization

### 4. File Size Issue
**Issue**: `zendesk_client.py` is 2,748 lines - too large for maintainability.

**Recommendation**: Split into modules:
```
zendesk_mcp_server/
  ├── __init__.py
  ├── server.py
  ├── client/
  │   ├── __init__.py
  │   ├── base.py          # ZendeskClient base class
  │   ├── tickets.py        # Ticket-related methods
  │   ├── search.py         # Search-related methods
  │   ├── kb.py             # Knowledge base methods
  │   ├── attachments.py     # Attachment methods
  │   └── exceptions.py     # Custom exceptions
  └── handlers/
      ├── __init__.py
      └── tools.py          # Tool handlers extracted from server.py
```

### 5. Code Duplication
**Issue**: Repetitive argument validation patterns throughout `handle_call_tool`.

**Example**: Pattern repeated 40+ times:
```python
if not arguments:
    raise ValueError("Missing arguments")
ticket_id = arguments.get("ticket_id")
if ticket_id is None:
    raise ValueError("ticket_id is required")
```

**Recommendation**: Create validation decorators/helpers:
```python
def require_args(*required_keys):
    """Decorator to validate required arguments"""
    def decorator(func):
        async def wrapper(name, arguments):
            if not arguments:
                raise ValueError("Missing arguments")
            for key in required_keys:
                if key not in arguments or arguments[key] is None:
                    raise ValueError(f"{key} is required")
            return await func(name, arguments)
        return wrapper
    return decorator
```

## Type Safety

### 6. Incomplete Type Hints
**Issue**: Many functions lack proper type hints, especially in `zendesk_client.py`.

**Recommendation**: 
- Add return type hints to all public methods
- Use `TypedDict` for structured return values
- Add type hints for complex nested dictionaries

**Example**:
```python
from typing import TypedDict

class TicketData(TypedDict):
    id: int
    subject: str
    status: str
    # ... etc

def get_ticket(self, ticket_id: int) -> TicketData:
    ...
```

### 7. Union Types for Optional Parameters
**Issue**: Some methods use `List[str] = None` which should be `List[str] | None` or `Optional[List[str]]`.

**Recommendation**: Standardize on Python 3.12 syntax (`|` operator) consistently.

## Error Handling Improvements

### 8. Inconsistent Error Messages
**Issue**: Error messages vary in format and detail level.

**Examples**:
- `"Failed to get ticket {ticket_id}: {str(e)}"`
- `"Failed to create ticket: {str(e)}"`
- `"ticket_id is required"` vs `"Missing arguments"`

**Recommendation**: Standardize error message format:
```python
class ZendeskError(Exception):
    def __init__(self, operation: str, details: str, original_error: Exception | None = None):
        self.operation = operation
        self.details = details
        self.original_error = original_error
        message = f"Zendesk {operation} failed: {details}"
        if original_error:
            message += f" (Original: {type(original_error).__name__})"
        super().__init__(message)
```

### 9. Missing Error Context
**Issue**: Generic exceptions lose HTTP status codes, response bodies, etc.

**Recommendation**: Preserve error context:
```python
except urllib.error.HTTPError as e:
    error_body = e.read().decode('utf-8') if hasattr(e, 'read') else None
    raise ZendeskAPIError(
        f"HTTP {e.code} - {e.reason}",
        status_code=e.code,
        response_body=error_body
    ) from e
```

## Testing

### 10. Test Coverage Gaps
**Issue**: Large codebase with relatively few test files (9 test files for 4,345 lines of code).

**Observation**: Tests exist for specific features but may not cover all edge cases.

**Recommendation**:
- Add integration tests for the most-used tools
- Add tests for error conditions (429 retries, invalid inputs, etc.)
- Test the tool handler dispatch logic
- Add property-based tests for search query building

### 11. Test Organization
**Recommendation**: Mirror source structure:
```
tests/
  ├── unit/
  │   ├── test_client/
  │   │   ├── test_tickets.py
  │   │   ├── test_search.py
  │   │   └── test_kb.py
  │   └── test_server/
  │       └── test_handlers.py
  └── integration/
      └── test_api.py
```

## Performance

### 12. Event Loop Management Issue
**Issue**: In `batch_search_tickets`, creating a new event loop may conflict with async context.

**Location**: `zendesk_client.py:2702-2709`

**Problem**:
```python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
# ... use loop ...
loop.close()
```

**Recommendation**: Use the existing event loop or make the function async:
```python
async def batch_search_tickets_async(self, ...):
    sem = asyncio.Semaphore(3)
    async def execute_search(query):
        async with sem:
            return await asyncio.to_thread(
                self.search_tickets_export,
                query=query,
                ...
            )
    tasks = [execute_search(query) for query in queries]
    return await asyncio.gather(*tasks)
```

### 13. Caching Strategy
**Issue**: KB caching uses `ttl_cache` decorator but no invalidation strategy.

**Location**: `server.py:1530`

**Recommendation**: Add cache invalidation on errors, configurable TTL, and cache size limits.

## Code Quality

### 14. Magic Numbers and Strings
**Issue**: Hard-coded values scattered throughout:
- `max_attempts: int = 5` in retry logic
- `Semaphore(3)` for concurrency limit
- `limit=100` defaults
- `ttl=3600` for cache

**Recommendation**: Extract to configuration:
```python
class Config:
    MAX_RETRY_ATTEMPTS = 5
    BATCH_SEARCH_CONCURRENCY = 3
    DEFAULT_SEARCH_LIMIT = 100
    KB_CACHE_TTL = 3600
```

### 15. Inconsistent Return Formats
**Issue**: Some methods return dicts, some return strings, some wrap in messages.

**Examples**:
- `create_ticket_comment` returns: `f"Comment created successfully: {result}"`
- `create_ticket` returns: `{"message": "Ticket created successfully", "ticket": created}`
- `get_ticket` returns: `json.dumps(ticket)`

**Recommendation**: Standardize return format - prefer structured data over strings.

### 16. Missing Input Validation
**Issue**: Limited validation of input parameters (e.g., ticket_id could be negative, limits could be too large).

**Recommendation**: Add validation layer:
```python
def validate_ticket_id(ticket_id: int) -> int:
    if ticket_id <= 0:
        raise ValueError(f"ticket_id must be positive, got {ticket_id}")
    return ticket_id

def validate_limit(limit: int, max_limit: int = 1000) -> int:
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    if limit > max_limit:
        raise ValueError(f"limit cannot exceed {max_limit}, got {limit}")
    return limit
```

## Documentation

### 17. Missing Docstrings
**Issue**: Some helper functions lack docstrings.

**Recommendation**: Add docstrings following Google/NumPy style for all public functions.

### 18. Complex Methods Need Documentation
**Issue**: Complex methods like `_incremental_fetch`, `batch_search_tickets` need detailed docs.

**Recommendation**: Add detailed docstrings with:
- Parameter descriptions
- Return value structure
- Example usage
- Error conditions
- Performance considerations

## Dependency Management

### 19. Dependency Versions
**Issue**: Dependency versions are unpinned (e.g., `mcp>=1.1.2`).

**Recommendation**: Pin exact versions in `pyproject.toml` and use `uv.lock` for reproducible builds:
```toml
dependencies = [
    "mcp==1.1.2",  # Pin versions
    "python-dotenv==1.0.1",
    "zenpy==2.0.56",
    "cachetools==5.5.0",
]
```

### 20. Development Dependencies
**Recommendation**: Add common dev tools:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",  # Linting
    "mypy>=1.7.0",  # Type checking
    "black>=23.12.0",  # Formatting (optional)
]
```

## Security

### 21. Credential Handling
**Issue**: Credentials loaded from environment but no validation of format.

**Recommendation**: Add validation:
```python
def validate_subdomain(subdomain: str) -> str:
    if not subdomain or not subdomain.isalnum():
        raise ValueError("ZENDESK_SUBDOMAIN must be alphanumeric")
    return subdomain

def validate_email(email: str) -> str:
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValueError(f"Invalid email format: {email}")
    return email
```

### 22. Logging Sensitive Data
**Issue**: Potential for logging sensitive data in error messages.

**Recommendation**: Scrub sensitive data before logging:
```python
def safe_log_data(data: dict) -> dict:
    """Remove sensitive fields before logging"""
    sensitive_keys = {'token', 'api_key', 'password', 'authorization'}
    safe_data = {k: '***REDACTED***' if k.lower() in sensitive_keys else v 
                 for k, v in data.items()}
    return safe_data
```

## Summary of Priority Actions

### High Priority
1. ✅ Add missing `cachetools` dependency
2. ✅ Refactor `handle_call_tool` into smaller handlers
3. ✅ Create custom exception hierarchy
4. ✅ Fix event loop management in `batch_search_tickets`

### Medium Priority
5. Split `zendesk_client.py` into modules
6. Add comprehensive type hints
7. Standardize error messages and return formats
8. Add input validation layer

### Low Priority
9. Extract magic numbers to config
10. Improve test coverage
11. Add docstrings to all public methods
12. Pin dependency versions

