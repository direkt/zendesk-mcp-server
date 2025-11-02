#!/usr/bin/env python3
"""
Test the get_tickets_with_csat_this_week MCP tool.

Usage:
    uv run python scripts/test_weekly_csat.py
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zendesk_mcp_server.client import ZendeskClient


def test_weekly_csat_tool():
    """Test the get_tickets_with_csat_this_week tool."""
    
    # Get settings from environment
    subdomain = os.getenv("ZENDESK_SUBDOMAIN")
    email = os.getenv("ZENDESK_EMAIL")
    api_key = os.getenv("ZENDESK_API_KEY")
    
    if not all([subdomain, email, api_key]):
        print("Error: Missing required environment variables.")
        print("Please set ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, and ZENDESK_API_KEY")
        sys.exit(1)
    
    # Initialize client
    client = ZendeskClient(
        subdomain=subdomain,
        email=email,
        token=api_key
    )
    
    print("=" * 80)
    print("Testing get_tickets_with_csat_this_week MCP Tool")
    print("=" * 80)
    print()
    
    # Test the tool
    print("Fetching tickets with CSAT scores from this week...")
    result = client.get_tickets_with_csat_this_week()
    
    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Week: {result['week_start']} to {result['week_end']}")
    print(f"Total tickets with CSAT this week: {result['count']}")
    print(f"Total with comments: {result['summary']['total_with_comments']}")
    print(f"Score distribution: {result['summary']['score_distribution']}")
    print()
    
    if result['count'] > 0:
        print("=" * 80)
        print("TICKETS WITH CSAT THIS WEEK")
        print("=" * 80)
        print()
        
        for idx, ticket in enumerate(result['tickets'], 1):
            print(f"[{idx}] Ticket #{ticket['ticket_id']}")
            print(f"    Subject: {ticket['subject']}")
            print(f"    Status: {ticket['status']} | Priority: {ticket['priority']}")
            print(f"    CSAT Score: {ticket['score']}")
            if ticket['comment']:
                print(f"    Comment: {ticket['comment']}")
            else:
                print(f"    Comment: (none)")
            print(f"    Updated: {ticket['updated_at']}")
            print()
    else:
        print("No tickets with CSAT scores found this week.")
        print()
    
    # Print full JSON for reference
    print("=" * 80)
    print("FULL JSON RESPONSE")
    print("=" * 80)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        test_weekly_csat_tool()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

