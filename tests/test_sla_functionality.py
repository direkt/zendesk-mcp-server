"""Tests for SLA functionality."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from zendesk_mcp_server.client import ZendeskClient


@pytest.fixture
def mock_zendesk_client():
    """Create a mock Zendesk client for testing."""
    with patch('zendesk_mcp_server.client.base.Zenpy'):
        client = ZendeskClient(
            subdomain='test',
            email='test@example.com',
            token='test_token'
        )
        return client


class TestSLAPolicies:
    """Test SLA policy retrieval."""
    
    def test_get_sla_policies(self, mock_zendesk_client):
        """Test fetching all SLA policies."""
        mock_policies = [
            {
                'id': 1,
                'title': 'Standard SLA',
                'description': 'Standard support SLA',
                'policy_metrics': [
                    {
                        'priority': 'normal',
                        'metric': 'first_reply_time',
                        'target': 480,  # 8 hours in minutes
                        'business_hours': True
                    }
                ]
            },
            {
                'id': 2,
                'title': 'Premium SLA',
                'description': 'Premium support SLA',
                'policy_metrics': [
                    {
                        'priority': 'urgent',
                        'metric': 'first_reply_time',
                        'target': 60,  # 1 hour
                        'business_hours': False
                    }
                ]
            }
        ]
        
        mock_zendesk_client._get_json = Mock(return_value={'sla_policies': mock_policies})
        
        result = mock_zendesk_client.get_sla_policies()
        
        assert result['count'] == 2
        assert len(result['sla_policies']) == 2
        assert result['sla_policies'][0]['title'] == 'Standard SLA'
        assert result['sla_policies'][1]['title'] == 'Premium SLA'
        mock_zendesk_client._get_json.assert_called_once_with('/slas/policies.json')
    
    def test_get_sla_policy(self, mock_zendesk_client):
        """Test fetching a specific SLA policy."""
        mock_policy = {
            'id': 1,
            'title': 'Standard SLA',
            'description': 'Standard support SLA',
            'policy_metrics': [
                {
                    'priority': 'normal',
                    'metric': 'first_reply_time',
                    'target': 480,
                    'business_hours': True
                }
            ]
        }
        
        mock_zendesk_client._get_json = Mock(return_value={'sla_policy': mock_policy})
        
        result = mock_zendesk_client.get_sla_policy(1)
        
        assert result['id'] == 1
        assert result['title'] == 'Standard SLA'
        mock_zendesk_client._get_json.assert_called_once_with('/slas/policies/1.json')


class TestSLABreachDetection:
    """Test SLA breach detection functionality."""
    
    def test_get_ticket_sla_status_no_breach(self, mock_zendesk_client):
        """Test SLA status for a ticket with no breaches."""
        mock_ticket = {
            'id': 123,
            'subject': 'Test ticket',
            'status': 'open',
            'priority': 'normal',
            'created_at': '2024-01-01T10:00:00Z',
            'updated_at': '2024-01-01T11:00:00Z'
        }
        
        mock_metric_events = [
            {
                'type': 'apply_sla',
                'time': '2024-01-01T10:00:00Z',
                'sla_policy': {
                    'id': 1,
                    'title': 'Standard SLA'
                }
            },
            {
                'type': 'fulfill',
                'metric': 'first_reply_time',
                'instance_id': 1,
                'time': '2024-01-01T10:30:00Z'
            }
        ]
        
        mock_zendesk_client._get_json = Mock(return_value={'ticket': mock_ticket})
        mock_zendesk_client.get_ticket_metric_events = Mock(
            return_value={'metric_events': mock_metric_events}
        )
        
        result = mock_zendesk_client.get_ticket_sla_status(123)
        
        assert result['ticket_id'] == 123
        assert result['status'] == 'ok'
        assert result['has_breaches'] is False
        assert result['breach_count'] == 0
        assert len(result['active_slas']) == 1
        assert result['active_slas'][0]['policy_title'] == 'Standard SLA'
    
    def test_get_ticket_sla_status_with_breach(self, mock_zendesk_client):
        """Test SLA status for a ticket with breaches."""
        mock_ticket = {
            'id': 456,
            'subject': 'Urgent issue',
            'status': 'open',
            'priority': 'urgent',
            'created_at': '2024-01-01T10:00:00Z',
            'updated_at': '2024-01-01T14:00:00Z'
        }
        
        mock_metric_events = [
            {
                'type': 'apply_sla',
                'time': '2024-01-01T10:00:00Z',
                'sla_policy': {
                    'id': 2,
                    'title': 'Premium SLA'
                }
            },
            {
                'type': 'breach',
                'metric': 'first_reply_time',
                'instance_id': 1,
                'time': '2024-01-01T11:00:00Z'
            }
        ]
        
        mock_zendesk_client._get_json = Mock(return_value={'ticket': mock_ticket})
        mock_zendesk_client.get_ticket_metric_events = Mock(
            return_value={'metric_events': mock_metric_events}
        )
        
        result = mock_zendesk_client.get_ticket_sla_status(456)
        
        assert result['ticket_id'] == 456
        assert result['status'] == 'breached'
        assert result['has_breaches'] is True
        assert result['breach_count'] == 1
        assert len(result['breaches']) == 1
        assert result['breaches'][0]['metric'] == 'first_reply_time'
        assert result['breaches'][0]['policy_title'] == 'Premium SLA'
    
    def test_get_ticket_sla_status_multiple_breaches(self, mock_zendesk_client):
        """Test SLA status for a ticket with multiple breaches."""
        mock_ticket = {
            'id': 789,
            'subject': 'Critical issue',
            'status': 'pending',
            'priority': 'urgent',
            'created_at': '2024-01-01T10:00:00Z',
            'updated_at': '2024-01-02T10:00:00Z'
        }
        
        mock_metric_events = [
            {
                'type': 'apply_sla',
                'time': '2024-01-01T10:00:00Z',
                'sla_policy': {
                    'id': 2,
                    'title': 'Premium SLA'
                }
            },
            {
                'type': 'breach',
                'metric': 'first_reply_time',
                'instance_id': 1,
                'time': '2024-01-01T11:00:00Z'
            },
            {
                'type': 'breach',
                'metric': 'next_reply_time',
                'instance_id': 2,
                'time': '2024-01-01T15:00:00Z'
            },
            {
                'type': 'breach',
                'metric': 'resolution_time',
                'instance_id': 3,
                'time': '2024-01-02T10:00:00Z'
            }
        ]
        
        mock_zendesk_client._get_json = Mock(return_value={'ticket': mock_ticket})
        mock_zendesk_client.get_ticket_metric_events = Mock(
            return_value={'metric_events': mock_metric_events}
        )
        
        result = mock_zendesk_client.get_ticket_sla_status(789)
        
        assert result['ticket_id'] == 789
        assert result['status'] == 'breached'
        assert result['has_breaches'] is True
        assert result['breach_count'] == 3
        assert len(result['breaches']) == 3
        
        # Verify all breach types are captured
        breach_metrics = [b['metric'] for b in result['breaches']]
        assert 'first_reply_time' in breach_metrics
        assert 'next_reply_time' in breach_metrics
        assert 'resolution_time' in breach_metrics


class TestWeeklyCSAT:
    """Test weekly CSAT retrieval functionality."""

    def test_get_tickets_with_csat_this_week(self, mock_zendesk_client):
        """Test retrieving tickets with CSAT scores from this week."""
        mock_tickets = [
            {
                'id': 1,
                'subject': 'Ticket 1',
                'status': 'solved',
                'priority': 'normal',
                'created_at': '2024-01-15T10:00:00Z',
                'updated_at': '2024-01-16T14:30:00Z',
                'satisfaction_rating': {
                    'score': 'good',
                    'comment': 'Great support!'
                }
            },
            {
                'id': 2,
                'subject': 'Ticket 2',
                'status': 'solved',
                'priority': 'high',
                'created_at': '2024-01-14T10:00:00Z',
                'updated_at': '2024-01-16T15:00:00Z',
                'satisfaction_rating': {
                    'score': 'offered',
                    'comment': None
                }
            },
        ]

        mock_zendesk_client.search_tickets_export = Mock(
            return_value={'tickets': mock_tickets}
        )

        result = mock_zendesk_client.get_tickets_with_csat_this_week()

        assert result['count'] == 2
        assert len(result['tickets']) == 2
        assert result['summary']['total_with_csat'] == 2
        assert result['summary']['total_with_comments'] == 1
        assert 'week_start' in result
        assert 'week_end' in result


class TestRecentCSAT:
    """Test recent CSAT retrieval functionality."""

    def test_get_recent_tickets_with_csat(self, mock_zendesk_client):
        """Test retrieving recent tickets with CSAT scores."""
        mock_tickets = [
            {
                'id': 1,
                'subject': 'Ticket 1',
                'status': 'solved',
                'priority': 'normal',
                'satisfaction_rating': {
                    'score': 'good',
                    'comment': 'Great support!'
                }
            },
            {
                'id': 2,
                'subject': 'Ticket 2',
                'status': 'solved',
                'priority': 'normal',
                'satisfaction_rating': {
                    'score': 'offered',
                    'comment': None
                }
            },
            {
                'id': 3,
                'subject': 'Ticket 3',
                'status': 'solved',
                'priority': 'high',
                'satisfaction_rating': {
                    'score': 'good',
                    'comment': 'Very helpful team'
                }
            },
        ]

        mock_zendesk_client.search_tickets_export = Mock(
            return_value={'tickets': mock_tickets}
        )

        result = mock_zendesk_client.get_recent_tickets_with_csat(limit=20)

        assert result['count'] == 3
        assert len(result['tickets']) == 3
        assert result['summary']['total_with_csat'] == 3
        assert result['summary']['total_with_comments'] == 2

        # Check score distribution
        assert result['summary']['score_distribution']['good'] == 2
        assert result['summary']['score_distribution']['offered'] == 1

        # Check first ticket has comment
        assert result['tickets'][0]['comment'] == 'Great support!'
        assert result['tickets'][1]['comment'] is None


class TestSLASearch:
    """Test SLA breach search functionality."""

    def test_search_tickets_with_sla_breaches(self, mock_zendesk_client):
        """Test searching for tickets with SLA breaches."""
        mock_tickets = [
            {'id': 1, 'subject': 'Ticket 1', 'status': 'open'},
            {'id': 2, 'subject': 'Ticket 2', 'status': 'pending'},
        ]
        
        # Mock search results
        mock_zendesk_client.search_tickets_export = Mock(
            return_value={'tickets': mock_tickets}
        )
        
        # Mock SLA status - first ticket has breach, second doesn't
        def mock_sla_status(ticket_id):
            if ticket_id == 1:
                return {
                    'ticket_id': 1,
                    'status': 'breached',
                    'has_breaches': True,
                    'breaches': [{'metric': 'first_reply_time'}]
                }
            else:
                return {
                    'ticket_id': 2,
                    'status': 'ok',
                    'has_breaches': False,
                    'breaches': []
                }
        
        mock_zendesk_client.get_ticket_sla_status = Mock(side_effect=mock_sla_status)
        
        result = mock_zendesk_client.search_tickets_with_sla_breaches(
            status='open',
            limit=10
        )
        
        assert result['count'] == 1
        assert len(result['tickets']) == 1
        assert result['tickets'][0]['id'] == 1
        assert result['tickets'][0]['sla_status']['has_breaches'] is True
    
    def test_get_tickets_at_risk_of_breach(self, mock_zendesk_client):
        """Test finding tickets at risk of SLA breach."""
        mock_tickets = [
            {'id': 1, 'subject': 'Ticket 1', 'status': 'open'},
            {'id': 2, 'subject': 'Ticket 2', 'status': 'open'},
            {'id': 3, 'subject': 'Ticket 3', 'status': 'open'},
        ]
        
        mock_zendesk_client.search_tickets_export = Mock(
            return_value={'tickets': mock_tickets}
        )
        
        # Mock SLA status - ticket 2 is at risk
        def mock_sla_status(ticket_id):
            if ticket_id == 2:
                return {
                    'ticket_id': 2,
                    'status': 'at_risk',
                    'has_breaches': False,
                    'at_risk': [{'metric': 'first_reply_time'}]
                }
            else:
                return {
                    'ticket_id': ticket_id,
                    'status': 'ok',
                    'has_breaches': False,
                    'at_risk': []
                }
        
        mock_zendesk_client.get_ticket_sla_status = Mock(side_effect=mock_sla_status)
        
        result = mock_zendesk_client.get_tickets_at_risk_of_breach(limit=10)
        
        assert result['count'] == 1
        assert len(result['tickets']) == 1
        assert result['tickets'][0]['id'] == 2
        assert result['tickets'][0]['sla_status']['status'] == 'at_risk'

