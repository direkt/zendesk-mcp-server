"""Tests for case volume analytics aggregation."""

from unittest.mock import Mock, patch

import pytest

from zendesk_mcp_server.zendesk_client import ZendeskClient
from zendesk_mcp_server.exceptions import ZendeskValidationError


class TestCaseVolumeAnalytics:
    """Test cases for get_case_volume_analytics."""

    def setup_method(self):
        self.client = ZendeskClient("test", "test", "test")
        self.client.client = Mock()

    def test_get_case_volume_analytics_basic(self):
        """Aggregate weekly, monthly, and technician counts within a range."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "status": "open",
                "priority": "normal",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 2,
                "created_at": "2024-01-08T09:00:00Z",
                "assignee_id": 101,
                "status": "open",
                "priority": "high",
                "type": "problem",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 3,
                "created_at": "2024-02-10T12:00:00Z",
                "assignee_id": None,
                "status": "solved",
                "priority": "normal",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-02-15",
            )

        mock_export.assert_called_once_with(
            query="created>=2024-01-01 created<=2024-02-15",
            sort_by="created_at",
            sort_order="asc",
            max_results=10000,
        )

        assert result["totals"]["tickets"] == 3
        assert result["totals"]["assigned_tickets"] == 2
        assert result["totals"]["unassigned_tickets"] == 1
        assert result["range"]["start_date"] == "2024-01-01"
        assert result["range"]["end_date"] == "2024-02-15"
        assert result["range"]["time_bucket"] == "weekly"

        weekly = {item["week"]: item["count"] for item in result["weekly_counts"]}
        assert weekly["2024-W01"] == 1
        assert weekly["2024-W02"] == 1
        assert weekly["2024-W06"] == 1
        # Zero-filled weeks exist
        assert weekly["2024-W03"] == 0

        monthly = {item["month"]: item["count"] for item in result["monthly_counts"]}
        assert monthly == {"2024-01": 2, "2024-02": 1}

        technician = {
            entry["display_key"]: {w["week"]: w["count"] for w in entry["weeks"]}
            for entry in result["technician_weekly_counts"]
        }
        assert technician["101"]["2024-W01"] == 1
        assert technician["101"]["2024-W02"] == 1
        assert technician["unassigned"]["2024-W06"] == 1

        status_breakdown = result["totals"]["status_breakdown"]
        assert status_breakdown["open"] == 2
        assert status_breakdown["solved"] == 1

    def test_get_case_volume_analytics_with_metrics(self):
        """Test analytics with time-based metrics."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "updated_at": "2024-01-02T11:00:00Z",
                "assignee_id": 101,
                "status": "solved",
                "priority": "normal",
                "type": "question",
                "via": {"channel": "email"},
                "metrics": {
                    "reply_time_in_seconds": 3600,
                    "first_resolution_time_in_seconds": 7200,
                    "full_resolution_time_in_seconds": 7200,
                },
                "satisfaction_rating": {"score": 5},
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
                include_metrics=["response_times", "resolution_times", "channels", "satisfaction"],
            )

        assert "response_time_metrics" in result
        assert "resolution_time_metrics" in result
        assert "channel_breakdown" in result
        assert "satisfaction_metrics" in result
        
        assert result["response_time_metrics"]["reply_time"]["avg"] == 3600.0
        assert result["channel_breakdown"]["email"] == 1
        assert result["satisfaction_metrics"]["average_score"] == 5.0

    def test_get_case_volume_analytics_with_filters(self):
        """Test analytics with status and priority filters."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "status": "open",
                "priority": "high",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 2,
                "created_at": "2024-01-08T09:00:00Z",
                "assignee_id": 101,
                "status": "solved",
                "priority": "normal",
                "type": "problem",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
                filter_by_status=["open"],
                filter_by_priority=["high"],
            )

        assert result["totals"]["tickets"] == 1
        assert result["totals"]["status_breakdown"]["open"] == 1

    def test_get_case_volume_analytics_with_grouping(self):
        """Test analytics with grouping by channel and priority."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "status": "open",
                "priority": "high",
                "type": "question",
                "via": {"channel": "email"},
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
                group_by=["channel", "priority"],
            )

        assert "grouped_breakdowns" in result
        assert "channel" in result["grouped_breakdowns"]
        assert "priority" in result["grouped_breakdowns"]

    def test_get_case_volume_analytics_time_buckets(self):
        """Test different time bucket options."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "status": "open",
                "priority": "normal",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            # Test daily bucket
            result_daily = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-03",
                time_bucket="daily",
            )
            assert result_daily["range"]["time_bucket"] == "daily"
            assert "time_series" in result_daily

            # Test monthly bucket
            result_monthly = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-02-15",
                time_bucket="monthly",
            )
            assert result_monthly["range"]["time_bucket"] == "monthly"

    def test_get_case_volume_analytics_with_tags(self):
        """Test analytics with tag extraction and filtering."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "status": "open",
                "priority": "normal",
                "type": "question",
                "tags": ["bug", "urgent"],
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 2,
                "created_at": "2024-01-08T09:00:00Z",
                "assignee_id": 101,
                "status": "open",
                "priority": "high",
                "type": "problem",
                "tags": ["bug"],
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
            )

            assert "tag_breakdown" in result
            assert result["tag_breakdown"]["bug"] == 2
            assert result["tag_breakdown"]["urgent"] == 1
            assert "tag_weekly_counts" in result
            assert len(result["tag_weekly_counts"]) > 0

            # Test filtering by tags
            result_filtered = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
                filter_by_tags=["urgent"],
            )
            assert result_filtered["totals"]["tickets"] == 1

            # Test grouping by tags
            result_grouped = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
                group_by=["tags"],
            )
            assert "grouped_breakdowns" in result_grouped
            assert "tags" in result_grouped["grouped_breakdowns"]

    def test_get_case_volume_analytics_invalid_range(self):
        """Reject end dates earlier than start dates."""

        with pytest.raises(ZendeskValidationError):
            self.client.get_case_volume_analytics(
                start_date="2024-03-01",
                end_date="2024-02-01",
            )

    def test_get_case_volume_analytics_with_requesters(self):
        """Test analytics with requester tracking."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "requester_id": 201,
                "status": "open",
                "priority": "normal",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 2,
                "created_at": "2024-01-08T09:00:00Z",
                "assignee_id": 101,
                "requester_id": 201,
                "status": "open",
                "priority": "high",
                "type": "problem",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 3,
                "created_at": "2024-01-10T12:00:00Z",
                "assignee_id": None,
                "requester_id": 202,
                "status": "solved",
                "priority": "normal",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
            )

        assert "requester_weekly_counts" in result
        assert "requester_breakdown" in result
        
        requester_breakdown = result["requester_breakdown"]
        assert requester_breakdown["201"] == 2
        assert requester_breakdown["202"] == 1
        
        # Check weekly counts structure
        requester_weekly = {entry["requester_id"]: entry for entry in result["requester_weekly_counts"]}
        assert 201 in requester_weekly
        assert requester_weekly[201]["total"] == 2
        assert 202 in requester_weekly
        assert requester_weekly[202]["total"] == 1

    def test_get_case_volume_analytics_with_organizations(self):
        """Test analytics with organization tracking."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "requester_id": 201,
                "organization_id": 301,
                "status": "open",
                "priority": "normal",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 2,
                "created_at": "2024-01-08T09:00:00Z",
                "assignee_id": 101,
                "requester_id": 202,
                "organization_id": 301,
                "status": "open",
                "priority": "high",
                "type": "problem",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 3,
                "created_at": "2024-01-10T12:00:00Z",
                "assignee_id": None,
                "requester_id": 203,
                "organization_id": 302,
                "status": "solved",
                "priority": "normal",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
            )

        assert "organization_weekly_counts" in result
        assert "organization_breakdown" in result
        
        org_breakdown = result["organization_breakdown"]
        assert org_breakdown["301"] == 2
        assert org_breakdown["302"] == 1
        
        # Check weekly counts structure
        org_weekly = {entry["organization_id"]: entry for entry in result["organization_weekly_counts"]}
        assert 301 in org_weekly
        assert org_weekly[301]["total"] == 2
        assert 302 in org_weekly
        assert org_weekly[302]["total"] == 1

    def test_get_case_volume_analytics_with_custom_fields(self):
        """Test analytics with custom field tracking."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "requester_id": 201,
                "status": "open",
                "priority": "normal",
                "type": "question",
                "custom_fields": [
                    {"id": 12345, "value": "feature_request"},
                    {"id": 67890, "value": "high_priority"},
                ],
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 2,
                "created_at": "2024-01-08T09:00:00Z",
                "assignee_id": 101,
                "requester_id": 202,
                "status": "open",
                "priority": "high",
                "type": "problem",
                "custom_fields": [
                    {"id": 12345, "value": "bug"},
                    {"id": 67890, "value": "high_priority"},
                ],
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
            {
                "id": 3,
                "created_at": "2024-01-10T12:00:00Z",
                "assignee_id": None,
                "requester_id": 203,
                "status": "solved",
                "priority": "normal",
                "type": "question",
                "custom_fields": [
                    {"id": 12345, "value": "feature_request"},
                ],
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
            )

        assert "custom_field_breakdown" in result
        assert "custom_field_weekly_counts" in result
        
        cf_breakdown = result["custom_field_breakdown"]
        assert "12345" in cf_breakdown
        assert cf_breakdown["12345"]["feature_request"] == 2
        assert cf_breakdown["12345"]["bug"] == 1
        assert "67890" in cf_breakdown
        assert cf_breakdown["67890"]["high_priority"] == 2
        
        # Check weekly counts structure
        cf_weekly = result["custom_field_weekly_counts"]
        assert len(cf_weekly) > 0
        # Find entries for field 12345
        field_12345_entries = [e for e in cf_weekly if e["field_id"] == "12345"]
        assert len(field_12345_entries) >= 2  # Should have entries for both values

    def test_get_case_volume_analytics_group_by_requester_organization(self):
        """Test grouping by requester and organization."""

        tickets = [
            {
                "id": 1,
                "created_at": "2024-01-02T10:00:00Z",
                "assignee_id": 101,
                "requester_id": 201,
                "organization_id": 301,
                "status": "open",
                "priority": "normal",
                "type": "question",
                "via": None,
                "metrics": {},
                "satisfaction_rating": None,
            },
        ]

        with patch.object(self.client, "search_tickets_export") as mock_export:
            mock_export.return_value = {"tickets": tickets, "count": len(tickets)}

            result = self.client.get_case_volume_analytics(
                start_date="2024-01-01",
                end_date="2024-01-15",
                group_by=["requester", "organization"],
            )

        assert "grouped_breakdowns" in result
        assert "requester" in result["grouped_breakdowns"]
        assert "organization" in result["grouped_breakdowns"]
        assert result["grouped_breakdowns"]["requester"]["201"] == 1
        assert result["grouped_breakdowns"]["organization"]["301"] == 1


if __name__ == "__main__":
    pytest.main([__file__])

