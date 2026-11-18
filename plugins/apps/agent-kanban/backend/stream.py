# -*- coding: utf-8 -*-
"""Bounded Kanban notifications; disconnect does not cancel an issue."""

import asyncio
import json


class SSEChannel:
    def __init__(self):
        self.queue = asyncio.Queue(maxsize=1000)
        self.closed = False

    async def send_event(self, data):
        if not self.closed:
            if self.queue.full():
                self.queue.get_nowait()
            self.queue.put_nowait(data)

    def close(self):
        self.closed = True
        if not self.queue.full():
            self.queue.put_nowait(None)

    async def __aiter__(self):
        while not self.closed or not self.queue.empty():
            try:
                item = await asyncio.wait_for(self.queue.get(), 30)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if item is None:
                return
            yield "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
