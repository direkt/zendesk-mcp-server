"""Attachment-related methods for ZendeskClient."""
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict

from zendesk_mcp_server.exceptions import (
    ZendeskError,
    ZendeskAPIError,
    ZendeskValidationError,
    ZendeskNotFoundError,
    ZendeskRateLimitError,
    ZendeskNetworkError,
)
from zendesk_mcp_server.client.base import _urlopen_with_retry


class AttachmentsMixin:
    """Mixin providing attachment-related methods."""
    
    def upload_attachment(self, file_path: str) -> Dict[str, Any]:
        """Upload a file to Zendesk to get an attachment token.

        The returned token can be used when creating or updating tickets
        to attach the file to a comment. Tokens expire after 60 minutes.
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
                raise ZendeskValidationError(f"File size ({file_size} bytes) exceeds 50 MB limit")

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
            raise ZendeskValidationError(f"File not found: {str(e)}")
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to upload attachment: {str(e)}")

    def get_ticket_attachments(self, ticket_id: int) -> Dict[str, Any]:
        """Get all attachments from all comments on a ticket."""
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
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to get attachments for ticket {ticket_id}: {str(e)}")

    def download_attachment(self, attachment_id: int, save_path: str | None = None) -> Dict[str, Any]:
        """Download an attachment by its ID."""
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
                raise ZendeskValidationError(f"Attachment {attachment_id} not found")

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
                    raise ZendeskValidationError("No content_url available for this attachment")

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
            status_code = getattr(e, 'code', None)
            if status_code == 404:
                raise ZendeskNotFoundError(
                    f"Failed to download attachment {attachment_id}: HTTP {e.code} - {e.reason}",
                    status_code=status_code,
                    response_body=error_body
                )
            elif status_code == 429:
                raise ZendeskRateLimitError(
                    f"Failed to download attachment {attachment_id}: HTTP {e.code} - {e.reason}",
                    status_code=status_code,
                    response_body=error_body
                )
            else:
                raise ZendeskAPIError(
                    f"Failed to download attachment {attachment_id}: HTTP {e.code} - {e.reason}",
                    status_code=status_code,
                    response_body=error_body
                )
        except urllib.error.URLError as e:
            raise ZendeskNetworkError(f"Network error downloading attachment {attachment_id}: {str(e)}")
        except Exception as e:
            if isinstance(e, ZendeskError):
                raise
            raise ZendeskAPIError(f"Failed to download attachment {attachment_id}: {str(e)}")

