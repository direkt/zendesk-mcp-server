from typing import Dict, Any, List
import json
import urllib.request
import urllib.parse
import base64
import os

from zenpy import Zenpy
from zenpy.lib.api_objects import Comment
from zenpy.lib.api_objects import Ticket as ZenpyTicket



# Helper: urllib request with 429 retry/backoff
# Exponential backoff with jitter for HTTP 429 responses
# Kept module-agnostic so it can be reused across direct API calls

def _urlopen_with_retry(req, max_attempts: int = 5):
    import time
    import random
    import urllib.request
    import urllib.error

    last_err = None
    for attempt in range(max_attempts):
        try:
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            # Retry on 429 Too Many Requests
            if getattr(e, 'code', None) == 429 and attempt < max_attempts - 1:
                delay = min(2 ** attempt + random.random(), 30)
                time.sleep(delay)
                last_err = e
                continue
            # Re-raise other HTTP errors immediately
            raise
    # If we exhausted retries, re-raise the last 429 error
    if last_err:
        raise last_err

class ZendeskClient:
    def __init__(self, subdomain: str, email: str, token: str):
        """
        Initialize the Zendesk client using zenpy lib and direct API.
        """
        self.client = Zenpy(
            subdomain=subdomain,
            email=email,
            token=token
        )

        # For direct API calls
        self.subdomain = subdomain
        self.email = email
        self.token = token
        self.base_url = f"https://{subdomain}.zendesk.com/api/v2"
        # Create basic auth header
        credentials = f"{email}/token:{token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode('ascii')
        self.auth_header = f"Basic {encoded_credentials}"

    def get_ticket(self, ticket_id: int) -> Dict[str, Any]:
        """
        Query a ticket by its ID
        """
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
            raise Exception(f"Failed to get ticket {ticket_id}: {str(e)}")

    def get_ticket_comments(self, ticket_id: int) -> List[Dict[str, Any]]:
        """
        Get all comments for a specific ticket.
        """
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
            raise Exception(f"Failed to get comments for ticket {ticket_id}: {str(e)}")

    def post_comment(self, ticket_id: int, comment: str, public: bool = True) -> str:
        """
        Post a comment to an existing ticket.
        """
        try:
            ticket = self.client.tickets(id=ticket_id)
            ticket.comment = Comment(
                html_body=comment,
                public=public
            )
            self.client.tickets.update(ticket)
            return comment
        except Exception as e:
            raise Exception(f"Failed to post comment on ticket {ticket_id}: {str(e)}")

    def get_tickets(self, page: int = 1, per_page: int = 25, sort_by: str = 'created_at', sort_order: str = 'desc') -> Dict[str, Any]:
        """
        Get the latest tickets with proper pagination support using direct API calls.

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
            raise Exception(f"Failed to get latest tickets: HTTP {e.code} - {e.reason}. {error_body}")
        except Exception as e:
            raise Exception(f"Failed to get latest tickets: {str(e)}")

    def get_all_articles(self) -> Dict[str, Any]:
        """
        Fetch help center articles as knowledge base.
        Returns a Dict of section -> [article].
        """
        try:
            # Get all sections
            sections = self.client.help_center.sections()

            # Get articles for each section
            kb = {}
            for section in sections:
                articles = self.client.help_center.sections.articles(section.id)
                kb[section.name] = {
                    'section_id': section.id,
                    'description': section.description,
                    'articles': [{
                        'id': article.id,
                        'title': article.title,
                        'body': article.body,
                        'updated_at': str(article.updated_at),
                        'url': article.html_url
                    } for article in articles]
                }

            return kb
        except Exception as e:
            raise Exception(f"Failed to fetch knowledge base: {str(e)}")

    def search_articles(
        self,
        query: str,
        label_names: List[str] | None = None,
        section_id: int | None = None,
        locale: str = 'en-us',
        per_page: int = 25,
        sort_by: str = 'relevance'
    ) -> Dict[str, Any]:
        """
        Search Help Center articles using Zendesk's search API.

        Args:
            query: Search query string
            label_names: Optional list of labels/tags to filter by
            section_id: Optional section ID to limit search to
            locale: Locale for articles (default: en-us)
            per_page: Number of results per page (max 100)
            sort_by: Sort order - 'relevance' or 'updated_at'

        Returns:
            Dict containing:
                - articles: List of matching articles with summaries
                - count: Number of articles returned
                - query: The search query used
                - has_more: True if additional results are available beyond per_page
        """
        try:
            if not query:
                raise ValueError("Search query cannot be empty")

            # Cap per_page at 100 (Zendesk API limit)
            per_page = min(per_page, 100)

            # Build search parameters
            search_params = {
                'query': query,
                'per_page': per_page,
                'sort_by': sort_by
            }

            # Add optional filters
            if label_names:
                search_params['label_names'] = ','.join(label_names)
            if section_id:
                search_params['section_id'] = section_id

            # Execute search using zenpy
            search_results = self.client.help_center.articles.search(**search_params)

            # Collect results and deduplicate by ID
            articles = []
            seen_ids = set()
            count = 0
            has_more = False
            for article in search_results:
                if article.id not in seen_ids:
                    seen_ids.add(article.id)
                    articles.append({
                        'id': article.id,
                        'title': article.title,
                        'body_snippet': getattr(article, 'body', '')[:500] + '...' if len(getattr(article, 'body', '')) > 500 else getattr(article, 'body', ''),
                        'url': article.html_url,
                        'section_id': getattr(article, 'section_id', None),
                        'labels': list(getattr(article, 'label_names', []) or []),
                        'updated_at': str(article.updated_at),
                        'author_id': getattr(article, 'author_id', None),
                        'vote_sum': getattr(article, 'vote_sum', 0)
                    })
                    count += 1
                    if count >= per_page:
                        # Reached requested page size; indicate there may be more results
                        has_more = True
                        break

            return {
                'articles': articles,
                'count': count,
                'query': query,
                'label_names': label_names,
                'section_id': section_id,
                'sort_by': sort_by,
                'has_more': has_more
            }
        except Exception as e:
            raise Exception(f"Failed to search articles: {str(e)}")

    def get_article_by_id(self, article_id: int, locale: str = 'en-us') -> Dict[str, Any]:
        """
        Get full article content by ID.

        Args:
            article_id: The ID of the article to retrieve
            locale: Locale for the article (default: en-us)

        Returns:
            Dict containing complete article information
        """
        try:
            # Get article using zenpy
            article = self.client.help_center.articles(id=article_id, locale=locale)

            return {
                'id': article.id,
                'title': article.title,
                'body': article.body,
                'html_url': article.html_url,
                'section_id': article.section_id,
                'labels': list(getattr(article, 'label_names', []) or []),
                'author_id': article.author_id,
                'created_at': str(article.created_at),
                'updated_at': str(article.updated_at),
                'vote_sum': getattr(article, 'vote_sum', 0),
                'vote_count': getattr(article, 'vote_count', 0),
                'comments_disabled': getattr(article, 'comments_disabled', False),
                'draft': getattr(article, 'draft', False),
                'promoted': getattr(article, 'promoted', False)
            }
        except Exception as e:
            raise Exception(f"Failed to get article {article_id}: {str(e)}")

    def search_articles_by_labels(
        self,
        label_names: List[str],
        locale: str = 'en-us',
        per_page: int = 25
    ) -> Dict[str, Any]:
        """
        Search articles by specific tags/labels.

        Args:
            label_names: List of labels/tags to search for
            locale: Locale for articles (default: en-us)
            per_page: Number of results per page (max 100)

        Returns:
            Dict containing articles with specified labels and pagination info
        """
        try:
            if not label_names:
                raise ValueError("At least one label name is required")

            # Cap per_page at 100
            per_page = min(per_page, 100)

            # Build parameters
            params = {
                'label_names': ','.join(label_names),
                'per_page': per_page
            }

            # Execute search using zenpy
            search_results = self.client.help_center.articles(locale=locale, **params)

            # Collect results and deduplicate by ID
            articles = []
            seen_ids = set()
            count = 0
            has_more = False
            for article in search_results:
                if article.id not in seen_ids:
                    seen_ids.add(article.id)
                    articles.append({
                        'id': article.id,
                        'title': article.title,
                        'body_snippet': getattr(article, 'body', '')[:500] + '...' if len(getattr(article, 'body', '')) > 500 else getattr(article, 'body', ''),
                        'url': article.html_url,
                        'section_id': getattr(article, 'section_id', None),
                        'labels': list(getattr(article, 'label_names', []) or []),
                        'updated_at': str(article.updated_at),
                        'author_id': getattr(article, 'author_id', None),
                        'vote_sum': getattr(article, 'vote_sum', 0)
                    })
                    count += 1
                    if count >= per_page:
                        has_more = True
                        break

            return {
                'articles': articles,
                'count': count,
                'label_names': label_names,
                'locale': locale,
                'has_more': has_more
            }
        except Exception as e:
            raise Exception(f"Failed to search articles by labels: {str(e)}")

    def get_sections_list(self, locale: str = 'en-us') -> Dict[str, Any]:
        """
        List all KB sections/categories.

        Args:
            locale: Locale for sections (default: en-us)

        Returns:
            Dict containing all sections with their details
        """
        try:
            # Get sections using zenpy
            sections = self.client.help_center.sections(locale=locale)

            # Collect section information
            section_list = []
            for section in sections:
                section_list.append({
                    'id': section.id,
                    'name': section.name,
                    'description': getattr(section, 'description', ''),
                    'url': getattr(section, 'html_url', ''),
                    'position': getattr(section, 'position', 0),
                    'created_at': str(section.created_at),
                    'updated_at': str(section.updated_at),
                    'category_id': getattr(section, 'category_id', None)
                })

            return {
                'sections': section_list,
                'count': len(section_list),
                'locale': locale
            }
        except Exception as e:
            raise Exception(f"Failed to get sections list: {str(e)}")

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
        """
        Create a new Zendesk ticket using Zenpy and return essential fields.

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
            raise Exception(f"Failed to create ticket: {str(e)}")

    def update_ticket(self, ticket_id: int, **fields: Any) -> Dict[str, Any]:
        """
        Update a Zendesk ticket with provided fields using Zenpy.

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
            raise Exception(f"Failed to update ticket {ticket_id}: {str(e)}")

    def search_tickets(
        self,
        query: str,
        sort_by: str | None = None,
        sort_order: str | None = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Search for tickets using Zendesk's search query syntax.

        This method returns up to 1000 results (Zendesk API limitation).
        For larger result sets, use search_tickets_export instead.

        Args:
            query: Zendesk search query using supported syntax
                Examples:
                - "status:open" - Open tickets
                - "priority:high status:open" - High priority open tickets
                - "created>2024-01-01" - Tickets created after date
                - "tags:bug tags:urgent" - Tickets with bug OR urgent tag
                - "assignee:me" - Tickets assigned to authenticated user
                - "subject:login*" - Subject containing words starting with "login"
                - "status:pending -tags:spam" - Pending tickets without spam tag
            sort_by: Field to sort by (updated_at, created_at, priority, status, ticket_type)
            sort_order: Sort order (asc or desc), defaults to desc
            limit: Maximum number of results to return (default 100, max 1000)

        Returns:
            Dict containing:
                - tickets: List of matching tickets
                - count: Number of tickets returned
                - total_results: Total matching tickets (may be more than returned)
                - limited: Boolean indicating if results were limited
        """
        try:
            if not query:
                raise ValueError("Search query cannot be empty")

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
            # Note: Zendesk search API has a hard limit of 1000 results
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
            raise Exception(f"Failed to search tickets: {str(e)}")

    def search_tickets_export(
        self,
        query: str,
        sort_by: str | None = None,
        sort_order: str | None = None,
        max_results: int | None = None
    ) -> Dict[str, Any]:
        """
        Search for tickets using Zendesk's search export API (unlimited results).

        This method can return more than 1000 results but may take longer to execute.
        Use this for large result sets or data exports.

        Args:
            query: Zendesk search query (same syntax as search_tickets)
            sort_by: Field to sort by (updated_at, created_at, priority, status, ticket_type)
            sort_order: Sort order (asc or desc)
            max_results: Optional limit on results to return (default: unlimited)

        Returns:
            Dict containing:
                - tickets: List of all matching tickets
                - count: Total number of tickets returned
                - query: The search query used
        """
        try:
            if not query:
                raise ValueError("Search query cannot be empty")

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

            # Apply client-side sorting if sort parameters provided
            if sort_by and tickets:
                reverse_order = sort_order == 'desc' if sort_order else True

                # Define sort key functions for different fields
                def get_sort_key(ticket):
                    field_value = ticket.get(sort_by)

                    # Handle different field types
                    if sort_by in ['created_at', 'updated_at']:
                        # Convert ISO datetime strings to comparable format
                        try:
                            from datetime import datetime
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
            raise Exception(f"Failed to export search tickets: {str(e)}")

    def upload_attachment(self, file_path: str) -> Dict[str, Any]:
        """
        Upload a file to Zendesk to get an attachment token.

        The returned token can be used when creating or updating tickets
        to attach the file to a comment. Tokens expire after 60 minutes.

        Args:
            file_path: Path to the file to upload (absolute or relative)

        Returns:
            Dict containing:
                - token: The upload token to use when attaching to a ticket
                - filename: The uploaded filename
                - size: File size in bytes
                - content_type: MIME type of the file
                - expires_at: Token expiration time (60 minutes from upload)
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            # Get file info
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            # Check file size (50 MB limit)
            max_size = 50 * 1024 * 1024  # 50 MB in bytes
            if file_size > max_size:
                raise ValueError(f"File size ({file_size} bytes) exceeds 50 MB limit")

            # Upload using zenpy
            upload_result = self.client.attachments.upload(file_path)

            return {
                'token': upload_result.token,
                'filename': filename,
                'size': file_size,
                'content_type': getattr(upload_result, 'content_type', 'application/octet-stream'),
                'expires_at': 'Token expires in 60 minutes',
                'note': 'Use this token in the uploads array when creating/updating a ticket comment'
            }
        except FileNotFoundError as e:
            raise e
        except Exception as e:
            raise Exception(f"Failed to upload attachment: {str(e)}")

    def get_ticket_attachments(self, ticket_id: int) -> Dict[str, Any]:
        """
        Get all attachments from all comments on a ticket.

        Args:
            ticket_id: The ID of the ticket

        Returns:
            Dict containing:
                - ticket_id: The ticket ID
                - attachments: List of all attachments with details
                - total_count: Total number of attachments
                - total_size: Total size of all attachments in bytes
        """
        try:
            # Get all comments for the ticket
            comments = self.client.tickets.comments(ticket=ticket_id)

            attachments = []
            total_size = 0

            for comment in comments:
                # Check if comment has attachments
                comment_attachments = getattr(comment, 'attachments', [])
                if comment_attachments:
                    for attachment in comment_attachments:
                        attachment_info = {
                            'id': attachment.id,
                            'filename': attachment.file_name,
                            'content_url': attachment.content_url,
                            'content_type': attachment.content_type,
                            'size': attachment.size,
                            'inline': getattr(attachment, 'inline', False),
                            'comment_id': comment.id,
                            'created_at': str(comment.created_at),
                            'author_id': comment.author_id
                        }

                        # Add malware scan result if available
                        if hasattr(attachment, 'malware_scan_result'):
                            attachment_info['malware_scan_result'] = attachment.malware_scan_result

                        attachments.append(attachment_info)
                        total_size += attachment.size

            return {
                'ticket_id': ticket_id,
                'attachments': attachments,
                'total_count': len(attachments),
                'total_size': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }
        except Exception as e:
            raise Exception(f"Failed to get attachments for ticket {ticket_id}: {str(e)}")

    def download_attachment(self, attachment_id: int, save_path: str | None = None) -> Dict[str, Any]:
        """
        Download an attachment by its ID.

        Args:
            attachment_id: The ID of the attachment to download
            save_path: Optional path to save the file. If not provided, returns download URL only.

        Returns:
            Dict containing:
                - attachment_id: The attachment ID
                - filename: The attachment filename
                - content_url: Direct download URL
                - size: File size in bytes
                - saved_to: Path where file was saved (if save_path provided)
        """
        try:
            # Get attachment details using direct API call
            url = f"{self.base_url}/attachments/{attachment_id}.json"
            req = urllib.request.Request(url)
            req.add_header('Authorization', self.auth_header)
            req.add_header('Content-Type', 'application/json')

            with _urlopen_with_retry(req) as response:
                data = json.loads(response.read().decode())
                attachment = data.get('attachment', {})

            if not attachment:
                raise ValueError(f"Attachment {attachment_id} not found")

            result = {
                'attachment_id': attachment_id,
                'filename': attachment.get('file_name'),
                'content_url': attachment.get('content_url'),
                'content_type': attachment.get('content_type'),
                'size': attachment.get('size')
            }

            # Download file if save_path is provided
            if save_path:
                content_url = attachment.get('content_url')
                if not content_url:
                    raise ValueError("No content_url available for this attachment")

                # Download the file (content_url already has token, no auth header needed)
                # Add User-Agent to avoid security blocks
                download_req = urllib.request.Request(content_url)
                download_req.add_header('User-Agent', 'Mozilla/5.0 (compatible; Zendesk-MCP-Server/1.0)')

                # Download the file
                with _urlopen_with_retry(download_req) as response:
                    file_content = response.read()

                # Ensure directory exists
                os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)

                # Save to file
                with open(save_path, 'wb') as f:
                    f.write(file_content)

                result['saved_to'] = save_path
                result['downloaded'] = True
            else:
                result['note'] = 'Use content_url to download the file. Provide save_path to auto-download.'

            return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else "No response body"
            raise Exception(f"Failed to download attachment {attachment_id}: HTTP {e.code} - {e.reason}. {error_body}")
        except Exception as e:
            raise Exception(f"Failed to download attachment {attachment_id}: {str(e)}")

    def find_related_tickets(self, ticket_id: int, limit: int = 100) -> Dict[str, Any]:
        """
        Find tickets related to the given ticket by subject similarity, same requester, or same organization.

        Args:
            ticket_id: The ID of the reference ticket
            limit: Maximum number of related tickets to return (default 100)

        Returns:
            Dict containing:
                - related_tickets: List of related tickets with relevance info
                - count: Number of related tickets found
                - reference_ticket: Basic info about the reference ticket
                - search_strategy: Description of how tickets were found
        """
        try:
            # Get the reference ticket
            reference_ticket = self.get_ticket(ticket_id)
            if not reference_ticket:
                raise ValueError(f"Ticket {ticket_id} not found")

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
            raise Exception(f"Failed to find related tickets for {ticket_id}: {str(e)}")

    def find_duplicate_tickets(self, ticket_id: int, limit: int = 100) -> Dict[str, Any]:
        """
        Identify potential duplicate tickets with highly similar subjects and same requester/organization.

        Args:
            ticket_id: The ID of the reference ticket
            limit: Maximum number of duplicate candidates to return (default 100)

        Returns:
            Dict containing:
                - duplicate_candidates: List of potential duplicate tickets
                - count: Number of duplicate candidates found
                - reference_ticket: Basic info about the reference ticket
                - similarity_threshold: Minimum similarity score for duplicates
        """
        try:
            # Get the reference ticket
            reference_ticket = self.get_ticket(ticket_id)
            if not reference_ticket:
                raise ValueError(f"Ticket {ticket_id} not found")

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
            raise Exception(f"Failed to find duplicate tickets for {ticket_id}: {str(e)}")

    def find_ticket_thread(self, ticket_id: int) -> Dict[str, Any]:
        """
        Find all tickets in a conversation thread using via_id relationships.

        Args:
            ticket_id: The ID of the reference ticket

        Returns:
            Dict containing:
                - thread_tickets: List of all tickets in the thread
                - count: Number of tickets in the thread
                - thread_root: The root ticket of the thread
                - thread_structure: Description of the thread structure
        """
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
            raise Exception(f"Failed to find ticket thread for {ticket_id}: {str(e)}")

    def get_ticket_relationships(self, ticket_id: int) -> Dict[str, Any]:
        """
        Get parent/child ticket relationships via the via field.

        Args:
            ticket_id: The ID of the reference ticket

        Returns:
            Dict containing:
                - relationships: Structured relationship data
                - parent_ticket: Parent ticket info (if exists)
                - child_tickets: List of child tickets
                - relationship_type: Description of the relationship
        """
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
            raise Exception(f"Failed to get ticket relationships for {ticket_id}: {str(e)}")

    def _extract_search_terms(self, subject: str) -> str:
        """
        Extract key search terms from a ticket subject for similarity searches.

        Args:
            subject: The ticket subject text

        Returns:
            String of key terms suitable for Zendesk search
        """
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
        """
        Calculate similarity score between two ticket subjects.

        Args:
            subject1: First subject
            subject2: Second subject

        Returns:
            Similarity score between 0.0 and 1.0
        """
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

    def get_ticket_fields(self) -> Dict[str, Any]:
        """
        Retrieve all ticket fields including custom fields with their definitions.

        Returns:
            Dict containing:
                - fields: List of all ticket fields with details
                - custom_fields: List of custom fields only
                - system_fields: List of system fields only
                - count: Total number of fields
        """
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
            raise Exception(f"Failed to get ticket fields: {str(e)}")

    def search_by_integration_source(
        self,
        channel: str,
        sort_by: str | None = None,
        sort_order: str | None = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Search for tickets created via a specific integration source/channel.

        Args:
            channel: The creation channel to filter by (email, web, mobile, api, chat, etc.)
            sort_by: Field to sort by (updated_at, created_at, priority, status, ticket_type)
            sort_order: Sort order (asc or desc)
            limit: Maximum number of results to return (default 100, max 1000)

        Returns:
            Dict containing tickets created via the specified channel
        """
        try:
            if not channel:
                raise ValueError("Channel cannot be empty")

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
            raise Exception(f"Failed to search by integration source {channel}: {str(e)}")

    def _apply_regex_filter(
        self,
        tickets: List[Dict[str, Any]],
        regex_pattern: str,
        fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Apply regex pattern filtering to a list of tickets.

        Args:
            tickets: List of ticket dictionaries
            regex_pattern: Regular expression pattern to match
            fields: List of fields to search in (default: ['subject', 'description'])

        Returns:
            List of tickets that match the regex pattern
        """
        import re

        if not regex_pattern:
            return tickets

        if fields is None:
            fields = ['subject', 'description']

        try:
            # Compile regex pattern
            pattern = re.compile(regex_pattern, re.IGNORECASE)

            filtered_tickets = []
            for ticket in tickets:
                # Check if pattern matches any of the specified fields
                for field in fields:
                    field_value = ticket.get(field, '')
                    if field_value and pattern.search(str(field_value)):
                        # Add match info to ticket
                        ticket_copy = ticket.copy()
                        ticket_copy['regex_match_field'] = field
                        ticket_copy['regex_match'] = pattern.search(str(field_value)).group()
                        filtered_tickets.append(ticket_copy)
                        break  # Only add ticket once even if multiple fields match

            return filtered_tickets

        except re.error as e:
            raise Exception(f"Invalid regex pattern '{regex_pattern}': {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to apply regex filter: {str(e)}")

    def _apply_fuzzy_filter(
        self,
        tickets: List[Dict[str, Any]],
        search_term: str,
        threshold: float = 0.7,
        fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Apply fuzzy matching filter to a list of tickets.

        Args:
            tickets: List of ticket dictionaries
            search_term: Term to search for with fuzzy matching
            threshold: Similarity threshold (0.0-1.0, default 0.7)
            fields: List of fields to search in (default: ['subject', 'description'])

        Returns:
            List of tickets that match the fuzzy criteria, sorted by similarity score
        """
        if not search_term:
            return tickets

        if fields is None:
            fields = ['subject', 'description']

        if threshold < 0.0 or threshold > 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")

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
            raise Exception(f"Failed to apply fuzzy filter: {str(e)}")

    def _apply_proximity_filter(
        self,
        tickets: List[Dict[str, Any]],
        terms: List[str],
        max_distance: int = 5,
        fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Apply proximity search filter to find tickets where terms appear within N words of each other.

        Args:
            tickets: List of ticket dictionaries
            terms: List of terms to search for proximity
            max_distance: Maximum number of words between terms (default 5)
            fields: List of fields to search in (default: ['subject', 'description'])

        Returns:
            List of tickets where terms appear within the specified distance
        """
        if not terms or len(terms) < 2:
            return tickets

        if fields is None:
            fields = ['subject', 'description']

        if max_distance < 1:
            raise ValueError("Max distance must be at least 1")

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
            raise Exception(f"Failed to apply proximity filter: {str(e)}")

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
        """
        Enhanced ticket search with client-side filtering capabilities.

        This method extends the basic Zendesk search with additional filtering options:
        - Regex pattern matching
        - Fuzzy string matching
        - Proximity search (terms within N words)

        Args:
            query: Base Zendesk search query
            regex_pattern: Optional regex pattern to filter results
            fuzzy_term: Optional term for fuzzy matching
            fuzzy_threshold: Similarity threshold for fuzzy matching (0.0-1.0)
            proximity_terms: Optional list of terms for proximity search
            proximity_distance: Maximum words between proximity terms
            sort_by: Field to sort by (updated_at, created_at, priority, status, ticket_type)
            sort_order: Sort order (asc or desc)
            limit: Maximum number of results to return

        Returns:
            Dict containing filtered tickets with applied enhancements
        """
        try:
            if not query:
                raise ValueError("Base search query cannot be empty")

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
            raise Exception(f"Failed to perform enhanced search: {str(e)}")

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
        """
        Build a Zendesk search query from structured parameters.

        Args:
            status: Ticket status (new, open, pending, on-hold, solved, closed)
            priority: Ticket priority (low, normal, high, urgent)
            assignee: Assignee email or "none" for unassigned
            requester: Requester email
            organization: Organization name
            tags: List of tags to include
            tags_logic: Logic for tags ("AND" or "OR", default "OR")
            exclude_tags: List of tags to exclude
            created_after: Created after date (ISO8601 or relative like "last 7 days")
            created_before: Created before date
            updated_after: Updated after date
            updated_before: Updated before date
            solved_after: Solved after date
            solved_before: Solved before date
            due_after: Due after date
            due_before: Due before date
            custom_fields: Dict of custom field IDs to values
            subject_contains: Text to search in subject
            description_contains: Text to search in description
            comment_contains: Text to search in comments

        Returns:
            Dict containing the query string and usage examples
        """
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
            raise Exception(f"Failed to build search query: {str(e)}")

    def get_search_statistics(
        self,
        query: str,
        sort_by: str = None,
        sort_order: str = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """
        Analyze search results and return aggregated statistics.

        Args:
            query: Zendesk search query
            sort_by: Field to sort by
            sort_order: Sort order
            limit: Maximum results to analyze

        Returns:
            Dict containing aggregated statistics and insights
        """
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
                        from datetime import datetime
                        date_obj = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        month_key = f"{date_obj.year}-{date_obj.month:02d}"
                        date_counts[month_key] = date_counts.get(month_key, 0) + 1
                    except:
                        pass

                # Resolution time calculation (for solved tickets)
                if status == 'solved':
                    try:
                        from datetime import datetime
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
            raise Exception(f"Failed to generate search statistics: {str(e)}")

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
        """
        Search tickets by date range with support for relative dates.

        Args:
            date_field: Date field to filter (created, updated, solved, due)
            range_type: Type of range (custom, relative)
            start_date: Start date (ISO8601 format)
            end_date: End date (ISO8601 format)
            relative_period: Relative period (last_7_days, last_30_days, this_month, last_month, this_quarter, last_quarter)
            sort_by: Field to sort by
            sort_order: Sort order
            limit: Maximum results

        Returns:
            Dict containing tickets in the specified date range
        """
        try:
            from datetime import datetime, timedelta

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
            raise Exception(f"Failed to search by date range: {str(e)}")

    def search_by_tags_advanced(
        self,
        include_tags: List[str] = None,
        exclude_tags: List[str] = None,
        tag_logic: str = "OR",
        sort_by: str = None,
        sort_order: str = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Advanced tag-based search with AND/OR/NOT logic.

        Args:
            include_tags: Tags to include
            exclude_tags: Tags to exclude
            tag_logic: Logic for include_tags (AND or OR)
            sort_by: Field to sort by
            sort_order: Sort order
            limit: Maximum results

        Returns:
            Dict containing tickets matching tag criteria
        """
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
            raise Exception(f"Failed to search by tags: {str(e)}")

    def batch_search_tickets(
        self,
        queries: List[str],
        deduplicate: bool = True,
        sort_by: str = None,
        sort_order: str = None,
        limit_per_query: int = 100
    ) -> Dict[str, Any]:
        """
        Execute multiple searches concurrently and return grouped results.

        Args:
            queries: List of search queries to execute
            deduplicate: Whether to remove duplicate tickets across queries
            sort_by: Field to sort by
            sort_order: Sort order
            limit_per_query: Maximum results per query

        Returns:
            Dict containing results grouped by query with execution metrics
        """
        try:
            import asyncio

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

            # Execute searches concurrently with a semaphore limiting concurrency
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            sem = asyncio.Semaphore(3)
            try:
                tasks = [execute_search(query) for query in queries]
                results = loop.run_until_complete(asyncio.gather(*tasks))
            finally:
                loop.close()

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
            raise Exception(f"Failed to execute batch search: {str(e)}")