# -*- coding: utf-8 -*-
"""Acceptance of the real Kanban migration candidate through public HTTP."""

import asyncio
import json
import importlib.util
import sys
import threading
from types import SimpleNamespace
import shutil
from pathlib import Path

from qwenpaw.plugins.compliance import check_plugin
from qwenpaw.plugins.testing import PluginTestHost
from qwenpaw.plugins.resources import ResourceOwner, ResourceScope

import pytest

from .sdk_author_fixture import make_plugin

PLUGIN = Path(__file__).resolve().parents[3] / "plugins/apps/agent-kanban"
PROVIDER = """
from qwenpaw.plugins.providers import ProviderSpec, ModelInfo, ModelChunk
from qwenpaw.plugins.messages import ContentBlock
class Plugin:
    def register(self, ctx):
        async def generate(call, request):
            yield ModelChunk((ContentBlock(text="kanban completed"),),
                             is_last=True)
        ctx.register_provider(ProviderSpec(
            "kanban-model", "Kanban", generate,
            models=(ModelInfo("model", "Model"),), require_api_key=False))
plugin = Plugin()
"""


def test_kanban_public_imports():
    report = check_plugin(PLUGIN)
    assert report.compatibility == "compatible"
    assert [
        (item.code, item.file, item.severity) for item in report.findings
    ] == [
        ("unmanaged-resource", "backend/main.py", "warning"),
    ]


async def test_board_persists_and_legacy_history_is_explicit(tmp_path):
    async with PluginTestHost(tmp_path / "host") as host:
        await host.load(PLUGIN)
        created = await host.request(
            "POST",
            "/api/agent-kanban/issues",
            json={"title": "Keep board", "description": "content"},
        )
        assert created.status == 200
        issue = created.json()
        assert {
            key: issue[key]
            for key in (
                "title",
                "description",
                "status",
                "assignee",
                "language",
            )
        } == {
            "title": "Keep board",
            "description": "content",
            "status": "backlog",
            "assignee": "",
            "language": "en",
        }
        result = await host.request(
            "GET",
            "/api/agent-kanban/issues/" + issue["id"] + "/result",
        )
        assert (result.status, result.json()) == (200, {"messages": []})
        assert (await host.uninstall("agent-kanban")).clean
        await host.load(PLUGIN)
        listed = await host.request("GET", "/api/agent-kanban/issues")
        assert listed.json() == {"issues": [issue]}
        unknown = await host.request(
            "POST",
            "/api/agent-kanban/approvals/foreign/approve",
        )
        assert unknown.status == 404


async def test_real_issue_runs_after_http_request_scope_ends(tmp_path):
    async with PluginTestHost(tmp_path / "host") as host:
        await host.load(make_plugin(tmp_path, PROVIDER, ["providers"]))
        await host.configure_chat_model("kanban-model", "model")
        await host.load(PLUGIN)
        issue = (
            await host.request(
                "POST",
                "/api/agent-kanban/issues",
                json={"title": "Run", "assignee": "test"},
            )
        ).json()
        path = "/api/agent-kanban/issues/" + issue["id"]
        assert (await host.request("POST", path + "/run")).status == 200
        async with asyncio.timeout(10):
            while True:
                rows = (
                    await host.request(
                        "GET",
                        "/api/agent-kanban/issues",
                    )
                ).json()["issues"]
                if rows[0]["status"] == "review":
                    break
                assert not rows[0].get("error"), rows[0]
                await asyncio.sleep(0.01)
        result = (await host.request("GET", path + "/result")).json()
        assert any(
            block.get("text") == "kanban completed"
            for message in result["messages"]
            for block in message["content"]
        )
        assert (await host.uninstall("agent-kanban")).clean


async def test_legacy_board_keeps_source_and_reports_history_gap(tmp_path):
    source = tmp_path / "kanban"
    shutil.copytree(PLUGIN, source)
    data = source / "data"
    data.mkdir(exist_ok=True)
    original = [{"id": "old", "title": "Old", "status": "done"}]
    legacy = data / "issues.json"
    legacy.write_text(json.dumps(original), encoding="utf-8")
    before = legacy.read_bytes()
    async with PluginTestHost(tmp_path / "host") as host:
        await host.load(source)
        result = await host.request(
            "GET",
            "/api/agent-kanban/issues/old/result",
        )
        assert result.status == 409
        assert legacy.read_bytes() == before
        assert (
            await host.request(
                "GET",
                "/api/agent-kanban/issues",
            )
        ).json() == {"issues": [{**original[0], "legacy_session": True}]}


async def test_io_cancellation_joins_waiter_before_releasing_owner(
    monkeypatch,
):
    spec = importlib.util.spec_from_file_location(
        "kanban_owned_io",
        PLUGIN / "backend/main.py",
        submodule_search_locations=[str(PLUGIN / "backend")],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    scope = ResourceScope(ResourceOwner("agent-kanban", 1), lambda: None)
    module._PLUGIN = SimpleNamespace(resources=scope)
    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()

    def blocking():
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(10):
            raise TimeoutError("Test did not release the IO operation")

    task = asyncio.create_task(module._blocking(blocking))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        await scope.close()
    assert scope.closed
