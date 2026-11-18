# -*- coding: utf-8 -*-
"""Remote-CI acceptance for the extracted production roundtable."""

import json
from pathlib import Path
import shutil

import pytest

from qwenpaw.plugins.testing import PluginTestHost

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.asyncio
PROVIDER = """
from qwenpaw.plugins.providers import ProviderSpec, ModelInfo, ModelChunk
from qwenpaw.plugins.messages import ContentBlock
class Plugin:
    def register(self, ctx):
        async def generate(call, request):
            yield ModelChunk((ContentBlock(
                text="answer-" + call.identity.workspace_id),), is_last=True)
        ctx.register_provider(ProviderSpec(
            "teamchat-model", "Model", generate,
            models=(ModelInfo("model", "Model"),), require_api_key=False))
plugin = Plugin()
"""


def package(tmp_path):
    target = tmp_path / "candidate"
    target.mkdir()
    for name in ("sdk_entry.py", "sdk_agents.py", "roundtable.py"):
        shutil.copyfile(ROOT / name, target / name)
    shutil.copyfile(ROOT / "sdk-preview.json", target / "plugin.json")
    return target


async def test_real_roundtable_preserves_flow_and_isolates_history(tmp_path):
    source = package(tmp_path)
    provider = tmp_path / "provider"
    provider.mkdir()
    (provider / "main.py").write_text(PROVIDER, encoding="utf-8")
    (provider / "plugin.json").write_text(
        json.dumps(
            {
                "id": "teamchat-model",
                "version": "1.0.0",
                "entry": {"backend": "main.py"},
                "sdk": {"version": "1.2.0", "capabilities": ["providers"]},
            },
        ),
        encoding="utf-8",
    )
    async with PluginTestHost(tmp_path / "host") as host:
        await host.load(provider)
        for workspace in ("test", "other"):
            await host.configure_chat_model(
                "teamchat-model",
                "model",
                workspace_id=workspace,
            )
        await host.load(source)
        payload = {
            "message": "Discuss",
            "agent_ids": ["test"],
            "host_id": "other",
            "session_id": "same-session",
        }
        for user, count in (("alice", 3), ("bob", 3), ("alice", 6)):
            result = await host.request(
                "POST",
                "/api/team_chat/chat",
                json=payload,
                user_id=user,
            )
            assert result.status == 200
            history = result.json()["history"]
            assert len(history) == count
            assert [
                (row["role"], row["sender"], row["content"])
                for row in history[-3:]
            ] == [
                ("human", "human", "Discuss"),
                ("agent", "test", "answer-test"),
                ("host", "other", "answer-other"),
            ]
        result = await host.request(
            "POST",
            "/api/team_chat/model",
            json={"prompt": "Hello"},
        )
        assert result.json() == {"text": "answer-test"}
        result = await host.request(
            "POST",
            "/api/team_chat/decision",
            json={"agent_id": "other", "vote_id": "one", "prompt": "Vote"},
        )
        assert result.json() == {"text": "answer-other"}
        assert (await host.uninstall("team_chat")).clean
