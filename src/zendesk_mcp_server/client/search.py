"""Search-related methods for ZendeskClient."""
import re
from typing import Any, Dict, List
from datetime import datetime, timedelta, date, timezone
from collections import defaultdict
import calendar

from zendesk_mcp_server.exceptions import ZendeskError, ZendeskAPIError, ZendeskValidationError


class SearchMixin:
    """Mixin providing search-related methods."""
    
    def search_tickets(
        self,
        query: str,
        sort_by: str | None = None,
        sort_order: str | None = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Search for tickets using Zendesk's search query syntax.

        This method returns up to 1000 results (Zendesk API limitation).
        For larger result sets, use search_tickets_export instead.
        """
        try:
            if not query:
                raise ZendeskValidationError("Search query cannot be empty")

            # Cap limit at 1000 (Zendesk API max)
            limit = min(limit, 1000)

            # Build search parameters
            search_params = {'type': 'ticket'}
            if sort_by:
                search_params['sort_by'] = sort_by
            if sort_order:
                search_params['sort_order'] = sort_order

            # Execute search using zenpy
            search_results = self.client.search(query, **search_params)

            # Collect results up to limit
            tickets = []
            count = 0
            for ticket in search_results:
                if count >= limit:
                    break
                tickets.append({
                    'id': ticket.id,
                    'subject': ticket.subject,
                    'description': ticket.description,
                    'status': ticket.status,
                    'priority': ticket.priority,
                    'type': getattr(ticket, 'type', None),
                    'created_at': str(ticket.created_at),
                    'updated_at': str(ticket.updated_at),
                    'requester_id': ticket.requester_id,
                    'assignee_id': ticket.assignee_id,
                    'organization_id': ticket.organization_id,
                    'tags': list(getattr(ticket, 'tags', []) or []),
                })
                count += 1

            # Check if there might be more results
            has_more = count >= limit

            return {
                'tickets': tickets,
                'count': count,
                'query': query,
                'sort_by': sort_by,
                'sort_order': sort_order,
                'limit': limit,
                'has_more': has_more,
                'note': 'Search API limited to 1000 total results. Use search_tickets_export for unlimited results.'
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to search tickets: {str(e)}")

    def search_tickets_export(
        self,
        query: str,
        sort_by: str | None = None,
        sort_order: str | None = None,
        max_results: int | None = None
    ) -> Dict[str, Any]:
        """Search for tickets using Zendesk's search export API (unlimited results)."""
        try:
            if not query:
                raise ZendeskValidationError("Search query cannot be empty")

            # Build search parameters - Export API does not support sorting
            # Sort parameters are stripped and applied client-side instead
            search_params = {'type': 'ticket'}

            # Execute search export using zenpy (without sort parameters)
            search_results = self.client.search_export(query, **search_params)

            # Collect all results (or up to max_results if specified)
            tickets = []
            count = 0
            for ticket in search_results:
                if max_results and count >= max_results:
                    break
                
                # Extract via object for channel/source info
                via_obj = getattr(ticket, 'via', None)
                via_data = None
                if via_obj:
                    via_data = {
                        'channel': getattr(via_obj, 'channel', None),
                        'source': getattr(via_obj, 'source', None) if hasattr(via_obj, 'source') else None,
                    }
                
                # Extract metric fields
                metric_set = getattr(ticket, 'metric_set', None)
                metrics = {}
                if metric_set:
                    metrics = {
                        'reply_time_in_seconds': getattr(metric_set, 'reply_time_in_seconds', None),
                        'first_resolution_time_in_seconds': getattr(metric_set, 'first_resolution_time_in_seconds', None),
                        'full_resolution_time_in_seconds': getattr(metric_set, 'full_resolution_time_in_seconds', None),
                        'agent_wait_time_in_seconds': getattr(metric_set, 'agent_wait_time_in_seconds', None),
                        'requester_wait_time_in_seconds': getattr(metric_set, 'requester_wait_time_in_seconds', None),
                        'on_hold_time_in_seconds': getattr(metric_set, 'on_hold_time_in_seconds', None),
                    }
                
                # Extract satisfaction rating
                satisfaction = getattr(ticket, 'satisfaction_rating', None)
                satisfaction_data = None
                if satisfaction:
                    satisfaction_data = {
                        'score': getattr(satisfaction, 'score', None),
                        'comment': getattr(satisfaction, 'comment', None),
                    }
                
                # Extract custom fields
                custom_fields_data = []
                custom_fields_obj = getattr(ticket, 'custom_fields', None)
                if custom_fields_obj:
                    for cf in custom_fields_obj:
                        custom_fields_data.append({
                            'id': getattr(cf, 'id', None),
                            'value': getattr(cf, 'value', None),
                        })
                
                tickets.append({
                    'id': ticket.id,
                    'subject': ticket.subject,
                    'description': ticket.description,
                    'status': ticket.status,
                    'priority': ticket.priority,
                    'type': getattr(ticket, 'type', None),
                    'created_at': str(ticket.created_at),
                    'updated_at': str(ticket.updated_at),
                    'solved_at': str(getattr(ticket, 'solved_at', None)) if getattr(ticket, 'solved_at', None) else None,
                    'requester_id': ticket.requester_id,
                    'assignee_id': ticket.assignee_id,
                    'organization_id': ticket.organization_id,
                    'group_id': getattr(ticket, 'group_id', None),
                    'ticket_form_id': getattr(ticket, 'ticket_form_id', None),
                    'tags': list(getattr(ticket, 'tags', []) or []),
                    'custom_fields': custom_fields_data,
                    'via': via_data,
                    'metrics': metrics,
                    'satisfaction_rating': satisfaction_data,
                })
                count += 1

            # Apply client-side sorting if sort parameters provided
            if sort_by and tickets:
                reverse_order = sort_order == 'desc' if sort_order else True

                def get_sort_key(ticket):
                    field_value = ticket.get(sort_by)

                    # Handle different field types
                    if sort_by in ['created_at', 'updated_at']:
                        # Convert ISO datetime strings to comparable format
                        try:
                            return datetime.fromisoformat(field_value.replace('Z', '+00:00'))
                        except:
                            return field_value or ''
                    elif sort_by == 'priority':
                        # Priority order: urgent > high > normal > low
                        priority_order = {'urgent': 4, 'high': 3, 'normal': 2, 'low': 1}
                        return priority_order.get(field_value, 0)
                    elif sort_by == 'status':
                        # Status order: new > open > pending > on-hold > solved > closed
                        status_order = {'new': 6, 'open': 5, 'pending': 4, 'on-hold': 3, 'solved': 2, 'closed': 1}
                        return status_order.get(field_value, 0)
                    else:
                        # For other fields, use string comparison
                        return str(field_value or '')

                tickets.sort(key=get_sort_key, reverse=reverse_order)

            # Indicate if results were truncated by max_results
            has_more = bool(max_results and count >= max_results)

            return {
                'tickets': tickets,
                'count': count,
                'query': query,
                'sort_by': sort_by,
                'sort_order': sort_order,
                'max_results': max_results,
                'has_more': has_more,
                'note': 'Results from search export API (no 1000 result limit). Sorting applied client-side.'
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to export search tickets: {str(e)}")

    def _apply_regex_filter(
        self,
        tickets: List[Dict[str, Any]],
        regex_pattern: str,
        fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Apply regex pattern filter to a list of tickets."""
        if not regex_pattern:
            return tickets

        if fields is None:
            fields = ['subject', 'description']

        try:
            pattern = re.compile(regex_pattern, re.IGNORECASE)
            filtered_tickets = []
            for ticket in tickets:
                for field in fields:
                    field_value = ticket.get(field, '')
                    if field_value and pattern.search(str(field_value)):
                        ticket_copy = ticket.copy()
                        ticket_copy['regex_match_field'] = field
                        ticket_copy['regex_pattern'] = regex_pattern
                        filtered_tickets.append(ticket_copy)
                        break  # Only add ticket once even if multiple fields match

            return filtered_tickets
        except re.error as e:
            raise ZendeskValidationError(f"Invalid regex pattern: {str(e)}")
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to apply regex filter: {str(e)}")

    def _apply_fuzzy_filter(
        self,
        tickets: List[Dict[str, Any]],
        search_term: str,
        threshold: float = 0.7,
        fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Apply fuzzy matching filter to a list of tickets."""
        if not search_term:
            return tickets

        if fields is None:
            fields = ['subject', 'description']

        if threshold < 0.0 or threshold > 1.0:
            raise ZendeskValidationError("Threshold must be between 0.0 and 1.0")

        try:
            filtered_tickets = []
            for ticket in tickets:
                best_match_score = 0.0
                best_match_field = None

                # Check similarity against each field
                for field in fields:
                    field_value = ticket.get(field, '')
                    if field_value:
                        similarity = self._calculate_subject_similarity(search_term, str(field_value))
                        if similarity > best_match_score:
                            best_match_score = similarity
                            best_match_field = field

                # Include ticket if similarity meets threshold
                if best_match_score >= threshold:
                    ticket_copy = ticket.copy()
                    ticket_copy['fuzzy_match_score'] = best_match_score
                    ticket_copy['fuzzy_match_field'] = best_match_field
                    ticket_copy['fuzzy_search_term'] = search_term
                    filtered_tickets.append(ticket_copy)

            # Sort by similarity score (highest first)
            filtered_tickets.sort(key=lambda x: x['fuzzy_match_score'], reverse=True)

            return filtered_tickets
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to apply fuzzy filter: {str(e)}")

    def _apply_proximity_filter(
        self,
        tickets: List[Dict[str, Any]],
        terms: List[str],
        max_distance: int = 5,
        fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Apply proximity search filter to find tickets where terms appear within N words of each other."""
        if not terms or len(terms) < 2:
            return tickets

        if fields is None:
            fields = ['subject', 'description']

        if max_distance < 1:
            raise ZendeskValidationError("Max distance must be at least 1")

        try:
            filtered_tickets = []
            for ticket in tickets:
                for field in fields:
                    field_value = ticket.get(field, '')
                    if field_value:
                        # Convert to lowercase and split into words
                        text = str(field_value).lower()
                        words = text.split()

                        # Find positions of each term
                        term_positions = {}
                        for term in terms:
                            term_lower = term.lower()
                            positions = []
                            for i, word in enumerate(words):
                                # Check if word contains the term (for partial matches)
                                if term_lower in word or word in term_lower:
                                    positions.append(i)
                            term_positions[term] = positions

                        # Check if all terms are found
                        if all(positions for positions in term_positions.values()):
                            # Check proximity between any pair of terms
                            found_proximity = False
                            min_distance = float('inf')

                            for i, term1 in enumerate(terms):
                                for j, term2 in enumerate(terms[i+1:], i+1):
                                    for pos1 in term_positions[term1]:
                                        for pos2 in term_positions[term2]:
                                            distance = abs(pos1 - pos2)
                                            if distance <= max_distance:
                                                found_proximity = True
                                                min_distance = min(min_distance, distance)

                            if found_proximity:
                                ticket_copy = ticket.copy()
                                ticket_copy['proximity_match_field'] = field
                                ticket_copy['proximity_terms'] = terms
                                ticket_copy['proximity_distance'] = min_distance
                                ticket_copy['proximity_max_distance'] = max_distance
                                filtered_tickets.append(ticket_copy)
                                break  # Only add ticket once even if multiple fields match

            # Sort by proximity distance (closest first)
            filtered_tickets.sort(key=lambda x: x['proximity_distance'])

            return filtered_tickets
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to apply proximity filter: {str(e)}")

    def _extract_search_terms(self, subject: str) -> str:
        """Extract key search terms from a ticket subject for similarity searches."""
        if not subject:
            return ""

        # Remove common words and clean up
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must', 'help', 'issue', 'problem', 'question', 'request', 'ticket', 'support'}

        # Split into words, remove stop words, and clean
        words = subject.lower().split()
        key_words = [word.strip('.,!?;:"()[]{}') for word in words if word.strip('.,!?;:"()[]{}') not in stop_words and len(word.strip('.,!?;:"()[]{}')) > 2]

        # Take first 3-5 meaningful words
        return ' '.join(key_words[:5])

    def _calculate_subject_similarity(self, subject1: str, subject2: str) -> float:
        """Calculate similarity score between two ticket subjects."""
        if not subject1 or not subject2:
            return 0.0

        # Convert to lowercase for comparison
        s1 = subject1.lower()
        s2 = subject2.lower()

        # Exact match
        if s1 == s2:
            return 1.0

        # Extract words from both subjects
        words1 = set(s1.split())
        words2 = set(s2.split())

        if not words1 or not words2:
            return 0.0

        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        if union == 0:
            return 0.0

        similarity = intersection / union

        # Boost score if one subject contains the other
        if s1 in s2 or s2 in s1:
            similarity = min(1.0, similarity + 0.2)

        return similarity

    def search_tickets_enhanced(
        self,
        query: str,
        regex_pattern: str = None,
        fuzzy_term: str = None,
        fuzzy_threshold: float = 0.7,
        proximity_terms: List[str] = None,
        proximity_distance: int = 5,
        sort_by: str = None,
        sort_order: str = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Enhanced ticket search with client-side filtering capabilities."""
        try:
            if not query:
                raise ZendeskValidationError("Base search query cannot be empty")

            # Get base results from Zendesk
            base_results = self.search_tickets_export(
                query=query,
                sort_by=sort_by,
                sort_order=sort_order,
                max_results=limit * 2  # Get more results to account for filtering
            )

            tickets = base_results.get('tickets', [])

            # Apply client-side filters in sequence
            if regex_pattern:
                tickets = self._apply_regex_filter(tickets, regex_pattern)

            if fuzzy_term:
                tickets = self._apply_fuzzy_filter(tickets, fuzzy_term, fuzzy_threshold)

            if proximity_terms and len(proximity_terms) >= 2:
                tickets = self._apply_proximity_filter(tickets, proximity_terms, proximity_distance)

            # Apply final limit
            tickets = tickets[:limit]

            # Build response
            response = {
                'tickets': tickets,
                'count': len(tickets),
                'query': query,
                'sort_by': sort_by,
                'sort_order': sort_order,
                'limit': limit,
                'enhancements_applied': []
            }

            # Add enhancement metadata
            if regex_pattern:
                response['enhancements_applied'].append(f"regex_pattern: {regex_pattern}")
            if fuzzy_term:
                response['enhancements_applied'].append(f"fuzzy_term: {fuzzy_term} (threshold: {fuzzy_threshold})")
            if proximity_terms:
                response['enhancements_applied'].append(f"proximity_terms: {proximity_terms} (distance: {proximity_distance})")

            response['enhancements_applied'] = ', '.join(response['enhancements_applied']) if response['enhancements_applied'] else 'none'

            return response
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to perform enhanced search: {str(e)}")

    def build_search_query(
        self,
        status: str = None,
        priority: str = None,
        assignee: str = None,
        requester: str = None,
        organization: str = None,
        tags: List[str] = None,
        tags_logic: str = "OR",
        exclude_tags: List[str] = None,
        created_after: str = None,
        created_before: str = None,
        updated_after: str = None,
        updated_before: str = None,
        solved_after: str = None,
        solved_before: str = None,
        due_after: str = None,
        due_before: str = None,
        custom_fields: Dict[str, Any] = None,
        subject_contains: str = None,
        description_contains: str = None,
        comment_contains: str = None
    ) -> Dict[str, Any]:
        """Build a Zendesk search query from structured parameters."""
        try:
            query_parts = []

            # Basic fields
            if status:
                query_parts.append(f"status:{status}")

            if priority:
                query_parts.append(f"priority:{priority}")

            if assignee:
                if assignee.lower() == "none":
                    query_parts.append("assignee:none")
                else:
                    query_parts.append(f"assignee:{assignee}")

            if requester:
                query_parts.append(f"requester:{requester}")

            if organization:
                query_parts.append(f'organization:"{organization}"')

            # Tags
            if tags:
                if tags_logic.upper() == "AND":
                    for tag in tags:
                        query_parts.append(f"tags:{tag}")
                else:  # OR logic
                    tag_query = " ".join([f"tags:{tag}" for tag in tags])
                    query_parts.append(tag_query)

            if exclude_tags:
                for tag in exclude_tags:
                    query_parts.append(f"-tags:{tag}")

            # Date ranges
            if created_after:
                query_parts.append(f"created>={created_after}")
            if created_before:
                query_parts.append(f"created<={created_before}")

            if updated_after:
                query_parts.append(f"updated>={updated_after}")
            if updated_before:
                query_parts.append(f"updated<={updated_before}")

            if solved_after:
                query_parts.append(f"solved>={solved_after}")
            if solved_before:
                query_parts.append(f"solved<={solved_before}")

            if due_after:
                query_parts.append(f"due>={due_after}")
            if due_before:
                query_parts.append(f"due<={due_before}")

            # Custom fields
            if custom_fields:
                for field_id, value in custom_fields.items():
                    if isinstance(value, str) and " " in value:
                        query_parts.append(f'custom_field_{field_id}:"{value}"')
                    else:
                        query_parts.append(f"custom_field_{field_id}:{value}")

            # Text searches
            if subject_contains:
                query_parts.append(f'subject:"{subject_contains}"')

            if description_contains:
                query_parts.append(f'description:"{description_contains}"')

            if comment_contains:
                query_parts.append(f'comment:"{comment_contains}"')

            # Build final query
            query_string = " ".join(query_parts) if query_parts else "*"

            # Generate examples
            examples = []
            if query_string != "*":
                examples.append(f"Generated query: {query_string}")

            # Add common examples
            examples.extend([
                "status:open priority:high",
                "tags:bug tags:urgent",
                "assignee:none created>2024-01-01",
                'organization:"Acme Corp" -tags:spam',
                "subject:login* description:password"
            ])

            return {
                "query": query_string,
                "examples": examples,
                "parameters_used": {
                    "status": status,
                    "priority": priority,
                    "assignee": assignee,
                    "requester": requester,
                    "organization": organization,
                    "tags": tags,
                    "tags_logic": tags_logic,
                    "exclude_tags": exclude_tags,
                    "created_after": created_after,
                    "created_before": created_before,
                    "updated_after": updated_after,
                    "updated_before": updated_before,
                    "solved_after": solved_after,
                    "solved_before": solved_before,
                    "due_after": due_after,
                    "due_before": due_before,
                    "custom_fields": custom_fields,
                    "subject_contains": subject_contains,
                    "description_contains": description_contains,
                    "comment_contains": comment_contains
                }
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to build search query: {str(e)}")

    def get_search_statistics(
        self,
        query: str,
        sort_by: str = None,
        sort_order: str = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """Analyze search results and return aggregated statistics."""
        try:
            # Get search results
            results = self.search_tickets_export(
                query=query,
                sort_by=sort_by,
                sort_order=sort_order,
                max_results=limit
            )

            tickets = results.get('tickets', [])
            if not tickets:
                return {
                    'query': query,
                    'total_tickets': 0,
                    'statistics': {},
                    'message': 'No tickets found for analysis'
                }

            # Initialize counters
            status_counts = {}
            priority_counts = {}
            assignee_counts = {}
            requester_counts = {}
            organization_counts = {}
            tag_counts = {}
            date_counts = {}
            resolution_times = []

            # Analyze each ticket
            for ticket in tickets:
                # Status counts
                status = ticket.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1

                # Priority counts
                priority = ticket.get('priority', 'unknown')
                priority_counts[priority] = priority_counts.get(priority, 0) + 1

                # Assignee counts
                assignee_id = ticket.get('assignee_id')
                if assignee_id:
                    assignee_counts[assignee_id] = assignee_counts.get(assignee_id, 0) + 1

                # Requester counts
                requester_id = ticket.get('requester_id')
                if requester_id:
                    requester_counts[requester_id] = requester_counts.get(requester_id, 0) + 1

                # Organization counts
                org_id = ticket.get('organization_id')
                if org_id:
                    organization_counts[org_id] = organization_counts.get(org_id, 0) + 1

                # Tag counts
                tags = ticket.get('tags', [])
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

                # Date analysis (by month)
                created_at = ticket.get('created_at', '')
                if created_at:
                    try:
                        date_obj = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        month_key = f"{date_obj.year}-{date_obj.month:02d}"
                        date_counts[month_key] = date_counts.get(month_key, 0) + 1
                    except:
                        pass

                # Resolution time calculation (for solved tickets)
                if status == 'solved':
                    try:
                        created = datetime.fromisoformat(ticket.get('created_at', '').replace('Z', '+00:00'))
                        updated = datetime.fromisoformat(ticket.get('updated_at', '').replace('Z', '+00:00'))
                        resolution_time = (updated - created).total_seconds() / 3600  # hours
                        resolution_times.append(resolution_time)
                    except:
                        pass

            # Calculate averages
            avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0

            # Top requesters and organizations
            top_requesters = sorted(requester_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            top_organizations = sorted(organization_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            return {
                'query': query,
                'total_tickets': len(tickets),
                'statistics': {
                    'by_status': status_counts,
                    'by_priority': priority_counts,
                    'by_assignee': dict(sorted(assignee_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
                    'by_requester': dict(top_requesters),
                    'by_organization': dict(top_organizations),
                    'by_tags': dict(top_tags),
                    'by_month': dict(sorted(date_counts.items())),
                    'resolution_time': {
                        'average_hours': round(avg_resolution_time, 2),
                        'total_solved': len(resolution_times),
                        'min_hours': round(min(resolution_times), 2) if resolution_times else 0,
                        'max_hours': round(max(resolution_times), 2) if resolution_times else 0
                    }
                },
                'summary': {
                    'most_common_status': max(status_counts.items(), key=lambda x: x[1])[0] if status_counts else None,
                    'most_common_priority': max(priority_counts.items(), key=lambda x: x[1])[0] if priority_counts else None,
                    'most_active_requester': top_requesters[0] if top_requesters else None,
                    'most_active_organization': top_organizations[0] if top_organizations else None,
                    'most_common_tag': top_tags[0] if top_tags else None,
                    'unassigned_tickets': len(tickets) - sum(assignee_counts.values()),
                    'avg_resolution_time_hours': round(avg_resolution_time, 2)
                }
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to generate search statistics: {str(e)}")

    def search_by_date_range(
        self,
        date_field: str = "created",
        range_type: str = "custom",
        start_date: str = None,
        end_date: str = None,
        relative_period: str = None,
        sort_by: str = None,
        sort_order: str = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Search tickets by date range with support for relative dates."""
        try:
            # Handle relative periods
            if range_type == "relative" and relative_period:
                now = datetime.now()
                if relative_period == "last_7_days":
                    start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
                    end_date = now.strftime('%Y-%m-%d')
                elif relative_period == "last_30_days":
                    start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
                    end_date = now.strftime('%Y-%m-%d')
                elif relative_period == "this_month":
                    start_date = now.replace(day=1).strftime('%Y-%m-%d')
                    end_date = now.strftime('%Y-%m-%d')
                elif relative_period == "last_month":
                    last_month = now.replace(day=1) - timedelta(days=1)
                    start_date = last_month.replace(day=1).strftime('%Y-%m-%d')
                    end_date = last_month.strftime('%Y-%m-%d')
                elif relative_period == "this_quarter":
                    quarter_start = now.replace(month=((now.month-1)//3)*3+1, day=1)
                    start_date = quarter_start.strftime('%Y-%m-%d')
                    end_date = now.strftime('%Y-%m-%d')
                elif relative_period == "last_quarter":
                    quarter_start = now.replace(month=((now.month-1)//3)*3+1, day=1)
                    last_quarter_start = quarter_start - timedelta(days=90)
                    start_date = last_quarter_start.strftime('%Y-%m-%d')
                    end_date = quarter_start.strftime('%Y-%m-%d')

            # Build query
            query_parts = []
            if start_date:
                query_parts.append(f"{date_field}>={start_date}")
            if end_date:
                query_parts.append(f"{date_field}<={end_date}")

            query = " ".join(query_parts) if query_parts else "*"

            return self.search_tickets_export(
                query=query,
                sort_by=sort_by,
                sort_order=sort_order,
                max_results=limit
            )
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to search by date range: {str(e)}")

    def search_by_tags_advanced(
        self,
        include_tags: List[str] = None,
        exclude_tags: List[str] = None,
        tag_logic: str = "OR",
        sort_by: str = None,
        sort_order: str = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Advanced tag-based search with AND/OR/NOT logic."""
        try:
            query_parts = []

            # Include tags
            if include_tags:
                if tag_logic.upper() == "AND":
                    for tag in include_tags:
                        query_parts.append(f"tags:{tag}")
                else:  # OR logic
                    tag_query = " ".join([f"tags:{tag}" for tag in include_tags])
                    query_parts.append(tag_query)

            # Exclude tags
            if exclude_tags:
                for tag in exclude_tags:
                    query_parts.append(f"-tags:{tag}")

            query = " ".join(query_parts) if query_parts else "*"

            return self.search_tickets_export(
                query=query,
                sort_by=sort_by,
                sort_order=sort_order,
                max_results=limit
            )
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to search by tags: {str(e)}")

    def search_by_integration_source(
        self,
        channel: str,
        sort_by: str | None = None,
        sort_order: str | None = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Search for tickets created via a specific integration source/channel."""
        try:
            if not channel:
                raise ZendeskValidationError("Channel cannot be empty")

            # Build query using Zendesk's via.channel syntax
            query = f"via.channel:{channel}"

            # Use existing search_tickets_export method with the channel query
            return self.search_tickets_export(
                query=query,
                sort_by=sort_by,
                sort_order=sort_order,
                max_results=limit
            )
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to search by integration source {channel}: {str(e)}")

    async def batch_search_tickets(
        self,
        queries: List[str],
        deduplicate: bool = True,
        sort_by: str = None,
        sort_order: str = None,
        limit_per_query: int = 100
    ) -> Dict[str, Any]:
        """Execute multiple searches concurrently and return grouped results."""
        try:
            import asyncio

            sem = asyncio.Semaphore(3)

            async def execute_search(query):
                # Limit concurrent export calls to avoid hitting rate limits
                async with sem:
                    return await asyncio.to_thread(
                        self.search_tickets_export,
                        query=query,
                        sort_by=sort_by,
                        sort_order=sort_order,
                        max_results=limit_per_query
                    )

            # Execute searches concurrently using existing event loop
            tasks = [execute_search(query) for query in queries]
            results = await asyncio.gather(*tasks)

            # Process results
            query_results = {}
            all_tickets = []
            total_execution_time = 0

            for i, (query, result) in enumerate(zip(queries, results)):
                tickets = result.get('tickets', [])
                query_results[f"query_{i+1}"] = {
                    "query": query,
                    "tickets": tickets,
                    "count": len(tickets),
                    "execution_time_ms": result.get('execution_time_ms', 0)
                }
                all_tickets.extend(tickets)
                total_execution_time += result.get('execution_time_ms', 0)

            # Deduplicate if requested
            if deduplicate and all_tickets:
                seen_ids = set()
                unique_tickets = []
                for ticket in all_tickets:
                    ticket_id = ticket.get('id')
                    if ticket_id not in seen_ids:
                        seen_ids.add(ticket_id)
                        unique_tickets.append(ticket)
                all_tickets = unique_tickets

            return {
                "queries_executed": len(queries),
                "total_tickets": len(all_tickets),
                "unique_tickets": len(all_tickets) if deduplicate else sum(len(r["tickets"]) for r in query_results.values()),
                "total_execution_time_ms": total_execution_time,
                "query_results": query_results,
                "all_tickets": all_tickets if deduplicate else None,
                "deduplication_applied": deduplicate
            }
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to execute batch search: {str(e)}")

    def get_case_volume_analytics(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        max_results: int | None = None,
        include_metrics: List[str] | None = None,
        group_by: List[str] | None = None,
        filter_by_status: List[str] | None = None,
        filter_by_priority: List[str] | None = None,
        filter_by_tags: List[str] | None = None,
        time_bucket: str = "weekly",
    ) -> Dict[str, Any]:
        """Aggregate comprehensive ticket analytics by week, month, and technician.

        Args:
            start_date: Inclusive start date in ISO format (YYYY-MM-DD). Defaults to encompass
                the last 13 weeks and 12 months relative to the end date.
            end_date: Inclusive end date in ISO format (YYYY-MM-DD). Defaults to today (UTC).
            max_results: Optional safety cap for search export results.
            include_metrics: List of metric types to include. Options: 'response_times', 
                'resolution_times', 'channels', 'forms', 'assignments', 'status_transitions', 
                'satisfaction'. If None, includes all metrics.
            group_by: List of dimensions to group by. Options: 'channel', 'form', 'priority', 
                'type', 'group_id', 'tags', 'requester', 'organization', 'custom_fields'. 
                If None, only groups by time and assignee.
            filter_by_status: Filter tickets to specific statuses. If None, includes all statuses.
            filter_by_priority: Filter tickets to specific priorities. If None, includes all priorities.
            filter_by_tags: Filter tickets to those containing any of the specified tags. 
                If None, includes all tickets.
            time_bucket: Time bucketing granularity. Options: 'daily', 'weekly', 'monthly'. 
                Defaults to 'weekly'.

        Returns:
            Dictionary containing comprehensive analytics including volumes, time metrics,
            channel breakdowns, assignment metrics, requester analytics, organization analytics,
            custom field analytics, and more.
        """

        def _parse_iso_date(value: str) -> date:
            try:
                return datetime.fromisoformat(value).date()
            except ValueError as exc:
                raise ZendeskValidationError(
                    f"Invalid date format '{value}'. Expected YYYY-MM-DD."
                ) from exc

        def _shift_month(base: date, offset: int) -> date:
            # Shift month preserving day when possible; clamp to last day of month.
            month_index = base.month - 1 + offset
            year = base.year + month_index // 12
            month = month_index % 12 + 1
            last_day = calendar.monthrange(year, month)[1]
            day = min(base.day, last_day)
            return date(year, month, day)

        today = datetime.now(timezone.utc).date()
        end_dt = _parse_iso_date(end_date) if end_date else today

        if start_date:
            start_dt = _parse_iso_date(start_date)
        else:
            # Default range ensures coverage of last 13 weeks and 12 months.
            current_week_start = end_dt - timedelta(days=end_dt.weekday())
            weekly_start = current_week_start - timedelta(weeks=12)

            current_month_start = end_dt.replace(day=1)
            monthly_start = _shift_month(current_month_start, -11)

            start_dt = weekly_start if weekly_start <= monthly_start else monthly_start

        if start_dt > end_dt:
            raise ZendeskValidationError("start_date must be on or before end_date")

        # Build created date query range for Zendesk search.
        query_parts: List[str] = []
        if start_dt:
            query_parts.append(f"created>={start_dt.isoformat()}")
        if end_dt:
            query_parts.append(f"created<={end_dt.isoformat()}")
        query = " ".join(query_parts) if query_parts else "*"

        results = self.search_tickets_export(
            query=query,
            sort_by="created_at",
            sort_order="asc",
            max_results=max_results,
        )

        tickets = results.get("tickets", [])
        
        # Determine which metrics to include (default: all)
        if include_metrics is None:
            include_metrics = ['response_times', 'resolution_times', 'channels', 'forms', 
                              'assignments', 'status_transitions', 'satisfaction']
        
        # Apply filters
        if filter_by_status:
            tickets = [t for t in tickets if t.get('status') in filter_by_status]
        if filter_by_priority:
            tickets = [t for t in tickets if t.get('priority') in filter_by_priority]
        if filter_by_tags:
            tickets = [t for t in tickets if any(tag in (t.get('tags') or []) for tag in filter_by_tags)]

        # Initialize all aggregation structures
        weekly_counts: defaultdict[str, int] = defaultdict(int)
        monthly_counts: defaultdict[str, int] = defaultdict(int)
        daily_counts: defaultdict[str, int] = defaultdict(int)
        technician_weekly: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
        status_counts: defaultdict[str, int] = defaultdict(int)
        priority_counts: defaultdict[str, int] = defaultdict(int)
        type_counts: defaultdict[str, int] = defaultdict(int)
        
        # Time-based metrics
        response_times: List[float] = []
        first_resolution_times: List[float] = []
        full_resolution_times: List[float] = []
        agent_wait_times: List[float] = []
        requester_wait_times: List[float] = []
        on_hold_times: List[float] = []
        
        # Channel/source metrics
        channel_counts: defaultdict[str, int] = defaultdict(int)
        form_counts: defaultdict[int, int] = defaultdict(int)
        group_counts: defaultdict[int, int] = defaultdict(int)
        
        # Assignment metrics
        reassignment_counts: defaultdict[str, int] = defaultdict(int)
        assignment_times: List[float] = []
        
        # Status transition metrics
        status_transition_counts: defaultdict[str, int] = defaultdict(int)
        time_in_status: defaultdict[str, List[float]] = defaultdict(list)
        
        # Satisfaction metrics
        satisfaction_scores: List[int] = []
        satisfaction_counts: defaultdict[int, int] = defaultdict(int)
        
        # Tag metrics
        tag_counts: defaultdict[str, int] = defaultdict(int)
        tag_weekly_counts: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        # Requester metrics
        requester_weekly: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
        requester_counts: defaultdict[int, int] = defaultdict(int)
        
        # Organization metrics
        organization_weekly: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
        organization_counts: defaultdict[int, int] = defaultdict(int)
        
        # Custom field metrics
        custom_field_counts: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
        custom_field_weekly_counts: defaultdict[str, defaultdict[str, defaultdict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        
        # Grouped metrics (if group_by specified)
        grouped_counts: Dict[str, Dict[str, int]] = {}
        if group_by:
            for group_dim in group_by:
                grouped_counts[group_dim] = {}

        # Helper to ensure weeks/months/days are generated sequentially.
        def _generate_week_keys(start_week: date, end_week: date) -> List[str]:
            weeks: List[str] = []
            current = start_week
            while current <= end_week:
                iso_year, iso_week, _ = current.isocalendar()
                weeks.append(f"{iso_year}-W{iso_week:02d}")
                current += timedelta(weeks=1)
            return weeks

        def _generate_month_keys(start_month: date, end_month: date) -> List[str]:
            months: List[str] = []
            current = start_month
            while current <= end_month:
                months.append(f"{current.year}-{current.month:02d}")
                current = _shift_month(current, 1)
            return months

        def _generate_daily_keys(start_day: date, end_day: date) -> List[str]:
            days: List[str] = []
            current = start_day
            while current <= end_day:
                days.append(current.isoformat())
                current += timedelta(days=1)
            return days

        # Precompute canonical sequences for zero filling based on time_bucket
        end_week_start = end_dt - timedelta(days=end_dt.weekday())
        start_week_start = start_dt - timedelta(days=start_dt.weekday())
        week_sequence = _generate_week_keys(start_week_start, end_week_start)

        end_month_start = end_dt.replace(day=1)
        start_month_start = start_dt.replace(day=1)
        month_sequence = _generate_month_keys(start_month_start, end_month_start)
        
        daily_sequence = _generate_daily_keys(start_dt, end_dt)

        total_tickets = 0
        assigned_tickets = 0

        for ticket in tickets:
            created_at = ticket.get("created_at")
            if not created_at:
                continue

            try:
                created_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            except ValueError:
                # Skip tickets with unparseable dates
                continue

            created_date = created_dt.date()
            if created_date < start_dt or created_date > end_dt:
                continue

            # Time bucket keys
            iso_year, iso_week, _ = created_date.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            month_key = f"{created_date.year}-{created_date.month:02d}"
            day_key = created_date.isoformat()

            # Basic counts
            weekly_counts[week_key] += 1
            monthly_counts[month_key] += 1
            daily_counts[day_key] += 1

            # Status, priority, type counts
            status = ticket.get("status", "unknown") or "unknown"
            status_counts[status] += 1
            priority = ticket.get("priority", "unknown") or "unknown"
            priority_counts[priority] += 1
            ticket_type = ticket.get("type") or "unknown"
            type_counts[ticket_type] += 1

            # Assignee metrics
            assignee_id = ticket.get("assignee_id")
            assignee_key = str(assignee_id) if assignee_id is not None else "unassigned"
            technician_weekly[assignee_key][week_key] += 1

            total_tickets += 1
            if assignee_id is not None:
                assigned_tickets += 1

            # Channel/source metrics
            if 'channels' in include_metrics:
                via = ticket.get("via")
                if via and via.get("channel"):
                    channel = via.get("channel")
                    channel_counts[channel] += 1
                    if 'channel' in (group_by or []):
                        grouped_counts['channel'][channel] = grouped_counts['channel'].get(channel, 0) + 1

            # Form metrics
            if 'forms' in include_metrics:
                form_id = ticket.get("ticket_form_id")
                if form_id:
                    form_counts[form_id] += 1
                    if 'form' in (group_by or []):
                        grouped_counts['form'][str(form_id)] = grouped_counts['form'].get(str(form_id), 0) + 1

            # Group metrics
            group_id = ticket.get("group_id")
            if group_id:
                group_counts[group_id] += 1
                if 'group_id' in (group_by or []):
                    grouped_counts['group_id'][str(group_id)] = grouped_counts['group_id'].get(str(group_id), 0) + 1

            # Time-based metrics
            metrics = ticket.get("metrics", {})
            if metrics:
                if 'response_times' in include_metrics:
                    reply_time = metrics.get("reply_time_in_seconds")
                    if reply_time is not None:
                        response_times.append(float(reply_time))
                    
                    agent_wait = metrics.get("agent_wait_time_in_seconds")
                    if agent_wait is not None:
                        agent_wait_times.append(float(agent_wait))
                    
                    requester_wait = metrics.get("requester_wait_time_in_seconds")
                    if requester_wait is not None:
                        requester_wait_times.append(float(requester_wait))

                if 'resolution_times' in include_metrics:
                    first_res = metrics.get("first_resolution_time_in_seconds")
                    if first_res is not None:
                        first_resolution_times.append(float(first_res))
                    
                    full_res = metrics.get("full_resolution_time_in_seconds")
                    if full_res is not None:
                        full_resolution_times.append(float(full_res))
                    
                    on_hold = metrics.get("on_hold_time_in_seconds")
                    if on_hold is not None:
                        on_hold_times.append(float(on_hold))

            # Assignment metrics (basic - would need audits for full history)
            if 'assignments' in include_metrics and assignee_id:
                # First assignment time approximation (created to updated)
                try:
                    updated_dt = datetime.fromisoformat(str(ticket.get("updated_at", "")).replace("Z", "+00:00"))
                    assignment_duration = (updated_dt - created_dt).total_seconds()
                    if assignment_duration > 0:
                        assignment_times.append(assignment_duration)
                except (ValueError, TypeError):
                    pass

            # Status transition metrics (basic - would need audits for full history)
            if 'status_transitions' in include_metrics:
                status_transition_counts[status] += 1
                # Calculate time in current status (created to updated)
                try:
                    updated_dt = datetime.fromisoformat(str(ticket.get("updated_at", "")).replace("Z", "+00:00"))
                    time_in_status_seconds = (updated_dt - created_dt).total_seconds()
                    if time_in_status_seconds > 0:
                        time_in_status[status].append(time_in_status_seconds)
                except (ValueError, TypeError):
                    pass

            # Satisfaction metrics
            if 'satisfaction' in include_metrics:
                satisfaction = ticket.get("satisfaction_rating")
                if satisfaction and satisfaction.get("score") is not None:
                    score = satisfaction.get("score")
                    satisfaction_scores.append(score)
                    satisfaction_counts[score] += 1

            # Tag metrics
            tags = ticket.get("tags", [])
            if tags:
                for tag in tags:
                    tag_counts[tag] += 1
                    tag_weekly_counts[tag][week_key] += 1
                    if 'tags' in (group_by or []):
                        grouped_counts['tags'][tag] = grouped_counts['tags'].get(tag, 0) + 1

            # Requester metrics
            requester_id = ticket.get("requester_id")
            if requester_id is not None:
                requester_key = str(requester_id)
                requester_weekly[requester_key][week_key] += 1
                requester_counts[requester_id] += 1
                if 'requester' in (group_by or []):
                    grouped_counts['requester'][requester_key] = grouped_counts['requester'].get(requester_key, 0) + 1

            # Organization metrics
            organization_id = ticket.get("organization_id")
            if organization_id is not None:
                org_key = str(organization_id)
                organization_weekly[org_key][week_key] += 1
                organization_counts[organization_id] += 1
                if 'organization' in (group_by or []):
                    grouped_counts['organization'][org_key] = grouped_counts['organization'].get(org_key, 0) + 1

            # Custom field metrics
            custom_fields = ticket.get("custom_fields", [])
            if custom_fields:
                for cf in custom_fields:
                    field_id = cf.get("id")
                    field_value = cf.get("value")
                    if field_id is not None and field_value is not None:
                        field_id_str = str(field_id)
                        field_value_str = str(field_value)
                        custom_field_counts[field_id_str][field_value_str] += 1
                        custom_field_weekly_counts[field_id_str][field_value_str][week_key] += 1
                        if 'custom_fields' in (group_by or []):
                            # Group by field_id:value combination
                            group_key = f"{field_id_str}:{field_value_str}"
                            grouped_counts['custom_fields'][group_key] = grouped_counts['custom_fields'].get(group_key, 0) + 1

            # Grouped metrics
            if group_by:
                if 'priority' in group_by:
                    grouped_counts['priority'][priority] = grouped_counts['priority'].get(priority, 0) + 1
                if 'type' in group_by:
                    grouped_counts['type'][ticket_type] = grouped_counts['type'].get(ticket_type, 0) + 1

        # Helper function to calculate statistics from a list of values
        def _calc_stats(values: List[float]) -> Dict[str, float]:
            if not values:
                return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0, "median": 0.0}
            sorted_vals = sorted(values)
            count = len(sorted_vals)
            avg = sum(sorted_vals) / count
            min_val = sorted_vals[0]
            max_val = sorted_vals[-1]
            median = sorted_vals[count // 2] if count % 2 == 1 else (sorted_vals[count // 2 - 1] + sorted_vals[count // 2]) / 2
            return {
                "count": count,
                "avg": round(avg, 2),
                "min": round(min_val, 2),
                "max": round(max_val, 2),
                "median": round(median, 2),
            }

        # Build time series based on time_bucket
        if time_bucket == "daily":
            time_series = [
                {"date": day, "count": daily_counts.get(day, 0)}
                for day in daily_sequence
            ]
        elif time_bucket == "monthly":
            time_series = [
                {"month": month, "count": monthly_counts.get(month, 0)}
                for month in month_sequence
            ]
        else:  # weekly (default)
            time_series = [
                {"week": week, "count": weekly_counts.get(week, 0)}
                for week in week_sequence
            ]

        weekly_series = [
            {"week": week, "count": weekly_counts.get(week, 0)}
            for week in week_sequence
        ]

        monthly_series = [
            {"month": month, "count": monthly_counts.get(month, 0)}
            for month in month_sequence
        ]

        daily_series = [
            {"date": day, "count": daily_counts.get(day, 0)}
            for day in daily_sequence
        ]

        technician_series = []
        for assignee_key, counts in sorted(technician_weekly.items(), key=lambda item: item[0]):
            technician_series.append(
                {
                    "assignee_id": None if assignee_key == "unassigned" else (
                        int(assignee_key) if assignee_key.isdigit() else assignee_key
                    ),
                    "display_key": assignee_key,
                    "weeks": [
                        {"week": week, "count": counts.get(week, 0)}
                        for week in week_sequence
                    ],
                    "total": sum(counts.get(week, 0) for week in week_sequence),
                }
            )

        # Build comprehensive response
        response = {
            "query": query,
            "range": {
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
                "weeks": len(week_sequence),
                "months": len(month_sequence),
                "days": len(daily_sequence),
                "time_bucket": time_bucket,
            },
            "totals": {
                "tickets": total_tickets,
                "assigned_tickets": assigned_tickets,
                "unassigned_tickets": total_tickets - assigned_tickets,
                "status_breakdown": dict(sorted(status_counts.items(), key=lambda item: item[0])),
                "priority_breakdown": dict(sorted(priority_counts.items(), key=lambda item: item[0])),
                "type_breakdown": dict(sorted(type_counts.items(), key=lambda item: item[0])),
            },
            "time_series": time_series,
            "weekly_counts": weekly_series,
            "monthly_counts": monthly_series,
            "daily_counts": daily_series,
            "technician_weekly_counts": technician_series,
        }

        # Add time-based metrics
        if 'response_times' in include_metrics:
            response["response_time_metrics"] = {
                "reply_time": _calc_stats(response_times),
                "agent_wait_time": _calc_stats(agent_wait_times),
                "requester_wait_time": _calc_stats(requester_wait_times),
            }

        if 'resolution_times' in include_metrics:
            response["resolution_time_metrics"] = {
                "first_resolution_time": _calc_stats(first_resolution_times),
                "full_resolution_time": _calc_stats(full_resolution_times),
                "on_hold_time": _calc_stats(on_hold_times),
            }

        # Add channel/source metrics
        if 'channels' in include_metrics:
            response["channel_breakdown"] = dict(sorted(channel_counts.items(), key=lambda x: x[1], reverse=True))

        if 'forms' in include_metrics:
            response["form_breakdown"] = {str(k): v for k, v in sorted(form_counts.items(), key=lambda x: x[1], reverse=True)}

        if group_counts:
            response["group_breakdown"] = {str(k): v for k, v in sorted(group_counts.items(), key=lambda x: x[1], reverse=True)}

        # Add assignment metrics
        if 'assignments' in include_metrics:
            response["assignment_metrics"] = {
                "assignment_times": _calc_stats(assignment_times),
            }

        # Add status transition metrics
        if 'status_transitions' in include_metrics:
            status_time_stats = {
                status: _calc_stats(times) 
                for status, times in time_in_status.items()
            }
            response["status_transition_metrics"] = {
                "status_counts": dict(sorted(status_transition_counts.items(), key=lambda x: x[1], reverse=True)),
                "time_in_status": status_time_stats,
            }

        # Add satisfaction metrics
        if 'satisfaction' in include_metrics:
            avg_satisfaction = sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else 0
            response["satisfaction_metrics"] = {
                "average_score": round(avg_satisfaction, 2),
                "total_ratings": len(satisfaction_scores),
                "score_distribution": dict(sorted(satisfaction_counts.items())),
            }

        # Add tag metrics
        if tag_counts:
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            tag_breakdown = {tag: count for tag, count in top_tags}
            
            # Build tag weekly series
            tag_weekly_series = []
            for tag, weekly_counts_dict in sorted(tag_weekly_counts.items(), key=lambda x: sum(x[1].values()), reverse=True):
                tag_weekly_series.append({
                    "tag": tag,
                    "total": tag_counts[tag],
                    "weeks": [
                        {"week": week, "count": weekly_counts_dict.get(week, 0)}
                        for week in week_sequence
                    ],
                })
            
            response["tag_breakdown"] = tag_breakdown
            response["tag_weekly_counts"] = tag_weekly_series[:50]  # Limit to top 50 tags to avoid huge responses

        # Add requester analytics
        if requester_counts:
            requester_series = []
            for requester_key, counts in sorted(requester_weekly.items(), key=lambda item: sum(item[1].values()), reverse=True):
                requester_series.append({
                    "requester_id": int(requester_key) if requester_key.isdigit() else requester_key,
                    "display_key": requester_key,
                    "total": requester_counts[int(requester_key)] if requester_key.isdigit() else requester_counts.get(requester_key, 0),
                    "weeks": [
                        {"week": week, "count": counts.get(week, 0)}
                        for week in week_sequence
                    ],
                })
            response["requester_weekly_counts"] = requester_series
            response["requester_breakdown"] = {str(k): v for k, v in sorted(requester_counts.items(), key=lambda x: x[1], reverse=True)}

        # Add organization analytics
        if organization_counts:
            organization_series = []
            for org_key, counts in sorted(organization_weekly.items(), key=lambda item: sum(item[1].values()), reverse=True):
                organization_series.append({
                    "organization_id": int(org_key) if org_key.isdigit() else org_key,
                    "display_key": org_key,
                    "total": organization_counts[int(org_key)] if org_key.isdigit() else organization_counts.get(org_key, 0),
                    "weeks": [
                        {"week": week, "count": counts.get(week, 0)}
                        for week in week_sequence
                    ],
                })
            response["organization_weekly_counts"] = organization_series
            response["organization_breakdown"] = {str(k): v for k, v in sorted(organization_counts.items(), key=lambda x: x[1], reverse=True)}

        # Add custom field analytics
        if custom_field_counts:
            custom_field_breakdown = {}
            custom_field_weekly_series = []
            
            # Build breakdown by field ID, then by value
            for field_id, value_counts in sorted(custom_field_counts.items(), key=lambda x: sum(x[1].values()), reverse=True):
                # Top values for this field
                top_values = sorted(value_counts.items(), key=lambda x: x[1], reverse=True)[:20]  # Limit to top 20 values per field
                custom_field_breakdown[field_id] = {value: count for value, count in top_values}
                
                # Build weekly series for top values of this field
                field_weekly = custom_field_weekly_counts.get(field_id, {})
                for value, count in top_values:
                    weekly_counts_dict = field_weekly.get(value, {})
                    custom_field_weekly_series.append({
                        "field_id": field_id,
                        "value": value,
                        "total": count,
                        "weeks": [
                            {"week": week, "count": weekly_counts_dict.get(week, 0)}
                            for week in week_sequence
                        ],
                    })
            
            response["custom_field_breakdown"] = custom_field_breakdown
            response["custom_field_weekly_counts"] = custom_field_weekly_series[:100]  # Limit to top 100 field:value combinations

        # Add grouped metrics
        if group_by and grouped_counts:
            response["grouped_breakdowns"] = {
                dim: dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
                for dim, counts in grouped_counts.items()
            }

        if max_results is not None:
            response["max_results"] = max_results

        response["included_metrics"] = include_metrics
        response["group_by"] = group_by

        return response

