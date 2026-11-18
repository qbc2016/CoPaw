# -*- coding: utf-8 -*-
"""TeamChat 5.4.5 roundtable behavior with an injected Agent transport."""

import time
import uuid
from fastapi import HTTPException
from fastapi.responses import JSONResponse

MAX_HISTORY = 200


def build_host_prompt(_message: str, history: list) -> str:
    """Build a summary prompt for the host agent"""
    parts = []
    for h in history:
        if h.get("role") == "human":
            parts.append(f"[用户] {h.get('content', '')}")
        elif h.get("role") == "agent":
            parts.append(
                f"[{h.get('sender_name', h.get('sender', '?'))}] "
                f"{h.get('content', '')}",
            )
    context = "\n".join(parts)
    return (
        "你是团队主持人。以下是多智能体讨论的内容：\n\n"
        f"{context}\n\n"
        "请做一个简洁的总结（200字以内），指出各智能体的观点异同，并给出你的建议。"
    )


async def run_roundtable(req, *, store, agent_cache, call_agent):
    agent_list = req.agent_ids
    if not agent_list:
        raise HTTPException(status_code=400, detail="至少需要一个参与智能体")

    now = time.time()
    new_sid = req.session_id or str(uuid.uuid4())

    history = []
    host_steps = []
    existing = None
    if req.session_id:
        existing = store.get(req.session_id)
        if existing:
            history = existing.get("history", [])
            host_steps = existing.get("host_steps", [])

    if req.message.strip():
        history.append(
            {
                "role": "human",
                "sender": "human",
                "sender_name": "人类用户",
                "content": req.message,
                "timestamp": now,
            },
        )

    for aid in agent_list:
        try:
            agents = await agent_cache.get()
            agent_info = next(
                (a for a in agents if a.get("agent_id") == aid),
                None,
            )
            agent_name = agent_info.get("name", aid) if agent_info else aid

            resp_text = await call_agent(aid, req.message)
            history.append(
                {
                    "role": "agent",
                    "sender": aid,
                    "sender_name": agent_name,
                    "content": resp_text,
                    "timestamp": time.time(),
                },
            )
        except Exception as e:
            history.append(
                {
                    "role": "agent",
                    "sender": aid,
                    "sender_name": aid,
                    "content": f"[调用失败] {e}",
                    "timestamp": time.time(),
                },
            )

    host_prompt = build_host_prompt(req.message, history)
    try:
        host_resp = await call_agent(req.host_id, host_prompt)
        host_steps.append(
            {
                "id": req.host_id,
                "content": host_prompt,
                "response": host_resp,
                "time": time.time(),
                "action": "主持人 " + req.host_name + " 汇总回复",
                "detail": host_resp[:120] if host_resp else "",
            },
        )
        history.append(
            {
                "role": "host",
                "sender": req.host_id,
                "sender_name": req.host_name,
                "content": host_resp,
                "timestamp": time.time(),
            },
        )
    except Exception as e:
        history.append(
            {
                "role": "host",
                "sender": req.host_id,
                "sender_name": req.host_id,
                "content": f"[主持人调用失败] {e}",
                "timestamp": time.time(),
            },
        )

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    data = {
        "session_id": new_sid,
        "host_id": req.host_id,
        "host_name": req.host_name,
        "agent_ids": agent_list,
        "history": history,
        "host_steps": host_steps,
        "brainstorm": req.brainstorm,
        "discussion_done": False,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
        "tag": req.session_id
        and (store.get(req.session_id) or {}).get("tag", ""),
        "pinned": req.session_id
        and (store.get(req.session_id) or {}).get("pinned", False),
    }
    store.save(new_sid, data)

    return JSONResponse(
        content={
            "session_id": new_sid,
            "history": history,
            "host_steps": host_steps,
        },
    )
