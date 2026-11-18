# -*- coding: utf-8 -*-
"""Opt-in SDK core routes; the full TeamChat release entry stays unchanged."""

import asyncio
import json
import weakref

from pydantic import BaseModel, Field, ValidationError

from qwenpaw.plugins.apps import HttpResponse, PawApp

# The host loads the entry as an isolated package.
# pylint: disable=relative-beyond-top-level
from .roundtable import run_roundtable
from .sdk_agents import AgentCalls, AgentDirectory, SessionStore

# pylint: enable=relative-beyond-top-level


class RoundtableRequest(BaseModel):
    message: str = ""
    host_id: str = "cloud-orchestrator"
    agent_ids: list[str] = Field(default_factory=list)
    session_id: str = ""
    host_name: str = "CloudPaw-Master"
    brainstorm: bool = False


app = PawApp("TeamChat SDK core preview", app_id="team_chat")
_locks = weakref.WeakValueDictionary()


@app.route("/agents")
async def agents(call, _request):
    return {"agents": await AgentDirectory(call).get()}


@app.route("/chat", methods=("POST",))
async def chat(call, request):
    try:
        payload = RoundtableRequest.model_validate(request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        return HttpResponse({"detail": str(exc)}, status=422)
    key = (
        call.workspace_id,
        call.identity.user_id,
        call.identity.channel,
        payload.session_id,
    )
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        result = await run_roundtable(
            payload,
            store=SessionStore(call.storage),
            agent_cache=AgentDirectory(call),
            call_agent=AgentCalls(call).chat,
        )
    return HttpResponse(json.loads(result.body), status=result.status_code)


@app.route("/decision", methods=("POST",))
async def decision(call, request):
    body = request.json()
    if not isinstance(body, dict) or not all(
        isinstance(body.get(key), str) and body[key]
        for key in ("agent_id", "prompt", "vote_id")
    ):
        return HttpResponse(
            {"detail": "Agent, prompt and vote ID required"},
            422,
        )
    text = await AgentCalls(call).decide(
        body["agent_id"],
        body["prompt"],
        body["vote_id"],
    )
    return {"text": text}


@app.route("/model", methods=("POST",))
async def model(call, request):
    body = request.json()
    if not isinstance(body, dict) or not isinstance(body.get("prompt"), str):
        return HttpResponse({"detail": "Prompt required"}, 422)
    return {"text": await AgentCalls(call).model(body["prompt"])}


plugin = app
