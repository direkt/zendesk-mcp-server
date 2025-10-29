import sys, types

# Stub zenpy and its submodules to avoid external dependency during local smoke test
class DummyComment: ...
class DummyTicket: ...
class DummyZenpy:
    def __init__(self, **kwargs):
        self._search_export = None
    def search_export(self, query, **kwargs):
        # Delegate to injected function if present
        if self._search_export:
            return self._search_export(query, **kwargs)
        return []

zenpy_pkg = types.SimpleNamespace(Zenpy=DummyZenpy)
lib_pkg = types.SimpleNamespace(api_objects=types.SimpleNamespace(Comment=DummyComment, Ticket=DummyTicket))
zenpy_pkg.lib = lib_pkg
sys.modules['zenpy'] = zenpy_pkg
sys.modules['zenpy.lib'] = zenpy_pkg.lib
sys.modules['zenpy.lib.api_objects'] = zenpy_pkg.lib.api_objects

# Now import our client module directly by path to avoid package __init__ side-effects
import importlib.util, pathlib
module_path = pathlib.Path(__file__).resolve().parents[1] / 'src' / 'zendesk_mcp_server' / 'zendesk_client.py'
spec = importlib.util.spec_from_file_location('smoke_zendesk_client', str(module_path))
zendesk_client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zendesk_client)
ZendeskClient = zendesk_client.ZendeskClient

# Prepare fake tickets (namespaces with attributes), returned by search_export
Tickets = [
    types.SimpleNamespace(id=1, subject='A', description='d1', status='open', priority='normal', type='incident',
                          created_at='2024-01-01T00:00:00Z', updated_at='2024-01-02T00:00:00Z', requester_id=1, assignee_id=2, organization_id=3, tags=[]),
    types.SimpleNamespace(id=2, subject='B', description='d2', status='open', priority='high', type='incident',
                          created_at='2024-01-01T00:00:00Z', updated_at='2024-01-03T00:00:00Z', requester_id=1, assignee_id=2, organization_id=3, tags=[]),
    types.SimpleNamespace(id=3, subject='C', description='d3', status='open', priority='low', type='incident',
                          created_at='2024-01-01T00:00:00Z', updated_at='2024-01-01T00:00:00Z', requester_id=1, assignee_id=2, organization_id=3, tags=[]),
]

client = ZendeskClient('sub', 'e', 't')
# Inject our fake export function so we can introspect kwargs passed
calls = []

def fake_export(query, **kwargs):
    calls.append((query, kwargs))
    return Tickets

client.client._search_export = fake_export
client.client.search_export = fake_export

# Call with and without sort; ensure sort isn't passed downstream and results are sorted client-side
res_desc = client.search_tickets_export(query='status:open', sort_by='updated_at', sort_order='desc')
res_asc = client.search_tickets_export(query='status:open', sort_by='updated_at', sort_order='asc')

assert all('order_by' not in kw and 'sort_by' not in kw and 'sort_order' not in kw for _, kw in calls), f"Sort leaked to export: {calls}"
assert [t['id'] for t in res_desc['tickets']] == [2, 1, 3], 'DESC sort failed'
assert [t['id'] for t in res_asc['tickets']] == [3, 1, 2], 'ASC sort failed'

print('OK: client-side sorting works and sort params are not sent to Export API')

