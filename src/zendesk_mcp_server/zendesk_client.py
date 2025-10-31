"""
Backward compatibility shim for ZendeskClient.

This module re-exports ZendeskClient from the new modular structure
for backward compatibility. New code should import from zendesk_mcp_server.client instead.
"""

from zendesk_mcp_server.client import ZendeskClient

__all__ = ['ZendeskClient']
