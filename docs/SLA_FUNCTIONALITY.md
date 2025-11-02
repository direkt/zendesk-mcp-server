# SLA (Service Level Agreement) Functionality

This document describes the SLA policy integration and breach detection functionality in the Zendesk MCP server.

## Overview

The SLA functionality provides comprehensive tools for:
- Retrieving SLA policies configured in Zendesk
- Detecting SLA breaches for individual tickets
- Searching for tickets with SLA breaches
- Identifying tickets at risk of breaching SLA targets

## Available Tools

### 1. `get_sla_policies`

Retrieve all SLA policies configured in your Zendesk instance.

**Parameters:** None

**Returns:**
```json
{
  "sla_policies": [
    {
      "id": 1,
      "title": "Standard SLA",
      "description": "Standard support SLA",
      "policy_metrics": [
        {
          "priority": "normal",
          "metric": "first_reply_time",
          "target": 480,
          "business_hours": true
        }
      ]
    }
  ],
  "count": 1
}
```

**Example Usage:**
```python
result = client.get_sla_policies()
print(f"Found {result['count']} SLA policies")
```

### 2. `get_sla_policy`

Retrieve a specific SLA policy by ID.

**Parameters:**
- `policy_id` (integer, required): The ID of the SLA policy to retrieve

**Returns:** Detailed SLA policy configuration

**Example Usage:**
```python
policy = client.get_sla_policy(policy_id=1)
print(f"Policy: {policy['title']}")
```

### 3. `get_ticket_sla_status`

Get comprehensive SLA status and breach information for a specific ticket.

**Parameters:**
- `ticket_id` (integer, required): The ID of the ticket to check

**Returns:**
```json
{
  "ticket_id": 123,
  "status": "breached",
  "has_breaches": true,
  "breach_count": 2,
  "breaches": [
    {
      "metric": "first_reply_time",
      "instance_id": 1,
      "breached_at": "2024-01-01T11:00:00Z",
      "policy_id": 2,
      "policy_title": "Premium SLA"
    },
    {
      "metric": "resolution_time",
      "instance_id": 3,
      "breached_at": "2024-01-02T10:00:00Z",
      "policy_id": 2,
      "policy_title": "Premium SLA"
    }
  ],
  "at_risk": [],
  "active_slas": [
    {
      "policy_id": 2,
      "policy_title": "Premium SLA",
      "applied_at": "2024-01-01T10:00:00Z"
    }
  ],
  "ticket_status": "open",
  "priority": "urgent",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-02T10:00:00Z"
}
```

**Status Values:**
- `ok`: No breaches, not at risk
- `at_risk`: Approaching breach but not breached yet
- `breached`: One or more SLA targets have been breached

**Example Usage:**
```python
sla_status = client.get_ticket_sla_status(ticket_id=123)
if sla_status['has_breaches']:
    print(f"Ticket {sla_status['ticket_id']} has {sla_status['breach_count']} SLA breaches")
    for breach in sla_status['breaches']:
        print(f"  - {breach['metric']} breached at {breach['breached_at']}")
```

### 4. `search_tickets_with_sla_breaches`

Search for tickets that have breached their SLA targets.

**Parameters:**
- `breach_type` (string, optional): Filter by specific breach type
  - Options: `first_reply_time`, `next_reply_time`, `resolution_time`
- `status` (string, optional): Filter by ticket status (e.g., `open`, `pending`)
- `priority` (string, optional): Filter by ticket priority (e.g., `high`, `urgent`)
- `limit` (integer, optional): Maximum number of tickets to return (default: 100)

**Returns:**
```json
{
  "tickets": [
    {
      "id": 123,
      "subject": "Urgent issue",
      "status": "open",
      "priority": "urgent",
      "sla_status": {
        "status": "breached",
        "has_breaches": true,
        "breaches": [...]
      }
    }
  ],
  "count": 1,
  "breach_type_filter": "first_reply_time",
  "status_filter": "open",
  "priority_filter": "urgent",
  "note": "Tickets with SLA breaches. Each ticket includes sla_status with breach details."
}
```

**Example Usage:**
```python
# Find all open tickets with first reply time breaches
breached = client.search_tickets_with_sla_breaches(
    breach_type='first_reply_time',
    status='open',
    limit=50
)
print(f"Found {breached['count']} tickets with first reply SLA breaches")
```

### 5. `get_tickets_at_risk_of_breach`

Find tickets that are at risk of breaching their SLA but haven't breached yet. Useful for proactive SLA management.

**Parameters:**
- `status` (string, optional): Filter by ticket status (default: open and pending tickets)
- `priority` (string, optional): Filter by ticket priority
- `limit` (integer, optional): Maximum number of tickets to return (default: 50)

**Returns:**
```json
{
  "tickets": [
    {
      "id": 456,
      "subject": "Issue approaching SLA",
      "status": "open",
      "priority": "high",
      "sla_status": {
        "status": "at_risk",
        "has_breaches": false,
        "at_risk": [
          {
            "metric": "first_reply_time",
            "instance_id": 1,
            "status": "approaching_breach",
            "time": "2024-01-01T10:45:00Z"
          }
        ]
      }
    }
  ],
  "count": 1,
  "status_filter": null,
  "priority_filter": "high",
  "note": "Tickets at risk of SLA breach. Each ticket includes sla_status with risk details."
}
```

**Example Usage:**
```python
# Find high priority tickets at risk
at_risk = client.get_tickets_at_risk_of_breach(priority='high', limit=25)
print(f"Found {at_risk['count']} high priority tickets at risk of SLA breach")
for ticket in at_risk['tickets']:
    print(f"  - Ticket #{ticket['id']}: {ticket['subject']}")
```

## Implementation Details

### SLA Breach Detection

The SLA functionality uses the Zendesk Ticket Metric Events API to determine breach status. Metric events track:
- When SLA policies are applied to tickets
- When SLA targets are fulfilled
- When SLA targets are breached
- When SLA timers are paused/resumed

### Breach Types

Three types of SLA breaches are tracked:

1. **First Reply Time**: Time from ticket creation to first public agent response
2. **Next Reply Time**: Time between customer responses and subsequent agent responses
3. **Resolution Time**: Time from ticket creation to ticket resolution

### Performance Considerations

- `search_tickets_with_sla_breaches` and `get_tickets_at_risk_of_breach` fetch tickets and check SLA status individually
- For large result sets, these operations may take time as they need to query metric events for each ticket
- Use appropriate `limit` parameters to control performance
- Consider filtering by status and priority to reduce the search space

## Use Cases

### 1. SLA Compliance Monitoring

Monitor overall SLA compliance across your support organization:

```python
# Get all tickets with SLA breaches
breached = client.search_tickets_with_sla_breaches(limit=1000)
print(f"Total SLA breaches: {breached['count']}")

# Break down by breach type
for breach_type in ['first_reply_time', 'next_reply_time', 'resolution_time']:
    result = client.search_tickets_with_sla_breaches(
        breach_type=breach_type,
        limit=1000
    )
    print(f"{breach_type}: {result['count']} breaches")
```

### 2. Proactive SLA Management

Identify and prioritize tickets at risk of breaching:

```python
# Find urgent tickets at risk
at_risk = client.get_tickets_at_risk_of_breach(priority='urgent')
for ticket in at_risk['tickets']:
    print(f"URGENT: Ticket #{ticket['id']} needs attention")
    # Take action: assign, escalate, etc.
```

### 3. SLA Policy Analysis

Understand which SLA policies are in effect and their targets:

```python
policies = client.get_sla_policies()
for policy in policies['sla_policies']:
    print(f"\nPolicy: {policy['title']}")
    for metric in policy.get('policy_metrics', []):
        print(f"  {metric['metric']}: {metric['target']} minutes")
```

### 4. Ticket-Specific SLA Investigation

Deep dive into SLA status for a specific ticket:

```python
sla_status = client.get_ticket_sla_status(ticket_id=12345)
print(f"Ticket #{sla_status['ticket_id']}")
print(f"Status: {sla_status['status']}")
print(f"Active SLA: {sla_status['active_slas'][0]['policy_title']}")

if sla_status['has_breaches']:
    print("\nBreaches:")
    for breach in sla_status['breaches']:
        print(f"  - {breach['metric']} breached at {breach['breached_at']}")
```

## Testing

Comprehensive tests are available in `tests/test_sla_functionality.py`. Run them with:

```bash
uv run pytest tests/test_sla_functionality.py -v
```

## API References

- [Zendesk SLA Policies API](https://developer.zendesk.com/api-reference/ticketing/business-rules/sla_policies/)
- [Zendesk Ticket Metric Events API](https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_metric_events/)

