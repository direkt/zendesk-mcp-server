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
    filter_by_csat_score = arguments.get("filter_by_csat_score") if arguments else None
    filter_by_sla_breach = arguments.get("filter_by_sla_breach") if arguments else None
    filter_by_organization_id = arguments.get("filter_by_organization_id") if arguments else None
    filter_by_custom_field = arguments.get("filter_by_custom_field") if arguments else None
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
        filter_by_csat_score=filter_by_csat_score,
        filter_by_sla_breach=filter_by_sla_breach,
        filter_by_organization_id=filter_by_organization_id,
        filter_by_custom_field=filter_by_custom_field,
        time_bucket=time_bucket,
    )
    return _json_response(result)


async def handle_get_ticket_sla_status(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_ticket_sla_status tool."""
    _require_args(arguments, "ticket_id")
    ticket_id = int(arguments["ticket_id"])

    # Get ticket info
    ticket = await run_client_call(client.get_ticket, ticket_id)

    # Get metric events for SLA status
    metric_events_result = await run_client_call(client.get_ticket_metric_events, ticket_id)
    metric_events = metric_events_result.get('metric_events', [])

    # Parse SLA information
    sla_status = {
        'ticket_id': ticket_id,
        'ticket_subject': ticket.get('subject'),
        'sla_breached': False,
        'sla_met': False,
        'first_response_sla': None,
    }

    for event in metric_events:
        metric_set = event.get('metric_set', {})
        sla_policy = metric_set.get('sla_policy', {})
        if sla_policy:
            reply_time_sla = sla_policy.get('reply_time_in_minutes', {})
            if reply_time_sla:
                target = reply_time_sla.get('target')
                breached_at = reply_time_sla.get('breached_at')
                sla_status['first_response_sla'] = {
                    'target_minutes': target,
                    'breached_at': breached_at,
                    'breached': bool(breached_at),
                }
                if breached_at:
                    sla_status['sla_breached'] = True
                elif target:
                    sla_status['sla_met'] = True
                break

    return _json_response(sla_status)


async def handle_search_tickets_by_csat(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_tickets_by_csat tool.

    Now supports csat_score='any', filter_by_rating_date (Guide Survey Responses), and has_comment filter.
    """
    _require_args(arguments, "csat_score")
    csat_score_filter = arguments.get("csat_score")
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")
    organization_id = arguments.get("organization_id")
    custom_field = arguments.get("custom_field")
    limit = arguments.get("limit", 100)
    filter_by_rating_date = arguments.get("filter_by_rating_date", False)
    has_comment = arguments.get("has_comment", False)

    # Determine score range for CSAT filter
    if csat_score_filter == 'low':
        score_min, score_max = 1, 2
    elif csat_score_filter == 'high':
        score_min, score_max = 4, 5
    else:  # 'any' or unspecified
        score_min, score_max = 1, 5

    if filter_by_rating_date:
        # Use Guide Survey Responses API filtered by response submission time
        from datetime import datetime, timezone, timedelta

        def to_ms(date_str: str | None, end_of_day: bool = False) -> int | None:
            if not date_str:
                return None
            # Expect YYYY-MM-DD
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if end_of_day:
                    dt = dt + timedelta(days=1) - timedelta(milliseconds=1)
                return int(dt.timestamp() * 1000)
            except Exception:
                return None

        start_ms = to_ms(start_date, end_of_day=False)
        end_ms = to_ms(end_date, end_of_day=True)

        filtered_tickets: list[dict[str, Any]] = []
        seen_tickets: set[int] = set()
        cursor = None
        safety = 0
        while len(filtered_tickets) < limit and safety < 1000:
            raw = await run_client_call(
                client.list_survey_responses_guide,
                created_at_start_ms=start_ms,
                created_at_end_ms=end_ms,
                subject_ticket_ids=None,
                responder_ids=None,
                cursor=cursor,
            )
            survey_responses = raw.get("survey_responses", [])
            meta = raw.get("meta", {})

            # Normalize responses and map to tickets
            for resp in survey_responses:
                # extract rating + comment
                rating = None
                comment = None
                for ans in resp.get("answers", []) or []:
                    if ans.get("type") == "rating_scale":
                        try:
                            rating = int(ans.get("rating") if ans.get("rating") is not None else ans.get("value"))
                        except Exception:
                            rating = None
                    elif ans.get("type") == "open_ended":
                        comment = ans.get("value") or ans.get("text") or comment
                if rating is None or not (score_min <= rating <= score_max):
                    continue
                if has_comment and not (comment and str(comment).strip()):
                    continue

                # find ticket id
                ticket_id = None
                for subj in resp.get("subjects", []) or []:
                    zrn = subj.get("subject_zrn") or subj.get("zrn") or ""
                    if zrn.startswith("zen:ticket:"):
                        try:
                            ticket_id = int(zrn.split(":")[-1])
                        except Exception:
                            ticket_id = None
                if not ticket_id or ticket_id in seen_tickets:
                    continue

                # fetch ticket to apply org/custom filters and attach csat
                try:
                    ticket = await run_client_call(client.get_ticket, ticket_id)
                except Exception:
                    continue

                # Organization filter
                if organization_id and ticket.get("organization_id") != organization_id:
                    continue

                # Custom field filter
                if custom_field:
                    field_id = custom_field.get('field_id')
                    field_value = custom_field.get('value')
                    if field_id and field_value:
                        cfs = ticket.get('custom_fields', []) or []
                        if not any(cf.get('id') == field_id and str(cf.get('value')) == str(field_value) for cf in cfs):
                            continue

                ticket['csat_score'] = rating
                if comment:
                    ticket['csat_comments'] = [{
                        'source': 'guide_survey',
                        'comment': comment,
                        'created_at': resp.get('created_at'),
                    }]
                else:
                    ticket['csat_comments'] = []

                filtered_tickets.append(ticket)
                seen_tickets.add(ticket_id)
                if len(filtered_tickets) >= limit:
                    break

            if len(filtered_tickets) >= limit or not meta.get("has_more"):
                break
            cursor = meta.get("after_cursor") or meta.get("after")
            if not cursor:
                break
            safety += 1

        return _json_response({
            'tickets': filtered_tickets[:limit],
            'count': len(filtered_tickets[:limit]),
            'filter_applied': {
                'csat_score': csat_score_filter,
                'start_date': start_date,
                'end_date': end_date,
                'organization_id': organization_id,
                'custom_field': custom_field,
                'filter_by_rating_date': True,
                'has_comment': has_comment,
            },
            'note': 'Filtered by survey response created_at via Guide Survey Responses API'
        })

    # Fallback: ticket created_at based search (legacy behavior)
    # Build ticket search query - search for solved tickets first (most likely to have CSAT)
    query_parts = []
    if start_date:
        query_parts.append(f"created>={start_date}")
    if end_date:
        query_parts.append(f"created<={end_date}")
    if organization_id:
        query_parts.append(f"organization:{organization_id}")
    query_parts.append("status:solved")

    query = " ".join(query_parts) if query_parts else "status:solved"

    # Search tickets - get more than limit since we'll filter by CSAT
    ticket_results = await run_client_call(
        client.search_tickets_export,
        query=query,
        sort_by="created_at",
        sort_order="desc",
        max_results=limit * 20  # Get many tickets to find ones with CSAT
    )

    tickets = ticket_results.get("tickets", [])
    filtered_tickets = []

    # Process each ticket to check CSAT
    for ticket in tickets:
        if len(filtered_tickets) >= limit:
            break

        ticket_id = ticket.get("id")
        if not ticket_id:
            continue

        # Apply custom field filter early
        if custom_field:
            field_id = custom_field.get('field_id')
            field_value = custom_field.get('value')
            if field_id and field_value:
                custom_fields = ticket.get('custom_fields', [])
                if not any(
                    cf.get('id') == field_id and str(cf.get('value')) == str(field_value)
                    for cf in custom_fields
                ):
                    continue

        # Check CSAT - try multiple methods
        ticket_csat_score = None
        csat_comments = []

        # Method 1: Check legacy satisfaction_rating from ticket search result
        satisfaction = ticket.get("satisfaction_rating")
        if satisfaction:
            score = satisfaction.get("score")
            if score is not None:
                if isinstance(score, str):
                    s = score.lower()
                    if (csat_score_filter == 'low' and s == 'bad') or (csat_score_filter == 'high' and s == 'good') or (csat_score_filter == 'any' and s in ('good','bad')):
                        ticket_csat_score = 2 if s == 'bad' else 5
                        comment = satisfaction.get("comment")
                        if comment:
                            csat_comments.append({'source': 'legacy','comment': comment})
                else:
                    if score_min <= score <= score_max:
                        ticket_csat_score = score
                        comment = satisfaction.get("comment")
                        if comment:
                            csat_comments.append({'source': 'legacy','comment': comment})

        # Method 2: If no legacy CSAT or doesn't match, fetch ticket individually
        if ticket_csat_score is None:
            try:
                full_ticket = await run_client_call(client.get_ticket, ticket_id)
                satisfaction = full_ticket.get("satisfaction_rating")
                if satisfaction and satisfaction.get("score") is not None:
                    score = satisfaction.get("score")
                    if isinstance(score, str):
                        s = score.lower()
                        if (csat_score_filter == 'low' and s == 'bad') or (csat_score_filter == 'high' and s == 'good') or (csat_score_filter == 'any' and s in ('good','bad')):
                            ticket_csat_score = 2 if s == 'bad' else 5
                            comment = satisfaction.get("comment")
                            if comment:
                                csat_comments.append({'source': 'legacy','comment': comment})
                    else:
                        if score_min <= score <= score_max:
                            ticket_csat_score = score
                            comment = satisfaction.get("comment")
                            if comment:
                                csat_comments.append({'source': 'legacy','comment': comment})
            except Exception:
                pass

        # Method 3: Check CSAT survey responses (new API)
        if ticket_csat_score is None:
            try:
                csat_responses_result = await run_client_call(
                    client.get_ticket_csat_survey_responses,
                    ticket_id
                )
                survey_responses = csat_responses_result.get('csat_survey_responses', [])
                for response in survey_responses:
                    score = response.get('score')
                    if score is not None:
                        if isinstance(score, str) and score.isdigit():
                            score = int(score)
                        if isinstance(score, (int, float)) and score_min <= score <= score_max:
                            ticket_csat_score = score
                        comment = response.get('comment')
                        if comment:
                            csat_comments.append({'source': 'survey','comment': comment,'created_at': response.get('created_at')})
                        break
            except Exception:
                pass

        # Only include tickets with matching CSAT
        if ticket_csat_score is not None:
            if has_comment and not any((c.get('comment') or '').strip() for c in csat_comments):
                continue
            ticket['csat_score'] = ticket_csat_score
            ticket['csat_comments'] = csat_comments
            filtered_tickets.append(ticket)

    return _json_response({
        'tickets': filtered_tickets[:limit],
        'count': len(filtered_tickets[:limit]),
        'filter_applied': {
            'csat_score': csat_score_filter,
            'start_date': start_date,
            'end_date': end_date,
            'organization_id': organization_id,
            'custom_field': custom_field,
            'filter_by_rating_date': False,
            'has_comment': has_comment,
        },
        'note': 'CSAT data checked from both legacy satisfaction_rating and CSAT survey responses APIs'
    })


async def handle_list_survey_responses_zendesk(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle list_survey_responses_zendesk tool using Guide Survey Responses API.
    Filters by survey response created_at, rating, and comment presence.
    """
    arguments = arguments or {}

    # Extract parameters
    created_at_start_ms = arguments.get("created_at_start_ms")
    created_at_end_ms = arguments.get("created_at_end_ms")
    subject_ticket_ids = arguments.get("subject_ticket_ids")
    responder_ids = arguments.get("responder_ids")
    rating_min = arguments.get("rating_min")
    rating_max = arguments.get("rating_max")
    rating_category = arguments.get("rating_category")  # 'good'|'bad'
    has_comment = arguments.get("has_comment", False)
    cursor = arguments.get("cursor")

    # Call client (single page) and normalize
    raw = await run_client_call(
        client.list_survey_responses_guide,
        created_at_start_ms=created_at_start_ms,
        created_at_end_ms=created_at_end_ms,
        subject_ticket_ids=subject_ticket_ids,
        responder_ids=responder_ids,
        cursor=cursor,
    )

    survey_responses = raw.get("survey_responses", [])
    meta = raw.get("meta", {})

    def extract_fields(resp: dict[str, Any]) -> dict[str, Any]:
        rating = None
        category = None
        comment = None
        created_at = resp.get("created_at")
        responder_id = resp.get("responder_id")
        survey_id = resp.get("survey_id")
        expires_at = resp.get("expires_at")
        ticket_id = None

        # subjects -> find ticket
        for subj in resp.get("subjects", []) or []:
            # common shape: {"type":"ticket", "subject_zrn":"zen:ticket:123"} or {"zrn":"zen:ticket:123"}
            zrn = subj.get("subject_zrn") or subj.get("zrn") or ""
            if zrn.startswith("zen:ticket:"):
                try:
                    ticket_id = int(zrn.split(":")[-1])
                except Exception:
                    pass

        # answers -> extract rating and open_ended
        for ans in resp.get("answers", []) or []:
            atype = ans.get("type")
            if atype == "rating_scale":
                rating = ans.get("rating") if ans.get("rating") is not None else ans.get("value")
                # rating could be string
                try:
                    rating = int(rating) if rating is not None else None
                except Exception:
                    rating = None
                category = ans.get("rating_category") or ans.get("category")
            elif atype == "open_ended":
                # comment may be under value or text
                comment = ans.get("value") or ans.get("text") or comment

        return {
            "survey_response_id": resp.get("id"),
            "ticket_id": ticket_id,
            "rating": rating,
            "rating_category": category,
            "comment": comment,
            "created_at": created_at,
            "responder_id": responder_id,
            "survey_id": survey_id,
            "expires_at": expires_at,
        }

    # Apply normalization + filters
    normalized: list[dict[str, Any]] = []
    for r in survey_responses:
        item = extract_fields(r)
        # rating filters
        if rating_category == "good" and not (item["rating"] is not None and item["rating"] >= 4):
            continue
        if rating_category == "bad" and not (item["rating"] is not None and item["rating"] <= 2):
            continue
        if rating_min is not None and (item["rating"] is None or item["rating"] < int(rating_min)):
            continue
        if rating_max is not None and (item["rating"] is None or item["rating"] > int(rating_max)):
            continue
        if has_comment and not (item.get("comment") and str(item["comment"]).strip()):
            continue
        normalized.append(item)

    return _json_response({
        "survey_responses": normalized,
        "count": len(normalized),
        "has_more": bool(meta.get("has_more")),
        "next_cursor": meta.get("after_cursor") or meta.get("after"),
        "filter_applied": {
            "created_at_start_ms": created_at_start_ms,
            "created_at_end_ms": created_at_end_ms,
            "subject_ticket_ids": subject_ticket_ids,
            "responder_ids": responder_ids,
            "rating_min": rating_min,
            "rating_max": rating_max,
            "rating_category": rating_category,
            "has_comment": has_comment,
        }
    })


async def handle_count_survey_responses_zendesk(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Count survey responses matching filters across pages."""
    arguments = arguments or {}

    created_at_start_ms = arguments.get("created_at_start_ms")
    created_at_end_ms = arguments.get("created_at_end_ms")
    subject_ticket_ids = arguments.get("subject_ticket_ids")
    responder_ids = arguments.get("responder_ids")
    rating_min = arguments.get("rating_min")
    rating_max = arguments.get("rating_max")
    rating_category = arguments.get("rating_category")
    has_comment = arguments.get("has_comment", False)

    total = 0
    cursor = arguments.get("cursor")
    page_safety = 0

    # small inner filter function mirroring list handler
    def include_item(item: dict[str, Any]) -> bool:
        if rating_category == "good" and not (item["rating"] is not None and item["rating"] >= 4):
            return False
        if rating_category == "bad" and not (item["rating"] is not None and item["rating"] <= 2):
            return False
        if rating_min is not None and (item["rating"] is None or item["rating"] < int(rating_min)):
            return False
        if rating_max is not None and (item["rating"] is None or item["rating"] > int(rating_max)):
            return False
        if has_comment and not (item.get("comment") and str(item["comment"]).strip()):
            return False
        return True

    while page_safety < 1000:  # hard cap
        raw = await run_client_call(
            client.list_survey_responses_guide,
            created_at_start_ms=created_at_start_ms,
            created_at_end_ms=created_at_end_ms,
            subject_ticket_ids=subject_ticket_ids,
            responder_ids=responder_ids,
            cursor=cursor,
        )
        survey_responses = raw.get("survey_responses", [])
        meta = raw.get("meta", {})

        # normalize minimal fields for filtering
        for r in survey_responses:
            rating = None
            comment = None
            # answers
            for ans in r.get("answers", []) or []:
                if ans.get("type") == "rating_scale":
                    try:
                        rating = int(ans.get("rating") if ans.get("rating") is not None else ans.get("value"))
                    except Exception:
                        rating = None
                elif ans.get("type") == "open_ended":
                    comment = ans.get("value") or ans.get("text") or comment
            item = {"rating": rating, "comment": comment}
            if include_item(item):
                total += 1

        if not meta.get("has_more"):
            break
        cursor = meta.get("after_cursor") or meta.get("after")
        if not cursor:
            break
        page_safety += 1

    return _json_response({
        "total_count": total,
        "filter_applied": {
            "created_at_start_ms": created_at_start_ms,
            "created_at_end_ms": created_at_end_ms,
            "subject_ticket_ids": subject_ticket_ids,
            "responder_ids": responder_ids,
            "rating_min": rating_min,
            "rating_max": rating_max,
            "rating_category": rating_category,
            "has_comment": has_comment,
        }
    })


async def handle_get_sla_policies(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_sla_policies tool."""
    result = await run_client_call(client.get_sla_policies)
    return _json_response(result)


async def handle_get_sla_policy(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_sla_policy tool."""
    _require_args(arguments, "policy_id")
    result = await run_client_call(client.get_sla_policy, int(arguments["policy_id"]))
    return _json_response(result)


async def handle_search_tickets_with_sla_breaches(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle search_tickets_with_sla_breaches tool."""
    breach_type = arguments.get("breach_type") if arguments else None
    status = arguments.get("status") if arguments else None
    priority = arguments.get("priority") if arguments else None
    limit = arguments.get("limit", 100) if arguments else 100

    result = await run_client_call(
        client.search_tickets_with_sla_breaches,
        breach_type=breach_type,
        status=status,
        priority=priority,
        limit=limit
    )
    return _json_response(result)


async def handle_get_tickets_at_risk_of_breach(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_tickets_at_risk_of_breach tool."""
    status = arguments.get("status") if arguments else None
    priority = arguments.get("priority") if arguments else None
    limit = arguments.get("limit", 50) if arguments else 50

    result = await run_client_call(
        client.get_tickets_at_risk_of_breach,
        status=status,
        priority=priority,
        limit=limit
    )
    return _json_response(result)


async def handle_get_recent_tickets_with_csat(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_recent_tickets_with_csat tool."""
    limit = arguments.get("limit", 20) if arguments else 20

    result = await run_client_call(
        client.get_recent_tickets_with_csat,
        limit=limit
    )
    return _json_response(result)


async def handle_get_tickets_with_csat_this_week(client: Any, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Handle get_tickets_with_csat_this_week tool."""
    result = await run_client_call(client.get_tickets_with_csat_this_week)
    return _json_response(result)

