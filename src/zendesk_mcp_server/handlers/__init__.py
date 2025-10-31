"""Tool handler registry."""
from zendesk_mcp_server.handlers import tools

# Registry mapping tool names to handler functions
TOOL_HANDLERS = {
    "get_ticket": tools.handle_get_ticket,
    "create_ticket": tools.handle_create_ticket,
    "get_tickets": tools.handle_get_tickets,
    "get_ticket_comments": tools.handle_get_ticket_comments,
    "create_ticket_comment": tools.handle_create_ticket_comment,
    "update_ticket": tools.handle_update_ticket,
    "search_tickets": tools.handle_search_tickets,
    "search_tickets_export": tools.handle_search_tickets_export,
    "upload_attachment": tools.handle_upload_attachment,
    "get_ticket_attachments": tools.handle_get_ticket_attachments,
    "download_attachment": tools.handle_download_attachment,
    "search_kb_articles": tools.handle_search_kb_articles,
    "get_kb_article": tools.handle_get_kb_article,
    "search_kb_by_labels": tools.handle_search_kb_by_labels,
    "list_kb_sections": tools.handle_list_kb_sections,
    "find_related_tickets": tools.handle_find_related_tickets,
    "find_duplicate_tickets": tools.handle_find_duplicate_tickets,
    "find_ticket_thread": tools.handle_find_ticket_thread,
    "get_ticket_relationships": tools.handle_get_ticket_relationships,
    "get_ticket_fields": tools.handle_get_ticket_fields,
    "search_by_source": tools.handle_search_by_source,
    "search_tickets_enhanced": tools.handle_search_tickets_enhanced,
    "build_search_query": tools.handle_build_search_query,
    "get_search_statistics": tools.handle_get_search_statistics,
    "search_by_date_range": tools.handle_search_by_date_range,
    "search_by_tags_advanced": tools.handle_search_by_tags_advanced,
    "batch_search_tickets": tools.handle_batch_search_tickets,
    "get_ticket_bundle_zendesk": tools.handle_get_ticket_bundle_zendesk,
    "get_case_volume_analytics": tools.handle_get_case_volume_analytics,
}

__all__ = ['TOOL_HANDLERS']

