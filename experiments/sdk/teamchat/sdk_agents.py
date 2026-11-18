# -*- coding: utf-8 -*-
"""Public SDK transport for TeamChat roundtables and decision workers."""

import asyncio
import hashlib
import uuid

from qwenpaw.plugins.apps import ChatRequest
from qwenpaw.plugins.messages import ContentBlock, Message


class AgentDirectory:
    def __init__(self, call):
        self.call = call

    async def get(self):
        return [
            {"agent_id": row.id, "name": row.name, "enabled": row.enabled}
            for row in await self.call.workspaces()
            if row.enabled
        ]


class SessionStore:
    def __init__(self, storage):
        self.storage = storage

    @staticmethod
    def key(session_id):
        digest = hashlib.sha256(session_id.encode()).hexdigest()
        return "roundtables/" + digest + ".json"

    def get(self, session_id):
        return self.storage.read_json(self.key(session_id))

    def save(self, session_id, value):
        self.storage.write_json(self.key(session_id), value)


class AgentCalls:
    def __init__(self, call):
        self.call = call

    async def chat(self, agent_id, prompt, *, session_id=None, timeout=120):
        async with asyncio.timeout(timeout):
            async with self.call.for_workspace(agent_id) as target:
                reply = await target.chat(
                    ChatRequest(
                        prompt,
                        session_id=session_id
                        or "teamchat:" + uuid.uuid4().hex,
                    ),
                )
                if not reply.text.strip():
                    raise ValueError("Agent returned no visible reply")
                return reply.text

    async def decide(self, agent_id, prompt, vote_id):
        session_id = "decision:" + vote_id + ":" + agent_id
        async with self.call.for_workspace(agent_id) as target:
            async with asyncio.timeout(120):
                await target.chat(ChatRequest("/clear", session_id=session_id))
                return (
                    await target.chat(
                        ChatRequest(
                            prompt,
                            session_id=session_id,
                        ),
                    )
                ).text

    async def model(self, prompt):
        reply = await self.call.models.complete(
            (Message("user", (ContentBlock(text=prompt),)),),
        )
        return "".join(
            block.text for block in reply.content if block.type == "text"
        )
