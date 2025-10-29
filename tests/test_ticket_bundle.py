import sys
import types
import io
import json
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


def make_response(payload: dict):
    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return DummyResponse()


def minimal_client_init(self, subdomain, email, token):
    # Avoid real zenpy init; set minimal fields used by client
    self.client = types.SimpleNamespace()
    self.base_url = "https://example/api/v2"
    self.auth_header = "Basic xxx"


class UrlRouter:
    """A simple URL router to simulate Zendesk API endpoints for tests."""
    def __init__(self):
        self.handlers = {}

    def route(self, contains: str, handler):
        self.handlers[contains] = handler

    def __call__(self, req):
        url = getattr(req, "full_url", str(req))
        for key, handler in self.handlers.items():
            if key in url:
                return handler(url)
        # Default empty
        return make_response({})


def test_get_ticket_bundle_happy_path(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient
    monkeypatch.setattr(ZendeskClient, "__init__", minimal_client_init, raising=False)

    # Return a simple ticket via existing get_ticket (we'll patch method directly)
    ticket = {
        'id': 123,
        'subject': 'Test',
        'description': 'Desc',
        'status': 'open',
        'priority': 'high',
        'created_at': '2024-01-01T00:00:00Z',
        'updated_at': '2024-01-02T00:00:00Z',
        'requester_id': 11,
        'assignee_id': 22,
        'organization_id': 33,
    }

    def fake_get_ticket(self, ticket_id):
        assert ticket_id == 123
        return ticket

    monkeypatch.setattr(ZendeskClient, "get_ticket", fake_get_ticket, raising=False)

    # Wire up URL router for comments, audits, users, organizations
    import zendesk_mcp_server.zendesk_client as zc
    router = UrlRouter()

    # Comments: 2 comments, no pagination
    comments_payload = {
        'comments': [
            {
                'id': 1,
                'author_id': 11,
                'body': 'First',
                'html_body': '<p>First</p>',
                'public': True,
                'created_at': '2024-01-01T01:00:00Z',
                'attachments': [{'id': 900, 'file_name': 'a.txt', 'content_type': 'text/plain', 'content_url': 'u', 'size': 1}],
            },
            {
                'id': 2,
                'author_id': 22,
                'body': 'Second',
                'html_body': '<p>Second</p>',
                'public': False,
                'created_at': '2024-01-01T02:00:00Z',
                'attachments': [],
            },
        ],
        'next_page': None,
    }
    router.route('/comments.json', lambda url: make_response(comments_payload))

    # Audits: one audit with two change events
    audits_payload = {
        'audits': [
            {
                'id': 700,
                'author_id': 99,
                'created_at': '2024-01-01T00:30:00Z',
                'events': [
                    {'type': 'Change', 'field': 'status', 'previous_value': 'new', 'value': 'open'},
                    {'type': 'Change', 'field': 'assignee_id', 'previous_value': None, 'value': 22},
                ]
            }
        ],
        'next_page': None,
    }
    router.route('/audits.json', lambda url: make_response(audits_payload))

    # Users/Orgs
    router.route('/users/11.json', lambda url: make_response({'user': {'id': 11, 'name': 'Alice'}}))
    router.route('/users/22.json', lambda url: make_response({'user': {'id': 22, 'name': 'Bob'}}))
    router.route('/organizations/33.json', lambda url: make_response({'organization': {'id': 33, 'name': 'Acme'}}))

    # Patch urlopen
    monkeypatch.setattr(zc.urllib.request, "urlopen", router, raising=False)

    client = ZendeskClient("s", "e", "t")
    bundle = client.get_ticket_bundle(123)

    assert bundle['ticket']['id'] == 123
    assert bundle['requester']['id'] == 11
    assert bundle['assignee']['id'] == 22
    assert bundle['organization']['id'] == 33
    assert bundle['comments_count'] == 2
    assert bundle['audits_count'] == 1
    # Timeline: 2 change events + 2 comments
    assert len(bundle['timeline']) == 4
    assert bundle['timeline'][0]['event_type'] in ('status_change', 'assignment')
    assert bundle['timeline'][-1]['event_type'] == 'comment'


def test_get_ticket_bundle_pagination(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient
    monkeypatch.setattr(ZendeskClient, "__init__", minimal_client_init, raising=False)

    monkeypatch.setattr(ZendeskClient, "get_ticket", lambda self, tid: {'id': tid, 'updated_at': '2024-01-01T00:00:00Z'}, raising=False)

    import zendesk_mcp_server.zendesk_client as zc
    router = UrlRouter()

    # Comments pagination: 3 items, limit=2
    first_comments = {
        'comments': [
            {'id': 1, 'author_id': 1, 'body': 'c1', 'html_body': '', 'public': True, 'created_at': '2024-01-01T00:00:01Z', 'attachments': []},
            {'id': 2, 'author_id': 1, 'body': 'c2', 'html_body': '', 'public': True, 'created_at': '2024-01-01T00:00:02Z', 'attachments': []},
        ],
        'next_page': 'https://example/api/v2/tickets/555/comments.json?page=2'
    }
    second_comments = {
        'comments': [
            {'id': 3, 'author_id': 1, 'body': 'c3', 'html_body': '', 'public': True, 'created_at': '2024-01-01T00:00:03Z', 'attachments': []},
        ],
        'next_page': None
    }
    def comments_handler(url):
        if 'page=2' in url:
            return make_response(second_comments)
        return make_response(first_comments)
    router.route('/comments.json', comments_handler)

    # Audits pagination: 2 items, limit=1
    first_audits = {
        'audits': [
            {'id': 10, 'author_id': 2, 'created_at': '2024-01-01T00:00:10Z', 'events': [{'type': 'Change', 'field': 'status', 'previous_value': 'new', 'value': 'open'}]}
        ],
        'next_page': 'https://example/api/v2/tickets/555/audits.json?page=2'
    }
    second_audits = {
        'audits': [
            {'id': 11, 'author_id': 2, 'created_at': '2024-01-01T00:00:11Z', 'events': []}
        ],
        'next_page': None
    }
    def audits_handler(url):
        if 'page=2' in url:
            return make_response(second_audits)
        return make_response(first_audits)
    router.route('/audits.json', audits_handler)

    # No user/org lookups needed for this test
    monkeypatch.setattr(zc.urllib.request, "urlopen", router, raising=False)

    client = ZendeskClient("s", "e", "t")
    bundle = client.get_ticket_bundle(555, comment_limit=2, audit_limit=1)

    assert bundle['comments_count'] == 2
    assert bundle['comments_has_more'] is True
    assert bundle['audits_count'] == 1
    assert bundle['audits_has_more'] is True


def test_get_ticket_bundle_missing_context(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient
    monkeypatch.setattr(ZendeskClient, "__init__", minimal_client_init, raising=False)

    # Ticket with only requester
    fake_ticket = {'id': 999, 'requester_id': 11, 'assignee_id': None, 'organization_id': None, 'updated_at': '2024-01-01T00:00:00Z'}
    monkeypatch.setattr(ZendeskClient, "get_ticket", lambda self, tid: fake_ticket, raising=False)

    import zendesk_mcp_server.zendesk_client as zc
    router = UrlRouter()

    router.route('/comments.json', lambda url: make_response({'comments': [], 'next_page': None}))
    router.route('/audits.json', lambda url: make_response({'audits': [], 'next_page': None}))
    router.route('/users/11.json', lambda url: make_response({'user': {'id': 11, 'name': 'Alice'}}))
    monkeypatch.setattr(zc.urllib.request, "urlopen", router, raising=False)

    client = ZendeskClient("s", "e", "t")
    bundle = client.get_ticket_bundle(999)

    assert bundle['requester']['id'] == 11
    assert bundle['assignee'] is None
    assert bundle['organization'] is None


def test_get_ticket_bundle_api_failures(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient
    monkeypatch.setattr(ZendeskClient, "__init__", minimal_client_init, raising=False)

    monkeypatch.setattr(ZendeskClient, "get_ticket", lambda self, tid: {'id': tid, 'requester_id': 999, 'organization_id': 888, 'updated_at': '2024-01-01T00:00:00Z'}, raising=False)

    import zendesk_mcp_server.zendesk_client as zc

    def failing_urlopen(req):
        url = getattr(req, "full_url", str(req))
        if '/users/999.json' in url or '/organizations/888.json' in url:
            # Simulate 404
            raise HTTPError(url, 404, "Not Found", None, io.BytesIO(b""))
        if '/comments.json' in url:
            return make_response({'comments': [], 'next_page': None})
        if '/audits.json' in url:
            return make_response({'audits': [], 'next_page': None})
        return make_response({})

    monkeypatch.setattr(zc.urllib.request, "urlopen", failing_urlopen, raising=False)

    client = ZendeskClient("s", "e", "t")
    bundle = client.get_ticket_bundle(42)

    assert bundle['requester'] is None
    assert bundle['organization'] is None


def test_get_ticket_bundle_empty_ticket(monkeypatch):
    inject_fake_zenpy()
    from zendesk_mcp_server.zendesk_client import ZendeskClient
    monkeypatch.setattr(ZendeskClient, "__init__", minimal_client_init, raising=False)

    monkeypatch.setattr(ZendeskClient, "get_ticket", lambda self, tid: {'id': tid, 'updated_at': '2024-01-01T00:00:00Z'}, raising=False)

    import zendesk_mcp_server.zendesk_client as zc
    router = UrlRouter()
    router.route('/comments.json', lambda url: make_response({'comments': [], 'next_page': None}))
    router.route('/audits.json', lambda url: make_response({'audits': [], 'next_page': None}))
    monkeypatch.setattr(zc.urllib.request, "urlopen", router, raising=False)

    client = ZendeskClient("s", "e", "t")
    bundle = client.get_ticket_bundle(1)

    assert bundle['comments_count'] == 0
    assert bundle['audits_count'] == 0
    assert bundle['timeline'] == []

