import sys
import types
import threading
import time as _time


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


def test_batch_search_limited_to_three_concurrent(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient

    # Prevent any accidental real sleeping from slowing the test if present
    monkeypatch.setattr(_time, "sleep", lambda s: None)

    # Stub init to avoid real Zenpy
    def fake_init(self, subdomain, email, token):
        self.client = types.SimpleNamespace()
        self.base_url = "https://example"
        self.auth_header = "Basic xxx"

    monkeypatch.setattr(ZendeskClient, "__init__", fake_init, raising=False)

    current = 0
    max_concurrency = 0
    lock = threading.Lock()

    def fake_export(self, query, **kwargs):
        nonlocal current, max_concurrency
        with lock:
            current += 1
            if current > max_concurrency:
                max_concurrency = current
        try:
            _time.sleep(0.05)
            return {"tickets": [{"id": query}], "execution_time_ms": 10}
        finally:
            with lock:
                current -= 1

    monkeypatch.setattr(ZendeskClient, "search_tickets_export", fake_export, raising=False)

    import asyncio
    client = ZendeskClient("s", "e", "t")
    queries = [f"q{i}" for i in range(7)]
    res = asyncio.run(client.batch_search_tickets(queries=queries, deduplicate=False, sort_by=None, sort_order=None, limit_per_query=1))

    # Ensure the batch completed and returned results for each query
    assert res["queries_executed"] == len(queries)

    # The max observed concurrency should not exceed 3 due to the semaphore
    assert max_concurrency <= 3

