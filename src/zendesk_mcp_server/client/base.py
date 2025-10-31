"""Base ZendeskClient class and core utilities."""
from typing import Any, Dict, Optional
import json
import urllib.request
import urllib.parse
import urllib.error
import base64
from datetime import datetime

from zenpy import Zenpy
from zendesk_mcp_server.exceptions import (
    ZendeskError,
    ZendeskAPIError,
    ZendeskNetworkError,
    ZendeskValidationError,
)


# Helper: urllib request with 429 retry/backoff
# Exponential backoff with jitter for HTTP 429 responses
# Kept module-agnostic so it can be reused across direct API calls
def _urlopen_with_retry(req, max_attempts: int = 5):
    import time
    import random
    import urllib.request
    import urllib.error

    last_err = None
    for attempt in range(max_attempts):
        try:
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            code = getattr(e, "code", None)
            # Retry on 429 Too Many Requests or transient 5xx errors
            if code == 429 or (isinstance(code, int) and 500 <= code < 600):
                if attempt < max_attempts - 1:
                    # Honor Retry-After header if present
                    delay = None
                    headers = getattr(e, "headers", None) or getattr(e, "hdrs", None)
                    if headers:
                        try:
                            retry_after = headers.get("Retry-After") or headers.get("retry-after")
                            if retry_after:
                                retry_after = retry_after.strip()
                                if retry_after.isdigit():
                                    delay = int(retry_after)
                        except Exception:
                            delay = None
                    if delay is None:
                        delay = min(2 ** attempt + random.random(), 30)
                    time.sleep(delay)
                    last_err = e
                    continue
            # Re-raise other HTTP errors as API errors
            error_body = e.read().decode() if hasattr(e, 'fp') and e.fp else "No response body"
            raise ZendeskAPIError(
                f"HTTP Error: {e.code} - {e.reason}",
                status_code=e.code,
                response_body=error_body,
            )
        except urllib.error.URLError as e:
            # Treat network errors as retryable
            if attempt < max_attempts - 1:
                delay = min(2 ** attempt + random.random(), 30)
                time.sleep(delay)
                last_err = e
                continue
            raise ZendeskNetworkError(f"Network Error: {str(e)}")
    # If we exhausted retries, re-raise the last error
    if last_err:
        raise ZendeskError(f"Max retries exceeded: {str(last_err)}")
    raise ZendeskError("Unknown error during URL open.")


class ZendeskClientBase:
    """Base class for ZendeskClient with core initialization and helpers."""
    
    def __init__(self, subdomain: str, email: str, token: str):
        """
        Initialize the Zendesk client using zenpy lib and direct API.
        """
        self.client = Zenpy(
            subdomain=subdomain,
            email=email,
            token=token
        )

        # For direct API calls
        self.subdomain = subdomain
        self.email = email
        self.token = token
        self.base_url = f"https://{subdomain}.zendesk.com/api/v2"
        # Create basic auth header
        credentials = f"{email}/token:{token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode('ascii')
        self.auth_header = f"Basic {encoded_credentials}"
        # Optional cursor store for incremental APIs
        self.cursor_store = None
        self.cursor_label = None

    def set_cursor_store(self, store: Any, label: str | None = None) -> None:
        """Inject an optional cursor store used by incremental API wrappers.

        The store must implement get_cursor(key) -> int | None and set_cursor(key, value: int) -> None.
        An optional label can be provided to namespace cursors per timebox/use-case.
        """
        self.cursor_store = store
        self.cursor_label = label

    def _cursor_key(self, endpoint: str) -> str:
        label_part = f":{self.cursor_label}" if getattr(self, "cursor_label", None) else ""
        return f"{self.subdomain}:{endpoint}{label_part}"

    # Internal helper to GET a path and return parsed JSON
    def _get_json(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}{('?' + query) if query else ''}"
        req = urllib.request.Request(url)
        req.add_header('Authorization', self.auth_header)
        req.add_header('Content-Type', 'application/json')
        with _urlopen_with_retry(req) as response:
            return json.loads(response.read().decode('utf-8'))

    # Internal helper to GET a fully-qualified URL (e.g., next_page) and return parsed JSON
    def _get_json_url(self, url: str) -> Dict[str, Any]:
        req = urllib.request.Request(url)
        req.add_header('Authorization', self.auth_header)
        req.add_header('Content-Type', 'application/json')
        with _urlopen_with_retry(req) as response:
            return json.loads(response.read().decode('utf-8'))
    
    # Incremental API generic fetcher
    def _incremental_fetch(
        self,
        path: str,
        items_key: str,
        start_time: int | datetime,
        include_csv: str | None = None,
        max_results: int | None = None,
        cursor_endpoint_key: str | None = None,
    ) -> tuple[list[dict], bool, int | None]:
        """Fetch items from an incremental endpoint with robust paging and backoff.

        Returns (items, has_more, next_start_time).
        """
        # Coerce start_time
        if isinstance(start_time, datetime):
            start_ts = int(start_time.timestamp())
        elif isinstance(start_time, int):
            start_ts = int(start_time)
        else:
            raise ZendeskValidationError("start_time must be int or datetime")
        if start_ts < 0:
            raise ZendeskValidationError("start_time must be >= 0")

        # Seed from cursor store if present and more recent
        effective_ts = start_ts
        if getattr(self, "cursor_store", None) and cursor_endpoint_key:
            try:
                key = self._cursor_key(cursor_endpoint_key)
                last = self.cursor_store.get_cursor(key)
                if isinstance(last, int) and last > effective_ts:
                    effective_ts = last
            except Exception:
                # best-effort; ignore cursor errors
                pass

        params: Dict[str, Any] = {"start_time": effective_ts}
        if include_csv:
            params["include"] = include_csv

        items: list[dict] = []
        has_more: bool = False
        next_start_time: Optional[int] = None
        next_url: Optional[str] = None
        seen_pages: set[str] = set()

        def fetch(url: Optional[str]) -> Dict[str, Any]:
            if url:
                return self._get_json_url(url)
            return self._get_json(path, params)

        while True:
            data = fetch(next_url)
            page_items = list(data.get(items_key) or [])

            # Aggregate with respect to max_results
            if max_results is not None and max_results >= 0:
                remaining = max_results - len(items)
                if remaining <= 0:
                    # We already reached the cap; determine has_more below and break
                    pass
                else:
                    items.extend(page_items[:remaining])
            else:
                items.extend(page_items)

            raw_next = data.get("next_page") or data.get("after_url")
            eos = data.get("end_of_stream")
            end_time_val = data.get("end_time")

            # Determine candidate next_start_time
            candidate: Optional[int] = None
            if isinstance(end_time_val, int):
                candidate = end_time_val
            elif raw_next:
                try:
                    parsed = urllib.parse.urlparse(raw_next)
                    qs = urllib.parse.parse_qs(parsed.query)
                    st_vals = qs.get("start_time") or qs.get("start_time[]") or qs.get("start_time[]")
                    if st_vals and len(st_vals) > 0 and st_vals[0].isdigit():
                        candidate = int(st_vals[0])
                except Exception:
                    candidate = None

            if candidate is not None:
                next_start_time = candidate

            # Decide has_more as per contract (considering server signal)
            has_more = bool(raw_next) and (eos is False or eos is None)

            # Stop conditions
            if max_results is not None and len(items) >= max_results:
                # We reached the cap; signal has_more if server showed more
                break
            if not raw_next or eos is True:
                break
            if raw_next in seen_pages:
                # loop safety
                break

            seen_pages.add(raw_next)
            next_url = raw_next

        # Clock skew/loop safety adjustment for next_start_time
        if next_start_time is not None and next_start_time <= effective_ts:
            next_start_time = effective_ts + 1

        # If no more, do not suggest a next_start_time
        final_next = next_start_time if has_more else None

        # Persist cursor if store provided
        if getattr(self, "cursor_store", None) and cursor_endpoint_key and isinstance(final_next, int):
            try:
                key = self._cursor_key(cursor_endpoint_key)
                self.cursor_store.set_cursor(key, final_next)
            except Exception:
                pass

        return items, has_more, final_next

    def _get_user(self, user_id: int) -> Dict[str, Any] | None:
        try:
            data = self._get_json(f"/users/{user_id}.json")
            return data.get('user') or data
        except Exception:
            return None

    def _get_organization(self, org_id: int) -> Dict[str, Any] | None:
        try:
            data = self._get_json(f"/organizations/{org_id}.json")
            return data.get('organization') or data
        except Exception:
            return None

