# -*- coding: utf-8 -*-
"""Creator startup failures retain SDK-owned cleanup and require a data root."""

from types import SimpleNamespace

import pytest

from qwenpaw.plugins import SDKError
from qwenpaw.plugins.resources import ResourceOwner, ResourceScope
from qwenpaw.plugins.storage import PluginConfig

from sdk_host import CreatorSDKHost, activate


def test_missing_data_root_does_not_silently_start_an_empty_install():
    context = SimpleNamespace(
        config=PluginConfig({}, {}),
        resources=None,
    )
    with pytest.raises(SDKError, match="existing Creator data directory"):
        CreatorSDKHost(context)


@pytest.mark.asyncio
async def test_partial_start_keeps_cleanup_owned_until_scope_close(tmp_path):
    scope = ResourceScope(ResourceOwner("qwenpaw-creator", 1), lambda: None)
    context = SimpleNamespace(
        config=PluginConfig({"data_root": str(tmp_path)}, {}),
        resources=scope,
    )
    marker = tmp_path / "opened"
    steps = []

    async def startup(*, host):
        assert host.data_root == tmp_path
        await host.run_sync(marker.write_text, "active", encoding="utf-8")
        steps.append("started")
        raise RuntimeError("media initialization failed")

    async def shutdown():
        marker.unlink()
        steps.append("closed")

    try:
        with pytest.raises(RuntimeError, match="media initialization failed"):
            await activate(context, startup=startup, shutdown=shutdown)
        assert marker.read_text(encoding="utf-8") == "active"
        assert steps == ["started"]
    finally:
        await scope.close()
    assert steps == ["started", "closed"]
    assert not marker.exists()
    assert scope.closed
