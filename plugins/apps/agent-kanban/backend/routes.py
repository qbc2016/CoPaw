# -*- coding: utf-8 -*-
"""Translate the existing Kanban HTTP contract to public SDK routes."""

import json

from pydantic import ValidationError

from qwenpaw.plugins.apps import HttpResponse


def register_routes(app, handlers):
    def route(name, method, path, *, context=True, body=None, query=False):
        async def handle(call, request):
            arguments = dict(request.path_params)
            if context:
                arguments["ctx"] = call
            if query:
                arguments["language"] = request.query.get("language")
            if body:
                try:
                    arguments["body"] = handlers[body].model_validate(
                        request.json(),
                    )
                except (ValidationError, json.JSONDecodeError) as exc:
                    return HttpResponse({"detail": str(exc)}, status=422)
            return await handlers[name](**arguments)

        app.route(path, methods=(method,))(handle)

    route("list_issues", "GET", "/issues")
    route("create_issue", "POST", "/issues", body="IssueCreate")
    route(
        "patch_issue",
        "PATCH",
        "/issues/{issue_id:path}",
        body="IssuePatch",
    )
    route("delete_issue", "DELETE", "/issues/{issue_id:path}")
    route("run_issue", "POST", "/issues/{issue_id:path}/run", query=True)
    route(
        "stream_issue",
        "GET",
        "/issues/{issue_id:path}/stream",
        context=False,
    )
    route("get_issue_result", "GET", "/issues/{issue_id:path}/result")
    route("stop_issue", "POST", "/issues/{issue_id:path}/stop", context=False)
    route("list_kanban_approvals", "GET", "/approvals")
    route("get_agent_queue", "GET", "/queue/{agent_id:path}", context=False)

    @app.route("/agents")
    async def agents(call, _request):
        return {
            "agents": [
                {"id": row.id, "name": row.name, "enabled": row.enabled}
                for row in await call.workspaces()
            ],
        }

    def approval(approved):
        async def handle(call, request):
            return await handlers["resolve_kanban"](
                request.path_params["request_id"],
                approved,
                call,
            )

        return handle

    for action in ("approve", "deny"):
        app.route(
            "/approvals/{request_id}/" + action,
            methods=("POST",),
        )(approval(action == "approve"))
