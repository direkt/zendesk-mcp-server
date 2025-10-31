"""Ticket-related methods for ZendeskClient."""
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List
from datetime import datetime

from zenpy.lib.api_objects import Comment
from zenpy.lib.api_objects import Ticket as ZenpyTicket

from zendesk_mcp_server.exceptions import (
    ZendeskError,
    ZendeskAPIError,
    ZendeskValidationError,
    ZendeskNotFoundError,
    ZendeskRateLimitError,
    ZendeskNetworkError,
)
from zendesk_mcp_server.client.base import _urlopen_with_retry


class TicketMixin:
    """Mixin providing ticket-related methods."""
    
    def get_ticket(self, ticket_id: int) -> Dict[str, Any]:
        """Query a ticket by its ID."""
        try:
            ticket = self.client.tickets(id=ticket_id)
            return {
                'id': ticket.id,
                'subject': ticket.subject,
                'description': ticket.description,
                'status': ticket.status,
                'priority': ticket.priority,
                'created_at': str(ticket.created_at),
                'updated_at': str(ticket.updated_at),
                'requester_id': ticket.requester_id,
                'assignee_id': ticket.assignee_id,
                'organization_id': ticket.organization_id
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get ticket {ticket_id}: {str(e)}")

    def get_ticket_comments(self, ticket_id: int) -> List[Dict[str, Any]]:
        """Get all comments for a specific ticket."""
        try:
            comments = self.client.tickets.comments(ticket=ticket_id)
            return [{
                'id': comment.id,
                'author_id': comment.author_id,
                'body': comment.body,
                'html_body': comment.html_body,
                'public': comment.public,
                'created_at': str(comment.created_at)
            } for comment in comments]
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get comments for ticket {ticket_id}: {str(e)}")

    def incremental_tickets(
        self,
        start_time: int | datetime,
        include: list[str] | None = None,
        max_results: int | None = None,
    ) -> tuple[list[dict], bool, int | None]:
        """Incremental Tickets API wrapper.
        
        Args:
            start_time: Unix epoch seconds or datetime to start from (inclusive).
            include: Optional list of include values; passed as CSV to include= query.
            max_results: Global cap across pages; fetches until end if None.

        Returns: (items, has_more, next_start_time)
        """
        include_csv = ",".join(include) if include else None
        return self._incremental_fetch(
            path="/incremental/tickets.json",
            items_key="tickets",
            start_time=start_time,
            include_csv=include_csv,
            max_results=max_results,
            cursor_endpoint_key="incremental_tickets",
        )

    def incremental_ticket_events(
        self,
        start_time: int | datetime,
        max_results: int | None = None,
    ) -> tuple[list[dict], bool, int | None]:
        """Incremental Ticket Events API wrapper.
        
        Returns: (items, has_more, next_start_time)
        """
        return self._incremental_fetch(
            path="/incremental/ticket_events.json",
            items_key="ticket_events",
            start_time=start_time,
            include_csv=None,
            max_results=max_results,
            cursor_endpoint_key="incremental_ticket_events",
        )

    def get_ticket_audits(self, ticket_id: int, limit: int = 100) -> Dict[str, Any]:
        """Fetch ticket audits with pagination up to the given limit.
        
        Returns a dict with audits, count, and has_more.
        """
        try:
            audits: List[Dict[str, Any]] = []
            has_more = False
            url = f"{self.base_url}/tickets/{ticket_id}/audits.json"

            while url and len(audits) < limit:
                data = self._get_json_url(url)
                page_audits = data.get('audits') or []
                audits.extend(page_audits)
                url = data.get('next_page')
                if len(audits) >= limit:
                    has_more = bool(url)
                    break

            if len(audits) > limit:
                audits = audits[:limit]

            return {
                'audits': audits,
                'count': len(audits),
                'has_more': has_more,
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get audits for ticket {ticket_id}: {str(e)}")

    def _get_ticket_comments_with_attachments(self, ticket_id: int, limit: int = 50) -> Dict[str, Any]:
        """Fetch ticket comments (via direct API) including attachments, up to limit.
        
        Returns a dict with comments (normalized), count, has_more.
        """
        try:
            comments: List[Dict[str, Any]] = []
            has_more = False
            url = f"{self.base_url}/tickets/{ticket_id}/comments.json"

            while url and len(comments) < limit:
                data = self._get_json_url(url)
                for c in data.get('comments', []) or []:
                    att_list = []
                    for a in c.get('attachments', []) or []:
                        att_list.append({
                            'id': a.get('id'),
                            'file_name': a.get('file_name'),
                            'content_type': a.get('content_type'),
                            'content_url': a.get('content_url'),
                            'size': a.get('size'),
                        })
                    comments.append({
                        'id': c.get('id'),
                        'author_id': c.get('author_id'),
                        'body': c.get('body'),
                        'html_body': c.get('html_body'),
                        'public': c.get('public'),
                        'created_at': c.get('created_at'),
                        'attachments': att_list,
                    })
                    if len(comments) >= limit:
                        break
                next_page = data.get('next_page')
                if len(comments) >= limit:
                    has_more = bool(next_page)
                    break
                url = next_page

            if len(comments) > limit:
                comments = comments[:limit]

            return {
                'comments': comments,
                'count': len(comments),
                'has_more': has_more,
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get comments for ticket {ticket_id}: {str(e)}")

    def get_ticket_bundle(self, ticket_id: int, comment_limit: int = 50, audit_limit: int = 100) -> Dict[str, Any]:
        """Consolidate ticket, audits, comments(with attachments), and requester/assignee/org context
        into a single response with a chronological timeline.
        """
        # Core ticket (raise if not found)
        ticket = self.get_ticket(ticket_id)

        # Comments and audits with limits
        comments_res = self._get_ticket_comments_with_attachments(ticket_id, limit=comment_limit)
        audits_res = self.get_ticket_audits(ticket_id, limit=audit_limit)

        comments = comments_res['comments']
        audits = audits_res['audits']

        # User/org context (best effort)
        requester = self._get_user(ticket.get('requester_id')) if ticket.get('requester_id') else None
        assignee = self._get_user(ticket.get('assignee_id')) if ticket.get('assignee_id') else None
        organization = self._get_organization(ticket.get('organization_id')) if ticket.get('organization_id') else None

        # Build timeline from audits (field changes) and comments
        timeline: List[Dict[str, Any]] = []

        # Normalize audit events
        for audit in audits:
            created_at = audit.get('created_at') or audit.get('timestamp')
            author_id = audit.get('author_id')
            for ev in audit.get('events', []) or []:
                ev_type = (ev.get('type') or '').lower()
                if 'comment' in ev_type:
                    # Skip audit comment events; comments are already included
                    continue
                if 'change' in ev_type or ev_type == 'change':
                    field = ev.get('field') or ev.get('field_name') or ev.get('attribute')
                    prev_val = ev.get('previous_value') or ev.get('previous') or ev.get('from')
                    new_val = ev.get('value') or ev.get('new_value') or ev.get('to')
                    if field == 'status':
                        event_type = 'status_change'
                    elif field == 'assignee_id':
                        event_type = 'assignment'
                    elif field == 'priority':
                        event_type = 'priority_change'
                    else:
                        event_type = 'field_update'
                    timeline.append({
                        'timestamp': created_at,
                        'event_type': event_type,
                        'author_id': author_id,
                        'details': {
                            'field': field,
                            'from': prev_val,
                            'to': new_val,
                        }
                    })
                else:
                    # Generic audit event
                    timeline.append({
                        'timestamp': created_at,
                        'event_type': ev.get('type') or 'audit_event',
                        'author_id': author_id,
                        'details': {k: v for k, v in ev.items() if k not in ('type')}
                    })

        # Normalize comment events
        for c in comments:
            timeline.append({
                'timestamp': c.get('created_at'),
                'event_type': 'comment',
                'author_id': c.get('author_id'),
                'details': {
                    'public': c.get('public'),
                    'attachments': c.get('attachments') or [],
                }
            })

        # Sort timeline chronologically (oldest first)
        timeline.sort(key=lambda e: e.get('timestamp') or '')

        summary = {
            'total_comments': len(comments),
            'total_audits': len(audits),
            'status_changes': sum(1 for e in timeline if e['event_type'] == 'status_change'),
            'assignment_changes': sum(1 for e in timeline if e['event_type'] == 'assignment'),
            'last_updated': ticket.get('updated_at'),
        }

        return {
            'ticket_id': ticket_id,
            'ticket': ticket,
            'requester': requester,
            'assignee': assignee,
            'organization': organization,
            'comments': comments,
            'comments_count': len(comments),
            'comments_has_more': comments_res['has_more'],
            'audits': audits,
            'audits_count': len(audits),
            'audits_has_more': audits_res['has_more'],
            'timeline': timeline,
            'summary': summary,
        }

    def get_tickets(self, page: int = 1, per_page: int = 25, sort_by: str = 'created_at', sort_order: str = 'desc') -> Dict[str, Any]:
        """Get the latest tickets with proper pagination support using direct API calls.

        Args:
            page: Page number (1-based)
            per_page: Number of tickets per page (max 100)
            sort_by: Field to sort by (created_at, updated_at, priority, status)
            sort_order: Sort order (asc or desc)

        Returns:
            Dict containing tickets and pagination info
        """
        try:
            # Cap at reasonable limit
            per_page = min(per_page, 100)

            # Build URL with parameters for offset pagination
            params = {
                'page': str(page),
                'per_page': str(per_page),
                'sort_by': sort_by,
                'sort_order': sort_order
            }
            query_string = urllib.parse.urlencode(params)
            url = f"{self.base_url}/tickets.json?{query_string}"

            # Create request with auth header
            req = urllib.request.Request(url)
            req.add_header('Authorization', self.auth_header)
            req.add_header('Content-Type', 'application/json')

            # Make the API request
            with _urlopen_with_retry(req) as response:
                data = json.loads(response.read().decode())

            tickets_data = data.get('tickets', [])

            # Process tickets to return only essential fields
            ticket_list = []
            for ticket in tickets_data:
                ticket_list.append({
                    'id': ticket.get('id'),
                    'subject': ticket.get('subject'),
                    'status': ticket.get('status'),
                    'priority': ticket.get('priority'),
                    'description': ticket.get('description'),
                    'created_at': ticket.get('created_at'),
                    'updated_at': ticket.get('updated_at'),
                    'requester_id': ticket.get('requester_id'),
                    'assignee_id': ticket.get('assignee_id')
                })

            return {
                'tickets': ticket_list,
                'page': page,
                'per_page': per_page,
                'count': len(ticket_list),
                'sort_by': sort_by,
                'sort_order': sort_order,
                'has_more': data.get('next_page') is not None,
                'next_page': page + 1 if data.get('next_page') else None,
                'previous_page': page - 1 if data.get('previous_page') and page > 1 else None
            }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else "No response body"
            status_code = getattr(e, 'code', None)
            if status_code == 404:
                raise ZendeskNotFoundError(
                    f"Failed to get latest tickets: HTTP {e.code} - {e.reason}",
                    status_code=status_code,
                    response_body=error_body
                )
            elif status_code == 429:
                raise ZendeskRateLimitError(
                    f"Failed to get latest tickets: HTTP {e.code} - {e.reason}",
                    status_code=status_code,
                    response_body=error_body
                )
            else:
                raise ZendeskAPIError(
                    f"Failed to get latest tickets: HTTP {e.code} - {e.reason}",
                    status_code=status_code,
                    response_body=error_body
                )
        except urllib.error.URLError as e:
            raise ZendeskNetworkError(f"Network error getting latest tickets: {str(e)}")
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get latest tickets: {str(e)}")

    def post_comment(self, ticket_id: int, comment: str, public: bool = True) -> str:
        """Post a comment to an existing ticket."""
        try:
            ticket = self.client.tickets(id=ticket_id)
            ticket.comment = Comment(
                html_body=comment,
                public=public
            )
            self.client.tickets.update(ticket)
            return comment
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to post comment on ticket {ticket_id}: {str(e)}")

    def create_ticket(
        self,
        subject: str,
        description: str,
        requester_id: int | None = None,
        assignee_id: int | None = None,
        priority: str | None = None,
        type: str | None = None,
        tags: List[str] | None = None,
        custom_fields: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Create a new Zendesk ticket using Zenpy and return essential fields.

        Args:
            subject: Ticket subject
            description: Ticket description (plain text). Will also be used as initial comment.
            requester_id: Optional requester user ID
            assignee_id: Optional assignee user ID
            priority: Optional priority (low, normal, high, urgent)
            type: Optional ticket type (problem, incident, question, task)
            tags: Optional list of tags
            custom_fields: Optional list of dicts: {id: int, value: Any}
        """
        try:
            ticket = ZenpyTicket(
                subject=subject,
                description=description,
                requester_id=requester_id,
                assignee_id=assignee_id,
                priority=priority,
                type=type,
                tags=tags,
                custom_fields=custom_fields,
            )
            created_audit = self.client.tickets.create(ticket)
            # Fetch created ticket id from audit
            created_ticket_id = getattr(getattr(created_audit, 'ticket', None), 'id', None)
            if created_ticket_id is None:
                # Fallback: try to read id from audit events
                created_ticket_id = getattr(created_audit, 'id', None)

            # Fetch full ticket to return consistent data
            created = self.client.tickets(id=created_ticket_id) if created_ticket_id else None

            return {
                'id': getattr(created, 'id', created_ticket_id),
                'subject': getattr(created, 'subject', subject),
                'description': getattr(created, 'description', description),
                'status': getattr(created, 'status', 'new'),
                'priority': getattr(created, 'priority', priority),
                'type': getattr(created, 'type', type),
                'created_at': str(getattr(created, 'created_at', '')),
                'updated_at': str(getattr(created, 'updated_at', '')),
                'requester_id': getattr(created, 'requester_id', requester_id),
                'assignee_id': getattr(created, 'assignee_id', assignee_id),
                'organization_id': getattr(created, 'organization_id', None),
                'tags': list(getattr(created, 'tags', tags or []) or []),
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to create ticket: {str(e)}")

    def update_ticket(self, ticket_id: int, **fields: Any) -> Dict[str, Any]:
        """Update a Zendesk ticket with provided fields using Zenpy.

        Supported fields include common ticket attributes like:
        subject, status, priority, type, assignee_id, requester_id,
        tags (list[str]), custom_fields (list[dict]), due_at, etc.
        """
        try:
            # Load the ticket, mutate fields directly, and update
            ticket = self.client.tickets(id=ticket_id)
            for key, value in fields.items():
                if value is None:
                    continue
                setattr(ticket, key, value)

            # This call returns a TicketAudit (not a Ticket). Don't read attrs from it.
            self.client.tickets.update(ticket)

            # Fetch the fresh ticket to return consistent data
            refreshed = self.client.tickets(id=ticket_id)

            return {
                'id': refreshed.id,
                'subject': refreshed.subject,
                'description': refreshed.description,
                'status': refreshed.status,
                'priority': refreshed.priority,
                'type': getattr(refreshed, 'type', None),
                'created_at': str(refreshed.created_at),
                'updated_at': str(refreshed.updated_at),
                'requester_id': refreshed.requester_id,
                'assignee_id': refreshed.assignee_id,
                'organization_id': refreshed.organization_id,
                'tags': list(getattr(refreshed, 'tags', []) or []),
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to update ticket {ticket_id}: {str(e)}")

