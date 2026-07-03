"""Small background-task boundary for the current synchronous integrations."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable


logger = logging.getLogger(__name__)


class BackgroundTaskRunner:
    """Starts daemon workers and tracks them for orderly application shutdown."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads: set[threading.Thread] = set()

    def submit(self, task: Callable[[], None], *, name: str) -> threading.Thread:
        def run_and_release() -> None:
            try:
                task()
            except Exception:
                logger.exception("Unhandled error in background task %s", name)
            finally:
                with self._lock:
                    self._threads.discard(threading.current_thread())

        thread = threading.Thread(
            target=run_and_release,
            name=f"sammyai-{name}",
            daemon=True,
        )
        with self._lock:
            self._threads.add(thread)
        thread.start()
        return thread

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(thread.is_alive() for thread in self._threads)

    def shutdown(self, timeout: float = 0.25) -> None:
        with self._lock:
            threads = tuple(self._threads)
        for thread in threads:
            thread.join(timeout=timeout)
