# -*- coding: utf-8 -*-
"""SDK lifecycle boundary for the existing Creator media runtime."""

from pathlib import Path

from qwenpaw.plugins import SDKError


class CreatorSDKHost:
    def __init__(self, context):
        self.resources = context.resources
        configured = context.config.get("data_root")
        if not configured:
            raise SDKError(
                "Creator SDK preview requires data_root pointing to the "
                "existing Creator data directory; automatic legacy "
                "directory migration is not available yet",
            )
        self.data_root = Path(configured).expanduser()
        if not self.data_root.is_absolute():
            raise SDKError("Creator data_root must be absolute")

    async def run_sync(self, function, *args, **kwargs):
        return await self.resources.run_sync(function, *args, **kwargs)


async def activate(context, *, startup, shutdown):
    """Register shutdown before startup so partial starts retain an owner."""
    host = CreatorSDKHost(context)
    context.resources.defer(shutdown, "Creator runtime shutdown")
    await startup(host=host)
