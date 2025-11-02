#!/usr/bin/env python3
"""
Test the get_recent_tickets_with_csat MCP tool.

Usage:
    uv run python scripts/test_csat_tool.py
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


def test_csat_tool():
    """Test the get_recent_tickets_with_csat tool."""
    
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
    print("Testing get_recent_tickets_with_csat MCP Tool")
    print("=" * 80)
    print()
    
    # Test with default limit (20)
    print("Fetching recent tickets with CSAT scores (limit=20)...")
    result = client.get_recent_tickets_with_csat(limit=20)
    
    print(json.dumps(result, indent=2))
    print()
    
    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total tickets with CSAT: {result['count']}")
    print(f"Total with comments: {result['summary']['total_with_comments']}")
    print(f"Score distribution: {result['summary']['score_distribution']}")
    print()


if __name__ == '__main__':
    try:
        test_csat_tool()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

