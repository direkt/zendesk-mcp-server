"""Individual tool handler functions."""
import json
from typing import Any
from mcp.server import types

from zendesk_mcp_server.server import run_client_call


def _json_response(data: Any) -> list[types.TextContent]:
    """Helper to format JSON response."""
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _require_args(arguments: dict[str, Any] | None, *required_keys: str) -> None:
    """Helper to validate required arguments."""
    if not arguments:
        raise ValueError("Missing arguments")
    missing = [key for key in required_keys if key not in arguments or arguments[key] is None]
    if missing:
        raise ValueError(f"Missing required arguments: {', '.join(missing)}")


async def handle_get_ticket(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_ticket tool."""
    _require_args(arguments, "ticket_id")
    ticket = await run_client_call(client.get_ticket, arguments["ticket_id"])
    return _json_response(ticket)


async def handle_create_ticket(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle create_ticket tool."""
    _require_args(arguments, "subject", "description")
    created = await run_client_call(
        client.create_ticket,
        subject=arguments.get("subject"),
        description=arguments.get("description"),
        requester_id=arguments.get("requester_id"),
        assignee_id=arguments.get("assignee_id"),
        priority=arguments.get("priority"),
        type=arguments.get("type"),
        tags=arguments.get("tags"),
        custom_fields=arguments.get("custom_fields"),
    )
    return _json_response({"message": "Ticket created successfully", "ticket": created})


async def handle_get_tickets(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_tickets tool."""
    page = arguments.get("page", 1) if arguments else 1
    per_page = arguments.get("per_page", 25) if arguments else 25
    sort_by = arguments.get("sort_by", "created_at") if arguments else "created_at"
    sort_order = arguments.get("sort_order", "desc") if arguments else "desc"
    tickets = await run_client_call(
        client.get_tickets,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order
    )
    return _json_response(tickets)


async def handle_get_ticket_comments(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_ticket_comments tool."""
    _require_args(arguments, "ticket_id")
    comments = await run_client_call(client.get_ticket_comments, arguments["ticket_id"])
    return _json_response(comments)


async def handle_create_ticket_comment(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle create_ticket_comment tool."""
    _require_args(arguments, "ticket_id", "comment")
    public = arguments.get("public", True)
    result = await run_client_call(
        client.post_comment,
        ticket_id=arguments["ticket_id"],
        comment=arguments["comment"],
        public=public
    )
    return [types.TextContent(type="text", text=f"Comment created successfully: {result}")]


async def handle_update_ticket(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle update_ticket tool."""
    _require_args(arguments, "ticket_id")
    ticket_id = arguments.get("ticket_id")
    update_fields = {k: v for k, v in arguments.items() if k != "ticket_id"}
    updated = await run_client_call(client.update_ticket, int(ticket_id), **update_fields)
    return _json_response({"message": "Ticket updated successfully", "ticket": updated})


async def handle_search_tickets(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_tickets tool."""
    _require_args(arguments, "query")
    results = await run_client_call(
        client.search_tickets,
        query=arguments.get("query"),
        sort_by=arguments.get("sort_by"),
        sort_order=arguments.get("sort_order"),
        limit=arguments.get("limit", 100)
    )
    return _json_response(results)


async def handle_search_tickets_export(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_tickets_export tool."""
    _require_args(arguments, "query")
    results = await run_client_call(
        client.search_tickets_export,
        query=arguments.get("query"),
        sort_by=arguments.get("sort_by"),
        sort_order=arguments.get("sort_order"),
        max_results=arguments.get("max_results")
    )
    return _json_response(results)


async def handle_upload_attachment(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle upload_attachment tool."""
    _require_args(arguments, "file_path")
    result = await run_client_call(client.upload_attachment, arguments.get("file_path"))
    return _json_response(result)


async def handle_get_ticket_attachments(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_ticket_attachments tool."""
    _require_args(arguments, "ticket_id")
    result = await run_client_call(client.get_ticket_attachments, int(arguments["ticket_id"]))
    return _json_response(result)


async def handle_download_attachment(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle download_attachment tool."""
    _require_args(arguments, "attachment_id")
    result = await run_client_call(
        client.download_attachment,
        int(arguments["attachment_id"]),
        save_path=arguments.get("save_path")
    )
    return _json_response(result)


async def handle_search_kb_articles(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_kb_articles tool."""
    _require_args(arguments, "query")
    result = await run_client_call(
        client.search_articles,
        query=arguments.get("query"),
        label_names=arguments.get("labels"),
        section_id=arguments.get("section_id"),
        per_page=arguments.get("limit", 10),
        sort_by=arguments.get("sort_by", "relevance")
    )
    return _json_response(result)


async def handle_get_kb_article(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_kb_article tool."""
    _require_args(arguments, "article_id")
    result = await run_client_call(client.get_article_by_id, int(arguments["article_id"]))
    return _json_response(result)


async def handle_search_kb_by_labels(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_kb_by_labels tool."""
    _require_args(arguments, "labels")
    result = await run_client_call(
        client.search_articles_by_labels,
        label_names=arguments.get("labels"),
        per_page=arguments.get("limit", 10)
    )
    return _json_response(result)


async def handle_list_kb_sections(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle list_kb_sections tool."""
    result = await run_client_call(client.get_sections_list)
    return _json_response(result)


async def handle_find_related_tickets(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle find_related_tickets tool."""
    _require_args(arguments, "ticket_id")
    limit = arguments.get("limit", 100)
    result = await run_client_call(client.find_related_tickets, int(arguments["ticket_id"]), limit)
    return _json_response(result)


async def handle_find_duplicate_tickets(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle find_duplicate_tickets tool."""
    _require_args(arguments, "ticket_id")
    limit = arguments.get("limit", 100)
    result = await run_client_call(client.find_duplicate_tickets, int(arguments["ticket_id"]), limit)
    return _json_response(result)


async def handle_find_ticket_thread(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle find_ticket_thread tool."""
    _require_args(arguments, "ticket_id")
    result = await run_client_call(client.find_ticket_thread, int(arguments["ticket_id"]))
    return _json_response(result)


async def handle_get_ticket_relationships(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_ticket_relationships tool."""
    _require_args(arguments, "ticket_id")
    result = await run_client_call(client.get_ticket_relationships, int(arguments["ticket_id"]))
    return _json_response(result)


async def handle_get_ticket_fields(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_ticket_fields tool."""
    result = await run_client_call(client.get_ticket_fields)
    return _json_response(result)


async def handle_search_by_source(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_by_source tool."""
    _require_args(arguments, "channel")
    result = await run_client_call(
        client.search_by_integration_source,
        channel=arguments.get("channel"),
        sort_by=arguments.get("sort_by"),
        sort_order=arguments.get("sort_order"),
        limit=arguments.get("limit", 100)
    )
    return _json_response(result)


async def handle_search_tickets_enhanced(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_tickets_enhanced tool."""
    _require_args(arguments, "query")
    result = await run_client_call(
        client.search_tickets_enhanced,
        query=arguments.get("query"),
        regex_pattern=arguments.get("regex_pattern"),
        fuzzy_term=arguments.get("fuzzy_term"),
        fuzzy_threshold=arguments.get("fuzzy_threshold", 0.7),
        proximity_terms=arguments.get("proximity_terms"),
        proximity_distance=arguments.get("proximity_distance", 5),
        sort_by=arguments.get("sort_by"),
        sort_order=arguments.get("sort_order"),
        limit=arguments.get("limit", 100)
    )
    return _json_response(result)


async def handle_build_search_query(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle build_search_query tool."""
    result = await run_client_call(
        client.build_search_query,
        status=arguments.get("status") if arguments else None,
        priority=arguments.get("priority") if arguments else None,
        assignee=arguments.get("assignee") if arguments else None,
        requester=arguments.get("requester") if arguments else None,
        organization=arguments.get("organization") if arguments else None,
        tags=arguments.get("tags") if arguments else None,
        tags_logic=arguments.get("tags_logic", "OR") if arguments else "OR",
        exclude_tags=arguments.get("exclude_tags") if arguments else None,
        created_after=arguments.get("created_after") if arguments else None,
        created_before=arguments.get("created_before") if arguments else None,
        updated_after=arguments.get("updated_after") if arguments else None,
        updated_before=arguments.get("updated_before") if arguments else None,
        solved_after=arguments.get("solved_after") if arguments else None,
        solved_before=arguments.get("solved_before") if arguments else None,
        due_after=arguments.get("due_after") if arguments else None,
        due_before=arguments.get("due_before") if arguments else None,
        custom_fields=arguments.get("custom_fields") if arguments else None,
        subject_contains=arguments.get("subject_contains") if arguments else None,
        description_contains=arguments.get("description_contains") if arguments else None,
        comment_contains=arguments.get("comment_contains") if arguments else None
    )
    return _json_response(result)


async def handle_get_search_statistics(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_search_statistics tool."""
    _require_args(arguments, "query")
    result = await run_client_call(
        client.get_search_statistics,
        query=arguments.get("query"),
        sort_by=arguments.get("sort_by"),
        sort_order=arguments.get("sort_order"),
        limit=arguments.get("limit", 1000)
    )
    return _json_response(result)


async def handle_search_by_date_range(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_by_date_range tool."""
    result = await run_client_call(
        client.search_by_date_range,
        date_field=arguments.get("date_field", "created") if arguments else "created",
        range_type=arguments.get("range_type", "custom") if arguments else "custom",
        start_date=arguments.get("start_date") if arguments else None,
        end_date=arguments.get("end_date") if arguments else None,
        relative_period=arguments.get("relative_period") if arguments else None,
        sort_by=arguments.get("sort_by") if arguments else None,
        sort_order=arguments.get("sort_order") if arguments else None,
        limit=arguments.get("limit", 100) if arguments else 100
    )
    return _json_response(result)


async def handle_search_by_tags_advanced(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_by_tags_advanced tool."""
    result = await run_client_call(
        client.search_by_tags_advanced,
        include_tags=arguments.get("include_tags") if arguments else None,
        exclude_tags=arguments.get("exclude_tags") if arguments else None,
        tag_logic=arguments.get("tag_logic", "OR") if arguments else "OR",
        sort_by=arguments.get("sort_by") if arguments else None,
        sort_order=arguments.get("sort_order") if arguments else None,
        limit=arguments.get("limit", 100) if arguments else 100
    )
    return _json_response(result)


async def handle_batch_search_tickets(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle batch_search_tickets tool."""
    _require_args(arguments, "queries")
    # batch_search_tickets is now async, call it directly
    result = await client.batch_search_tickets(
        queries=arguments.get("queries"),
        deduplicate=arguments.get("deduplicate", True),
        sort_by=arguments.get("sort_by"),
        sort_order=arguments.get("sort_order"),
        limit_per_query=arguments.get("limit_per_query", 100)
    )
    return _json_response(result)


async def handle_get_ticket_bundle_zendesk(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_ticket_bundle_zendesk tool."""
    _require_args(arguments, "ticket_id")
    comment_limit = arguments.get("comment_limit", 50)
    audit_limit = arguments.get("audit_limit", 100)
    result = await run_client_call(
        client.get_ticket_bundle,
        int(arguments["ticket_id"]),
        comment_limit,
        audit_limit,
    )
    return _json_response(result)


async def handle_get_case_volume_analytics(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_case_volume_analytics tool."""
    start_date = arguments.get("start_date") if arguments else None
    end_date = arguments.get("end_date") if arguments else None
    max_results = arguments.get("max_results") if arguments else None
    include_metrics = arguments.get("include_metrics") if arguments else None
    group_by = arguments.get("group_by") if arguments else None
    filter_by_status = arguments.get("filter_by_status") if arguments else None
    filter_by_priority = arguments.get("filter_by_priority") if arguments else None
    filter_by_tags = arguments.get("filter_by_tags") if arguments else None
    time_bucket = arguments.get("time_bucket", "weekly") if arguments else "weekly"

    result = await run_client_call(
        client.get_case_volume_analytics,
        start_date=start_date,
        end_date=end_date,
        max_results=max_results,
        include_metrics=include_metrics,
        group_by=group_by,
        filter_by_status=filter_by_status,
        filter_by_priority=filter_by_priority,
        filter_by_tags=filter_by_tags,
        time_bucket=time_bucket,
    )
    return _json_response(result)

