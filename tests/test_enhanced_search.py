"""
Tests for enhanced search functionality in the Zendesk MCP server.
"""

import pytest
from unittest.mock import Mock, patch
from zendesk_mcp_server.zendesk_client import ZendeskClient


class TestEnhancedSearch:
    """Test cases for enhanced search features."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = ZendeskClient("test", "test", "test")
        self.client.client = Mock()

    def test_get_ticket_fields(self):
        """Test get_ticket_fields method."""
        # Mock field data
        mock_field = Mock()
        mock_field.id = 12345
        mock_field.title = "Test Field"
        mock_field.type = "text"
        mock_field.description = "Test description"
        mock_field.required = False
        mock_field.collapsed_for_agents = False
        mock_field.active = True
        mock_field.position = 1
        mock_field.created_at = "2024-01-01T00:00:00Z"
        mock_field.updated_at = "2024-01-01T00:00:00Z"
        mock_field.custom_field_id = None  # System field
        
        self.client.client.ticket_fields.return_value = [mock_field]
        
        result = self.client.get_ticket_fields()
        
        assert result['count'] == 1
        assert result['custom_count'] == 0
        assert result['system_count'] == 1
        assert len(result['fields']) == 1
        assert result['fields'][0]['id'] == 12345
        assert result['fields'][0]['title'] == "Test Field"

    def test_search_by_integration_source(self):
        """Test search_by_integration_source method."""
        with patch.object(self.client, 'search_tickets_export') as mock_search:
            mock_search.return_value = {
                'tickets': [{'id': 1, 'subject': 'Test ticket'}],
                'count': 1
            }
            
            result = self.client.search_by_integration_source("email")
            
            mock_search.assert_called_once_with(
                query="via.channel:email",
                sort_by=None,
                sort_order=None,
                max_results=100
            )
            assert result['count'] == 1

    def test_apply_regex_filter(self):
        """Test _apply_regex_filter method."""
        tickets = [
            {'id': 1, 'subject': 'Test Ticket', 'description': 'This is a test'},
            {'id': 2, 'subject': 'Another Ticket', 'description': 'No match here'}
        ]
        
        result = self.client._apply_regex_filter(tickets, r'\bTest\b')
        
        assert len(result) == 1
        assert result[0]['id'] == 1
        assert 'regex_match_field' in result[0]
        assert 'regex_match' in result[0]

    def test_apply_fuzzy_filter(self):
        """Test _apply_fuzzy_filter method."""
        tickets = [
            {'id': 1, 'subject': 'Login Issue', 'description': 'User cannot login'},
            {'id': 2, 'subject': 'Payment Problem', 'description': 'Payment failed'}
        ]
        
        result = self.client._apply_fuzzy_filter(tickets, "login", threshold=0.5)
        
        assert len(result) == 1
        assert result[0]['id'] == 1
        assert 'fuzzy_match_score' in result[0]
        assert 'fuzzy_match_field' in result[0]

    def test_apply_proximity_filter(self):
        """Test _apply_proximity_filter method."""
        tickets = [
            {'id': 1, 'subject': 'Login password reset issue', 'description': 'User needs help'},
            {'id': 2, 'subject': 'Payment issue', 'description': 'Login failed'}
        ]
        
        result = self.client._apply_proximity_filter(tickets, ["login", "password"], max_distance=3)
        
        assert len(result) == 1
        assert result[0]['id'] == 1
        assert 'proximity_match_field' in result[0]
        assert 'proximity_distance' in result[0]

    def test_search_tickets_enhanced(self):
        """Test search_tickets_enhanced method."""
        with patch.object(self.client, 'search_tickets_export') as mock_search:
            mock_search.return_value = {
                'tickets': [
                    {'id': 1, 'subject': 'Test Ticket', 'description': 'This is a test'},
                    {'id': 2, 'subject': 'Another Ticket', 'description': 'No match here'}
                ],
                'count': 2
            }
            
            result = self.client.search_tickets_enhanced(
                query="status:open",
                regex_pattern=r'\bTest\b'
            )
            
            assert result['count'] == 1
            assert 'enhancements_applied' in result
            assert 'regex_pattern' in result['enhancements_applied']

    def test_build_search_query(self):
        """Test build_search_query method."""
        result = self.client.build_search_query(
            status="open",
            priority="high",
            tags=["bug", "urgent"],
            tags_logic="AND"
        )
        
        assert "status:open" in result['query']
        assert "priority:high" in result['query']
        assert "tags:bug" in result['query']
        assert "tags:urgent" in result['query']
        assert len(result['examples']) > 0

    def test_get_search_statistics(self):
        """Test get_search_statistics method."""
        with patch.object(self.client, 'search_tickets_export') as mock_search:
            mock_search.return_value = {
                'tickets': [
                    {
                        'id': 1,
                        'status': 'solved',
                        'priority': 'high',
                        'assignee_id': 123,
                        'requester_id': 456,
                        'organization_id': 789,
                        'tags': ['bug', 'urgent'],
                        'created_at': '2024-01-01T00:00:00Z',
                        'updated_at': '2024-01-02T00:00:00Z'
                    }
                ],
                'count': 1
            }
            
            result = self.client.get_search_statistics("status:solved")
            
            assert result['total_tickets'] == 1
            assert 'statistics' in result
            assert 'by_status' in result['statistics']
            assert 'summary' in result

    def test_search_by_date_range_relative(self):
        """Test search_by_date_range with relative periods."""
        with patch.object(self.client, 'search_tickets_export') as mock_search:
            mock_search.return_value = {'tickets': [], 'count': 0}
            
            result = self.client.search_by_date_range(
                range_type="relative",
                relative_period="last_7_days"
            )
            
            mock_search.assert_called_once()
            call_args = mock_search.call_args
            assert "created>=" in call_args[1]['query']

    def test_search_by_tags_advanced(self):
        """Test search_by_tags_advanced method."""
        with patch.object(self.client, 'search_tickets_export') as mock_search:
            mock_search.return_value = {'tickets': [], 'count': 0}
            
            result = self.client.search_by_tags_advanced(
                include_tags=["bug", "urgent"],
                exclude_tags=["spam"],
                tag_logic="AND"
            )
            
            mock_search.assert_called_once()
            call_args = mock_search.call_args
            query = call_args[1]['query']
            assert "tags:bug" in query
            assert "tags:urgent" in query
            assert "-tags:spam" in query

    def test_batch_search_tickets(self):
        """Test batch_search_tickets method."""
        with patch.object(self.client, 'search_tickets_export') as mock_search:
            mock_search.return_value = {'tickets': [{'id': 1}], 'count': 1}
            
            result = self.client.batch_search_tickets(
                queries=["status:open", "priority:high"],
                deduplicate=True
            )
            
            assert result['queries_executed'] == 2
            assert result['deduplication_applied'] == True
            assert 'query_results' in result


if __name__ == "__main__":
    pytest.main([__file__])
