import sys
import types


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


def make_ticket(i):
    T = type("Ticket", (), {})
    t = T()
    t.id = i
    t.subject = f"Subject {i}"
    t.description = f"Desc {i}"
    t.status = "open"
    t.priority = "normal"
    t.type = None
    t.created_at = "2025-01-01T00:00:00Z"
    t.updated_at = "2025-01-01T00:00:00Z"
    t.requester_id = 1
    t.assignee_id = 2
    t.organization_id = 3
    t.tags = ["a", "b"]
    return t


def test_search_tickets_export_has_more_flag(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient
    from types import SimpleNamespace

    def fake_init(self, subdomain, email, token):
        # Stub zenpy client's search_export to yield 10 tickets
        def iterator():
            return iter([make_ticket(i) for i in range(10)])
        self.client = SimpleNamespace(search_export=lambda query, **kwargs: iterator())
        self.base_url = "https://example"
        self.auth_header = "Basic xxx"

    monkeypatch.setattr(ZendeskClient, "__init__", fake_init, raising=False)

    client = ZendeskClient("s", "e", "t")
    res = client.search_tickets_export(query="status:open", max_results=5)
    assert res["count"] == 5
    assert res["has_more"] is True

    # No max_results -> all (10) collected; has_more should be False
    res2 = client.search_tickets_export(query="status:open")
    assert res2["count"] == 10
    assert res2.get("has_more") in (False, None)

