# -*- coding: utf-8 -*-
"""Lifecycle-only SDK preview; not a replacement for Creator's HTTP app."""

# The host loads this file as an isolated package.
# pylint: disable=relative-beyond-top-level
from .main import _startup, _shutdown
from .sdk_host import activate

# pylint: enable=relative-beyond-top-level


class Plugin:
    def register(self, context):
        async def start(active):
            await activate(active, startup=_startup, shutdown=_shutdown)

        context.on_activate(start)


plugin = Plugin()
