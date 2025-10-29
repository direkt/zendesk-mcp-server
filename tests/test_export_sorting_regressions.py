"""
Regression tests to ensure Export API sort parameters are stripped and sorting is applied client‑side.
Also verifies affected endpoints succeed when called with and without sort options.
"""

import types
from unittest.mock import Mock, patch

import pytest

from zendesk_mcp_server.zendesk_client import ZendeskClient


def _make_ticket(
    id: int,
    subject: str,
    created: str,
    updated: str,
    priority: str = "normal",
    status: str = "open",
    requester_id: int = 1,
    assignee_id: int = 2,
    organization_id: int = 3,
    tags=None,
):
    t = types.SimpleNamespace()
    t.id = id
    t.subject = subject
    t.description = f"desc-{id}"
    t.status = status
    t.priority = priority
    t.type = "incident"
    t.created_at = created
    t.updated_at = updated
    t.requester_id = requester_id
    t.assignee_id = assignee_id
    t.organization_id = organization_id
    t.tags = tags or []
    return t


class TestExportSortingRegressions:
    def setup_method(self):
        self.client = ZendeskClient("sub", "e", "t")
        # Replace zenpy client with a Mock so no network is used
        self.client.client = Mock()

    def test_search_tickets_export_strips_sort_and_sorts_client_side(self):
        # Given three tickets with different updated_at
        tickets = [
            _make_ticket(1, "A", "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"),
            _make_ticket(2, "B", "2024-01-01T00:00:00Z", "2024-01-03T00:00:00Z"),
            _make_ticket(3, "C", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        ]
        self.client.client.search_export.return_value = tickets

        # When we call with sort params (which Export API does not support)
        res_desc = self.client.search_tickets_export(
            query="status:open", sort_by="updated_at", sort_order="desc"
        )
        res_asc = self.client.search_tickets_export(
            query="status:open", sort_by="updated_at", sort_order="asc"
        )

        # Then the underlying zenpy search_export should NOT receive any sort args
        # Only 'type' is forwarded (internally set)
        for call in self.client.client.search_export.call_args_list:
            args, kwargs = call
            assert "order_by" not in kwargs
            assert "sort_by" not in kwargs
            assert "sort_order" not in kwargs
            assert kwargs.get("type") == "ticket"

        # And tickets should be sorted client-side
        assert [t["id"] for t in res_desc["tickets"]] == [2, 1, 3]
        assert [t["id"] for t in res_asc["tickets"]] == [3, 1, 2]

    def test_wrappers_succeed_with_and_without_sort(self):
        # Common stub result
        stub = {
            "tickets": [
                {"id": 1, "status": "open", "priority": "high", "tags": [], "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z"}
            ],
            "count": 1,
        }
        with patch.object(self.client, "search_tickets_export", return_value=stub) as mocked:
            # get_search_statistics
            out1 = self.client.get_search_statistics("status:open", sort_by="updated_at", sort_order="desc")
            assert out1["total_tickets"] == 1
            out1b = self.client.get_search_statistics("status:open")
            assert out1b["total_tickets"] == 1

            # search_by_date_range
            out2 = self.client.search_by_date_range(start_date="2024-01-01", end_date="2024-01-31", sort_by="created_at", sort_order="asc")
            assert out2["count"] == 1
            out2b = self.client.search_by_date_range(start_date="2024-01-01", end_date="2024-01-31")
            assert out2b["count"] == 1

            # search_by_integration_source
            out3 = self.client.search_by_integration_source("email", sort_by="updated_at")
            assert out3["count"] == 1
            out3b = self.client.search_by_integration_source("email")
            assert out3b["count"] == 1

            # search_by_tags_advanced
            out4 = self.client.search_by_tags_advanced(include_tags=["bug"], sort_by="priority", sort_order="desc")
            assert out4["count"] == 1
            out4b = self.client.search_by_tags_advanced(include_tags=["bug"])
            assert out4b["count"] == 1

            # batch_search_tickets
            out5 = self.client.batch_search_tickets(["status:open", "priority:high"], sort_by="updated_at")
            assert out5["queries_executed"] == 2
            out5b = self.client.batch_search_tickets(["status:open", "priority:high"])
            assert out5b["queries_executed"] == 2

            # Ensure wrapper calls still routed through export method
            assert mocked.call_count >= 6


    def test_search_tickets_enhanced_with_and_without_sort(self):
        stub = {
            "tickets": [
                {"id": 2, "subject": "alpha beta", "description": "foo", "updated_at": "2024-01-02T00:00:00Z"},
                {"id": 1, "subject": "beta gamma", "description": "bar", "updated_at": "2024-01-01T00:00:00Z"},
            ],
            "count": 2,
        }
        with patch.object(self.client, "search_tickets_export", return_value=stub) as mocked:
            out1 = self.client.search_tickets_enhanced(
                query="subject:beta",
                regex_pattern="beta",
                sort_by="updated_at",
                sort_order="desc",
                limit=10,
            )
            assert out1["count"] == 2 or "tickets" in out1

            out2 = self.client.search_tickets_enhanced(
                query="subject:beta",
                regex_pattern="beta",
                limit=10,
            )
            assert out2 is not None
            assert mocked.call_count >= 2

    def test_find_related_tickets_no_sort_and_returns_results(self):
        # Mock the reference ticket
        with patch.object(self.client, "get_ticket", return_value={
            "id": 137515,
            "subject": "GandivaException: Not a valid day in monthOfYear",
            "requester_id": 42,
            "organization_id": 99,
        }):
            # Each export call returns a ticket different from reference
            with patch.object(self.client, "search_tickets_export", return_value={
                "tickets": [
                    {
                        "id": 2001,
                        "subject": "GandivaException during monthOfYear",
                        "updated_at": "2024-03-03T00:00:00Z",
                        "created_at": "2024-03-01T00:00:00Z",
                        "requester_id": 42,
                        "organization_id": 99,
                    }
                ],
                "count": 1,
            }):
                out = self.client.find_related_tickets(137515, limit=5)
                assert out["count"] >= 1
                assert any(t["id"] == 2001 for t in out["related_tickets"])
