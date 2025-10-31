import sys
import types
import io
import json
import time as _time
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


def test_get_tickets_retries_on_429(monkeypatch):
    inject_fake_zenpy()

    # Patch urllib.request.urlopen used by the module
    import zendesk_mcp_server.zendesk_client as zc

    call_state = {"n": 0}

    def fake_urlopen(req, max_attempts=5):
        call_state["n"] += 1
        url = getattr(req, "full_url", str(req))
        if "tickets.json" in url and call_state["n"] < 3:
            # First two attempts simulate 429
            raise HTTPError(url, 429, "Too Many Requests", None, io.BytesIO(b""))

        class DummyResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                payload = {"tickets": [{"id": 1, "subject": "foo"}], "next_page": None, "previous_page": None}
                return json.dumps(payload).encode("utf-8")

        return DummyResponse()

    # Avoid actual sleeping in retry loop
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen, raising=False)

    from zendesk_mcp_server.zendesk_client import ZendeskClient

    def fake_init(self, subdomain, email, token):
        self.client = types.SimpleNamespace()
        self.base_url = "https://example"
        self.auth_header = "Basic xxx"

    monkeypatch.setattr(ZendeskClient, "__init__", fake_init, raising=False)

    client = ZendeskClient("s", "e", "t")
    res = client.get_tickets(page=1, per_page=25)

    # Confirm we retried and eventually succeeded
    assert call_state["n"] >= 3
    assert res["count"] == 1

