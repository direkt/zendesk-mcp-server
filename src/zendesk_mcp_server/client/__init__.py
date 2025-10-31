"""ZendeskClient - composed from base and specialized mixins."""
from zendesk_mcp_server.client.base import ZendeskClientBase
from zendesk_mcp_server.client.tickets import TicketMixin
from zendesk_mcp_server.client.search import SearchMixin
from zendesk_mcp_server.client.kb import KnowledgeBaseMixin
from zendesk_mcp_server.client.attachments import AttachmentsMixin
from zendesk_mcp_server.client.relationships import RelationshipsMixin


class ZendeskClient(
    ZendeskClientBase,
    TicketMixin,
    SearchMixin,
    KnowledgeBaseMixin,
    AttachmentsMixin,
    RelationshipsMixin,
):
    """
    Main ZendeskClient class composed from base and specialized mixins.
    
    Maintains backward compatibility with the monolithic ZendeskClient class.
    All methods are available through multiple inheritance from the mixins.
    """
    pass


__all__ = ['ZendeskClient']
