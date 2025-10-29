import sys
import types
import io
import json
import urllib.parse
import time as _time
from datetime import datetime
from urllib.error import HTTPError


def inject_fake_zenpy():
    zenpy_mod = types.ModuleType("zenpy")
    zenpy_mod.Zenpy = type("Zenpy", (), {})
    lib_mod = types.ModuleType("zenpy.lib")
    api_objects_mod = types.ModuleType("zenpy.lib.api_objects")
    api_objects_mod.Comment = type("Comment", (), {})
    api_objects_mod.Ticket = type("Ticket", (), {})
    sys.modules.setdefault("zenpy", zenpy_mod)
    sys.modules.setdefault("zenpy.lib", lib_mod)
    sys.modules.setdefault("zenpy.lib.api_objects", api_objects_mod)


class DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def _fake_client_init(self, subdomain, email, token):
    # Minimal init for tests without hitting real Zenpy
    self.client = types.SimpleNamespace()
    self.subdomain = subdomain
    self.base_url = "https://example/api/v2"
    self.auth_header = "Basic xxx"


def test_incremental_tickets_pagination_respects_max_results(monkeypatch):
    inject_fake_zenpy()
    import zendesk_mcp_server.zendesk_client as zc

    urls = []

    def fake_urlopen(req):
        url = getattr(req, "full_url", str(req))
        urls.append(url)
        if "/incremental/tickets.json" in url:
            payload = {
                "tickets": [{"id": 1}, {"id": 2}],
                "next_page": "https://example/api/v2/incremental/tickets.json?start_time=200",
                "end_time": 200,
            }
            return DummyResponse(payload)
        raise AssertionError("Unexpected URL: " + url)

    monkeypatch.setattr(zc.urllib.request, "urlopen", fake_urlopen, raising=False)
    monkeypatch.setattr(zc.ZendeskClient, "__init__", _fake_client_init, raising=False)

    from zendesk_mcp_server.zendesk_client import ZendeskClient

    client = ZendeskClient("s", "e", "t")
    items, has_more, next_start_time = client.incremental_tickets(
        start_time=100, include=["metric_sets", "last_audits"], max_results=1
    )

    # Only one item due to max_results, but server indicated more
    assert len(items) == 1
    assert has_more is True
    assert next_start_time == 200

    # Verify include and start_time are passed through as CSV
    first = urls[0]
    parsed = urllib.parse.urlparse(first)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs.get("start_time") == ["100"]
    assert qs.get("include") == ["metric_sets,last_audits"]


def test_incremental_end_of_stream(monkeypatch):
    inject_fake_zenpy()
    import zendesk_mcp_server.zendesk_client as zc

    def fake_urlopen(req):
        url = getattr(req, "full_url", str(req))
        assert "/incremental/ticket_events.json" in url
        payload = {
            "ticket_events": [],
            "end_of_stream": True,
            "end_time": 100,
        }
        return DummyResponse(payload)

    monkeypatch.setattr(zc.urllib.request, "urlopen", fake_urlopen, raising=False)
    monkeypatch.setattr(zc.ZendeskClient, "__init__", _fake_client_init, raising=False)

    from zendesk_mcp_server.zendesk_client import ZendeskClient

    client = ZendeskClient("s", "e", "t")
    items, has_more, next_start_time = client.incremental_ticket_events(start_time=100)

    assert items == []
    assert has_more is False
    assert next_start_time is None


def test_clock_skew_and_flooring(monkeypatch):
    inject_fake_zenpy()
    import zendesk_mcp_server.zendesk_client as zc

    call_count = {"n": 0}

    def fake_urlopen(req):
        call_count["n"] += 1
        url = getattr(req, "full_url", str(req))
        assert "/incremental/tickets.json" in url
        payload = {
            "tickets": [],
            "end_time": 123,  # equals floored start_time
            "next_page": "https://example/api/v2/incremental/tickets.json?start_time=123",
        }
        return DummyResponse(payload)

    monkeypatch.setattr(zc.urllib.request, "urlopen", fake_urlopen, raising=False)
    monkeypatch.setattr(zc.ZendeskClient, "__init__", _fake_client_init, raising=False)

    from zendesk_mcp_server.zendesk_client import ZendeskClient

    client = ZendeskClient("s", "e", "t")
    dt = datetime.fromtimestamp(123.9)  # fractional seconds should floor to 123
    items, has_more, next_start_time = client.incremental_tickets(start_time=dt, max_results=0)

    assert has_more is True
    assert next_start_time == 124  # bumped by +1 due to clock skew protection


def test_rate_limit_handling_retry_after(monkeypatch):
    inject_fake_zenpy()
    import zendesk_mcp_server.zendesk_client as zc
    import time as time_mod

    calls = {"n": 0}
    sleeps: list[float] = []

    def fake_sleep(secs):
        sleeps.append(secs)

    def fake_urlopen(req):
        url = getattr(req, "full_url", str(req))
        if calls["n"] == 0:
            calls["n"] += 1
            # First call: 429 with Retry-After 2
            raise HTTPError(url, 429, "Too Many Requests", {"Retry-After": "2"}, io.BytesIO(b""))
        calls["n"] += 1
        payload = {"ticket_events": [{"id": "e1"}], "end_of_stream": True}
        return DummyResponse(payload)

    monkeypatch.setattr(time_mod, "sleep", fake_sleep)
    monkeypatch.setattr(zc.urllib.request, "urlopen", fake_urlopen, raising=False)
    monkeypatch.setattr(zc.ZendeskClient, "__init__", _fake_client_init, raising=False)

    from zendesk_mcp_server.zendesk_client import ZendeskClient

    client = ZendeskClient("s", "e", "t")
    items, has_more, next_start_time = client.incremental_ticket_events(start_time=100)

    assert len(items) == 1
    assert has_more is False
    assert next_start_time is None
    assert sleeps and int(sleeps[0]) == 2


def test_cursor_cache_usage(monkeypatch):
    inject_fake_zenpy()
    import zendesk_mcp_server.zendesk_client as zc

    urls = []

    def fake_urlopen(req):
        url = getattr(req, "full_url", str(req))
        urls.append(url)
        payload = {
            "ticket_events": [{"id": "e1"}],
            "next_page": "https://example/api/v2/incremental/ticket_events.json?start_time=200",
            "end_time": 200,
        }
        return DummyResponse(payload)

    class FakeStore:
        def __init__(self):
            self.get_calls = []
            self.set_calls = []

        def get_cursor(self, key):
            self.get_calls.append(key)
            return 150

        def set_cursor(self, key, value):
            self.set_calls.append((key, value))

    monkeypatch.setattr(zc.urllib.request, "urlopen", fake_urlopen, raising=False)
    monkeypatch.setattr(zc.ZendeskClient, "__init__", _fake_client_init, raising=False)

    from zendesk_mcp_server.zendesk_client import ZendeskClient

    client = ZendeskClient("s", "e", "t")
    store = FakeStore()
    client.set_cursor_store(store, label="test")

    items, has_more, next_start_time = client.incremental_ticket_events(start_time=100, max_results=1)

    # start_time should be seeded from cursor (150)
    first = urls[0]
    parsed = urllib.parse.urlparse(first)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs.get("start_time") == ["150"]

    # cursor updated with returned next_start_time
    assert store.set_calls == [("s:incremental_ticket_events:test", 200)]
    assert has_more is True
    assert next_start_time == 200

