# sse_manager.py
import asyncio
from typing import Dict, Optional


class SSEManager:
    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self):
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.get_event_loop()
        return self._loop

    def create_stream(self, search_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._queues[search_id] = queue
        return queue

    def get_queue(self, search_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(search_id)

    def push(self, search_id: str, job: dict):
        """Thread-safe push — called from spider subprocess via HTTP."""
        queue = self._queues.get(search_id)
        if not queue:
            return
        try:
            loop = self._get_loop()
            loop.call_soon_threadsafe(queue.put_nowait, job)
        except Exception:
            pass

    def close_stream(self, search_id: str):
        """Signal frontend that scraping is done."""
        queue = self._queues.get(search_id)
        if queue:
            try:
                loop = self._get_loop()
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"__done__": True}
                )
            except Exception:
                pass
        self._queues.pop(search_id, None)

    def error_stream(self, search_id: str, message: str):
        """Signal an error to the frontend."""
        queue = self._queues.get(search_id)
        if queue:
            try:
                loop = self._get_loop()
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"__error__": message}
                )
            except Exception:
                pass
        self._queues.pop(search_id, None)