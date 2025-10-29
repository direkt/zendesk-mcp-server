Title: Export API sorting: strip sort params and sort client-side + regression tests

Summary
- Export-backed endpoints in the Zendesk MCP server must not pass sort_by/sort_order to Zendesk’s Search Export API (which does not support ordering). Instead, we strip sort params on request and perform sorting client-side after retrieval.
- This PR adds regression tests that call each affected tool with and without sort parameters to ensure both succeed and produce consistent behavior.

Changes
- Tests: tests/test_export_sorting_regressions.py
  - Verifies search_tickets_export removes sort args from the outbound export call and sorts results locally
  - Exercises wrappers with and without sort: get_search_statistics, search_by_date_range, search_by_integration_source, search_by_tags_advanced, batch_search_tickets
  - Covers search_tickets_enhanced path (with/without sort) which internally uses export and performs client-side post-filtering
  - Adds a basic related-tickets test to ensure the related flow continues to work
- Implementation: No functional code changes required; zendesk_client.search_tickets_export already strips sort params and applies client-side sorting. All wrapper endpoints delegate to this method.

Validation
- To run the test suite locally (uses project’s Python configured env):
  - cd zendesk-mcp-server
  - Ensure dev deps are available, then run: PYTHONPATH=./src pytest -q
  - If pytest is not installed, either:
    - uv run pytest -q
    - or pip install -r dev-requirements.txt (if present) and run pytest -q

Manual sanity (optional)
- Invoke the following methods with and without sort to confirm consistent success:
  - search_tickets_export(query, sort_by="updated_at", sort_order="desc")
  - get_search_statistics(query, sort_by="updated_at")
  - search_by_date_range(start_date=..., end_date=..., sort_by="created_at")
  - search_by_integration_source("email", sort_by="updated_at")
  - search_by_tags_advanced(["bug"], sort_by="priority")
  - batch_search_tickets(["status:open", "priority:high"], sort_by="updated_at")

Notes
- Zendesk’s Search Export API rejects order_by params; this code path now centralizes on search_tickets_export which omits sort on the HTTP request and sorts client-side using stable rules for timestamps, priority, and status fields.
- No Zendesk write operations are performed by these tests.

