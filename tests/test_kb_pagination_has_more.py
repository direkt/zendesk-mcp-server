import sys
import types


def inject_fake_zenpy():
    # Minimal fake zenpy modules to satisfy imports
    zenpy_mod = types.ModuleType("zenpy")
    zenpy_mod.Zenpy = type("Zenpy", (), {})
    lib_mod = types.ModuleType("zenpy.lib")
    api_objects_mod = types.ModuleType("zenpy.lib.api_objects")
    api_objects_mod.Comment = type("Comment", (), {})
    api_objects_mod.Ticket = type("Ticket", (), {})
    sys.modules.setdefault("zenpy", zenpy_mod)
    sys.modules.setdefault("zenpy.lib", lib_mod)
    sys.modules.setdefault("zenpy.lib.api_objects", api_objects_mod)


class DummyArticles:
    def __init__(self, iterator_factory):
        self._factory = iterator_factory

    def search(self, **kwargs):
        return self._factory()

    def __call__(self, **kwargs):
        return self._factory()


def make_article(i):
    # Simple ticket-like object with required attributes
    A = type("Article", (), {})
    a = A()
    a.id = i
    a.title = f"Title {i}"
    a.body = "body" * 10
    a.html_url = f"http://example/{i}"
    a.section_id = 1
    a.label_names = ["a", "b"]
    a.updated_at = "2025-01-01T00:00:00Z"
    a.author_id = 123
    a.vote_sum = 0
    return a


def test_search_articles_respects_per_page_and_has_more(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient
    from types import SimpleNamespace

    def iterator_factory_many():
        return iter([make_article(i) for i in range(10)])

    def fake_init(self, subdomain, email, token):
        self.client = SimpleNamespace(help_center=SimpleNamespace(articles=DummyArticles(iterator_factory_many)))
        self.base_url = "https://example"
        self.auth_header = "Basic xxx"

    monkeypatch.setattr(ZendeskClient, "__init__", fake_init, raising=False)

    client = ZendeskClient("s", "e", "t")
    res = client.search_articles(query="foo", per_page=5)
    assert res["count"] == 5
    assert res["has_more"] is True
    assert len(res["articles"]) == 5


def test_search_articles_by_labels_respects_per_page_and_has_more(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient
    from types import SimpleNamespace

    def iterator_factory_few():
        return iter([make_article(i) for i in range(2)])

    def fake_init(self, subdomain, email, token):
        self.client = SimpleNamespace(help_center=SimpleNamespace(articles=DummyArticles(iterator_factory_few)))
        self.base_url = "https://example"
        self.auth_header = "Basic xxx"

    monkeypatch.setattr(ZendeskClient, "__init__", fake_init, raising=False)

    client = ZendeskClient("s", "e", "t")
    res = client.search_articles_by_labels(label_names=["a"], per_page=5)
    assert res["count"] == 2
    assert res["has_more"] is False
    assert len(res["articles"]) == 2

