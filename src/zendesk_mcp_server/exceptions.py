"""Custom exception hierarchy for Zendesk operations."""


class ZendeskError(Exception):
    """Base exception for Zendesk operations."""
    pass


class ZendeskAPIError(ZendeskError):
    """Errors from Zendesk API."""
    
    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        """
        Initialize Zendesk API error.
        
        Args:
            message: Error message
            status_code: HTTP status code if available
            response_body: Response body if available
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class ZendeskNotFoundError(ZendeskAPIError):
    """Resource not found (404)."""
    pass


class ZendeskRateLimitError(ZendeskAPIError):
    """Rate limit exceeded (429)."""
    pass


class ZendeskValidationError(ZendeskError):
    """Validation/input errors."""
    pass


class ZendeskNetworkError(ZendeskError):
    """Network/connection errors."""
    pass

