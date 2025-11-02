"""Ticket relationship methods for ZendeskClient."""
from typing import Any, Dict

from zendesk_mcp_server.exceptions import ZendeskError, ZendeskAPIError, ZendeskValidationError


class RelationshipsMixin:
    """Mixin providing ticket relationship methods."""

    def find_related_tickets(self, ticket_id: int, limit: int = 100) -> Dict[str, Any]:
        """Find tickets related to the given ticket by subject similarity, same requester, or same organization."""
        try:
            # Get the reference ticket
            reference_ticket = self.get_ticket(ticket_id)
            if not reference_ticket:
                raise ZendeskValidationError(f"Ticket {ticket_id} not found")

            # Extract search criteria
            subject = reference_ticket.get('subject', '')
            requester_id = reference_ticket.get('requester_id')
            organization_id = reference_ticket.get('organization_id')

            # Extract key terms from subject for similarity search
            subject_terms = self._extract_search_terms(subject)

            related_tickets = []
            search_strategies = []

            # Search 1: Similar subject (if we have terms)
            if subject_terms:
                try:
                    subject_query = f'subject:"{subject_terms}"'
                    subject_results = self.search_tickets_export(
                        query=subject_query,
                        max_results=limit
                    )

                    for ticket in subject_results.get('tickets', []):
                        if ticket['id'] != ticket_id:  # Exclude reference ticket
                            ticket['relevance_reason'] = 'similar_subject'
                            ticket['relevance_score'] = self._calculate_subject_similarity(subject, ticket['subject'])
                            related_tickets.append(ticket)

                    if subject_results.get('tickets'):
                        search_strategies.append(f"Found {len(subject_results['tickets'])} tickets with similar subjects")
                except Exception as e:
                    search_strategies.append(f"Subject search failed: {str(e)}")

            # Search 2: Same requester
            if requester_id:
                try:
                    requester_query = f'requester_id:{requester_id}'
                    requester_results = self.search_tickets_export(
                        query=requester_query,
                        max_results=limit
                    )

                    for ticket in requester_results.get('tickets', []):
                        if ticket['id'] != ticket_id:  # Exclude reference ticket
                            # Check if already added (avoid duplicates)
                            if not any(t['id'] == ticket['id'] for t in related_tickets):
                                ticket['relevance_reason'] = 'same_requester'
                                ticket['relevance_score'] = 0.8  # High relevance for same requester
                                related_tickets.append(ticket)

                    if requester_results.get('tickets'):
                        search_strategies.append(f"Found {len(requester_results['tickets'])} tickets from same requester")
                except Exception as e:
                    search_strategies.append(f"Requester search failed: {str(e)}")

            # Search 3: Same organization (if present)
            if organization_id:
                try:
                    org_query = f'organization_id:{organization_id}'
                    org_results = self.search_tickets_export(
                        query=org_query,
                        max_results=limit
                    )

                    for ticket in org_results.get('tickets', []):
                        if ticket['id'] != ticket_id:  # Exclude reference ticket
                            # Check if already added (avoid duplicates)
                            if not any(t['id'] == ticket['id'] for t in related_tickets):
                                ticket['relevance_reason'] = 'same_organization'
                                ticket['relevance_score'] = 0.6  # Medium relevance for same org
                                related_tickets.append(ticket)

                    if org_results.get('tickets'):
                        search_strategies.append(f"Found {len(org_results['tickets'])} tickets from same organization")
                except Exception as e:
                    search_strategies.append(f"Organization search failed: {str(e)}")

            # Sort by relevance score (descending) and updated_at (descending)
            related_tickets.sort(key=lambda x: (-x['relevance_score'], x['updated_at']), reverse=True)

            # Apply limit
            related_tickets = related_tickets[:limit]

            return {
                'related_tickets': related_tickets,
                'count': len(related_tickets),
                'reference_ticket': {
                    'id': reference_ticket['id'],
                    'subject': reference_ticket['subject'],
                    'requester_id': requester_id,
                    'organization_id': organization_id
                },
                'search_strategy': '; '.join(search_strategies) if search_strategies else 'No search strategies executed'
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to find related tickets for {ticket_id}: {str(e)}")

    def find_duplicate_tickets(self, ticket_id: int, limit: int = 100) -> Dict[str, Any]:
        """Identify potential duplicate tickets with highly similar subjects and same requester/organization."""
        try:
            # Get the reference ticket
            reference_ticket = self.get_ticket(ticket_id)
            if not reference_ticket:
                raise ZendeskValidationError(f"Ticket {ticket_id} not found")

            subject = reference_ticket.get('subject', '')
            requester_id = reference_ticket.get('requester_id')
            organization_id = reference_ticket.get('organization_id')

            # Extract key terms from subject
            subject_terms = self._extract_search_terms(subject)

            duplicate_candidates = []
            similarity_threshold = 0.7  # Minimum similarity score

            # Search for tickets with similar subjects
            if subject_terms:
                try:
                    # Use a broader search to catch potential duplicates
                    subject_query = f'subject:"{subject_terms}"'
                    subject_results = self.search_tickets_export(
                        query=subject_query,
                        max_results=limit * 2  # Get more to filter by similarity
                    )

                    for ticket in subject_results.get('tickets', []):
                        if ticket['id'] != ticket_id:  # Exclude reference ticket
                            similarity_score = self._calculate_subject_similarity(subject, ticket['subject'])

                            # Only include tickets above similarity threshold
                            if similarity_score >= similarity_threshold:
                                # Additional filtering: same requester or organization for better precision
                                is_same_requester = ticket.get('requester_id') == requester_id
                                is_same_org = ticket.get('organization_id') == organization_id

                                if is_same_requester or is_same_org:
                                    ticket['similarity_score'] = similarity_score
                                    ticket['duplicate_reason'] = 'similar_subject'
                                    if is_same_requester:
                                        ticket['duplicate_reason'] += '_same_requester'
                                    if is_same_org:
                                        ticket['duplicate_reason'] += '_same_organization'

                                    duplicate_candidates.append(ticket)

                except Exception as e:
                    pass  # Continue even if subject search fails

            # Also search by exact subject match (highest priority)
            try:
                exact_subject_query = f'subject:"{subject}"'
                exact_results = self.search_tickets_export(
                    query=exact_subject_query,
                    max_results=limit
                )

                for ticket in exact_results.get('tickets', []):
                    if ticket['id'] != ticket_id:  # Exclude reference ticket
                        # Check if already added
                        if not any(t['id'] == ticket['id'] for t in duplicate_candidates):
                            ticket['similarity_score'] = 1.0  # Exact match
                            ticket['duplicate_reason'] = 'exact_subject_match'
                            duplicate_candidates.append(ticket)

            except Exception as e:
                pass  # Continue even if exact search fails

            # Sort by similarity score (descending) and creation date (ascending - older duplicates first)
            duplicate_candidates.sort(key=lambda x: (-x['similarity_score'], x['created_at']))

            # Apply limit
            duplicate_candidates = duplicate_candidates[:limit]

            return {
                'duplicate_candidates': duplicate_candidates,
                'count': len(duplicate_candidates),
                'reference_ticket': {
                    'id': reference_ticket['id'],
                    'subject': reference_ticket['subject'],
                    'requester_id': requester_id,
                    'organization_id': organization_id
                },
                'similarity_threshold': similarity_threshold
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to find duplicate tickets for {ticket_id}: {str(e)}")

    def find_ticket_thread(self, ticket_id: int) -> Dict[str, Any]:
        """Find all tickets in a conversation thread using via_id relationships."""
        try:
            # Get the reference ticket with full details
            reference_ticket = self.client.tickets(id=ticket_id)

            thread_tickets = []
            thread_root = None

            # Check if this ticket has a via_id (is a child ticket)
            via_id = getattr(reference_ticket, 'via_id', None)

            if via_id:
                # This ticket is a child, find the parent
                try:
                    parent_ticket = self.client.tickets(id=via_id)
                    thread_root = {
                        'id': parent_ticket.id,
                        'subject': parent_ticket.subject,
                        'status': parent_ticket.status,
                        'created_at': str(parent_ticket.created_at),
                        'updated_at': str(parent_ticket.updated_at),
                        'requester_id': parent_ticket.requester_id,
                        'assignee_id': parent_ticket.assignee_id
                    }
                    thread_tickets.append(thread_root)
                except Exception as e:
                    pass  # Parent ticket might not exist

            # Search for child tickets (tickets that reference this ticket as via_id)
            try:
                child_query = f'via_id:{ticket_id}'
                child_results = self.search_tickets_export(
                    query=child_query
                )

                for ticket in child_results.get('tickets', []):
                    child_ticket = {
                        'id': ticket['id'],
                        'subject': ticket['subject'],
                        'status': ticket['status'],
                        'created_at': ticket['created_at'],
                        'updated_at': ticket['updated_at'],
                        'requester_id': ticket['requester_id'],
                        'assignee_id': ticket['assignee_id'],
                        'relationship': 'child'
                    }
                    thread_tickets.append(child_ticket)

            except Exception as e:
                pass  # No child tickets found

            # Add the reference ticket if not already included
            if not any(t['id'] == ticket_id for t in thread_tickets):
                reference_info = {
                    'id': reference_ticket.id,
                    'subject': reference_ticket.subject,
                    'status': reference_ticket.status,
                    'created_at': str(reference_ticket.created_at),
                    'updated_at': str(reference_ticket.updated_at),
                    'requester_id': reference_ticket.requester_id,
                    'assignee_id': reference_ticket.assignee_id,
                    'relationship': 'reference'
                }
                thread_tickets.append(reference_info)

            # Sort by creation date to show chronological order
            thread_tickets.sort(key=lambda x: x['created_at'])

            # Determine thread structure
            thread_structure = "Single ticket"
            if len(thread_tickets) > 1:
                if thread_root:
                    thread_structure = f"Thread with {len(thread_tickets)} tickets (parent + children)"
                else:
                    thread_structure = f"Thread with {len(thread_tickets)} tickets (children only)"

            return {
                'thread_tickets': thread_tickets,
                'count': len(thread_tickets),
                'thread_root': thread_root,
                'thread_structure': thread_structure,
                'reference_ticket_id': ticket_id
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to find ticket thread for {ticket_id}: {str(e)}")

    def get_ticket_relationships(self, ticket_id: int) -> Dict[str, Any]:
        """Get parent/child ticket relationships via the via field."""
        try:
            # Get the reference ticket with full details
            reference_ticket = self.client.tickets(id=ticket_id)

            relationships = {
                'parent': None,
                'children': [],
                'siblings': []
            }

            # Check for parent relationship (via_id field)
            via_id = getattr(reference_ticket, 'via_id', None)
            if via_id:
                try:
                    parent_ticket = self.client.tickets(id=via_id)
                    relationships['parent'] = {
                        'id': parent_ticket.id,
                        'subject': parent_ticket.subject,
                        'status': parent_ticket.status,
                        'created_at': str(parent_ticket.created_at),
                        'updated_at': str(parent_ticket.updated_at),
                        'requester_id': parent_ticket.requester_id,
                        'assignee_id': parent_ticket.assignee_id,
                        'relationship': 'parent'
                    }
                except Exception as e:
                    relationships['parent'] = {'id': via_id, 'error': f'Parent ticket not accessible: {str(e)}'}

            # Search for child tickets
            try:
                child_query = f'via_id:{ticket_id}'
                child_results = self.search_tickets_export(
                    query=child_query
                )

                for ticket in child_results.get('tickets', []):
                    child_ticket = {
                        'id': ticket['id'],
                        'subject': ticket['subject'],
                        'status': ticket['status'],
                        'created_at': ticket['created_at'],
                        'updated_at': ticket['updated_at'],
                        'requester_id': ticket['requester_id'],
                        'assignee_id': ticket['assignee_id'],
                        'relationship': 'child'
                    }
                    relationships['children'].append(child_ticket)

            except Exception as e:
                pass  # No children found

            # Search for sibling tickets (tickets with same parent)
            if via_id:
                try:
                    sibling_query = f'via_id:{via_id} -id:{ticket_id}'  # Same parent, exclude self
                    sibling_results = self.search_tickets_export(
                        query=sibling_query
                    )

                    for ticket in sibling_results.get('tickets', []):
                        sibling_ticket = {
                            'id': ticket['id'],
                            'subject': ticket['subject'],
                            'status': ticket['status'],
                            'created_at': ticket['created_at'],
                            'updated_at': ticket['updated_at'],
                            'requester_id': ticket['requester_id'],
                            'assignee_id': ticket['assignee_id'],
                            'relationship': 'sibling'
                        }
                        relationships['siblings'].append(sibling_ticket)

                except Exception as e:
                    pass  # No siblings found

            # Determine relationship type
            relationship_type = "Standalone ticket"
            if relationships['parent'] and relationships['children']:
                relationship_type = "Middle ticket in chain (has parent and children)"
            elif relationships['parent']:
                relationship_type = "Child ticket (has parent)"
            elif relationships['children']:
                relationship_type = "Parent ticket (has children)"
            elif relationships['siblings']:
                relationship_type = "Sibling ticket (shares parent with other tickets)"

            return {
                'relationships': relationships,
                'parent_ticket': relationships['parent'],
                'child_tickets': relationships['children'],
                'sibling_tickets': relationships['siblings'],
                'relationship_type': relationship_type,
                'reference_ticket_id': ticket_id,
                'total_related': len(relationships['children']) + len(relationships['siblings']) + (1 if relationships['parent'] else 0)
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get ticket relationships for {ticket_id}: {str(e)}")

    def get_ticket_fields(self) -> Dict[str, Any]:
        """Retrieve all ticket fields including custom fields with their definitions."""
        try:
            # Get all ticket fields using zenpy
            fields = self.client.ticket_fields()

            field_list = []
            custom_fields = []
            system_fields = []

            for field in fields:
                field_info = {
                    'id': field.id,
                    'title': field.title,
                    'type': field.type,
                    'description': getattr(field, 'description', ''),
                    'required': getattr(field, 'required', False),
                    'collapsed_for_agents': getattr(field, 'collapsed_for_agents', False),
                    'active': getattr(field, 'active', True),
                    'position': getattr(field, 'position', 0),
                    'created_at': str(field.created_at),
                    'updated_at': str(field.updated_at)
                }

                # Add field-specific attributes
                if field.type == 'tagger':
                    field_info['custom_field_options'] = [
                        {
                            'id': option.id,
                            'name': option.name,
                            'value': option.value,
                            'position': getattr(option, 'position', 0)
                        } for option in getattr(field, 'custom_field_options', [])
                    ]
                elif field.type == 'dropdown':
                    field_info['custom_field_options'] = [
                        {
                            'id': option.id,
                            'name': option.name,
                            'value': option.value,
                            'position': getattr(option, 'position', 0)
                        } for option in getattr(field, 'custom_field_options', [])
                    ]
                elif field.type == 'date':
                    field_info['default_date'] = getattr(field, 'default_date', None)
                elif field.type == 'integer':
                    field_info['min'] = getattr(field, 'min', None)
                    field_info['max'] = getattr(field, 'max', None)
                elif field.type == 'decimal':
                    field_info['min'] = getattr(field, 'min', None)
                    field_info['max'] = getattr(field, 'max', None)
                    field_info['precision'] = getattr(field, 'precision', None)

                field_list.append(field_info)

                # Categorize fields
                if getattr(field, 'custom_field_id', None) is not None:
                    custom_fields.append(field_info)
                else:
                    system_fields.append(field_info)

            return {
                'fields': field_list,
                'custom_fields': custom_fields,
                'system_fields': system_fields,
                'count': len(field_list),
                'custom_count': len(custom_fields),
                'system_count': len(system_fields)
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get ticket fields: {str(e)}")

