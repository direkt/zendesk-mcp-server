"""Knowledge base (Help Center) methods for ZendeskClient."""
from typing import Any, Dict, List

from zendesk_mcp_server.exceptions import ZendeskError, ZendeskAPIError, ZendeskValidationError


class KnowledgeBaseMixin:
    """Mixin providing knowledge base/Help Center methods."""
    
    def get_all_articles(self) -> Dict[str, Any]:
        """Fetch help center articles as knowledge base.
        
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
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to fetch knowledge base: {str(e)}")

    def search_articles(
        self,
        query: str,
        label_names: List[str] | None = None,
        section_id: int | None = None,
        locale: str = 'en-us',
        per_page: int = 25,
        sort_by: str = 'relevance'
    ) -> Dict[str, Any]:
        """Search Help Center articles using Zendesk's search API."""
        try:
            if not query:
                raise ZendeskValidationError("Search query cannot be empty")

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
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to search articles: {str(e)}")

    def get_article_by_id(self, article_id: int, locale: str = 'en-us') -> Dict[str, Any]:
        """Get full article content by ID."""
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
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get article {article_id}: {str(e)}")

    def search_articles_by_labels(
        self,
        label_names: List[str],
        locale: str = 'en-us',
        per_page: int = 25
    ) -> Dict[str, Any]:
        """Search articles by specific tags/labels."""
        try:
            if not label_names:
                raise ZendeskValidationError("At least one label name is required")

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
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to search articles by labels: {str(e)}")

    def get_sections_list(self, locale: str = 'en-us') -> Dict[str, Any]:
        """List all KB sections/categories."""
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
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get sections list: {str(e)}")

