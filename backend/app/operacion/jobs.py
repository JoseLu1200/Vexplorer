from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import Callable


class BoundedJobExecutor:
    """One process-local worker with a bounded durable admission queue."""

    def __init__(self, max_pending: int) -> None:
        if not 1 <= max_pending <= 100:
            raise ValueError("invalid_job_max_pending")
        self._capacity = BoundedSemaphore(max_pending)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vexplorer-job")

    def reserve(self) -> bool:
        return self._capacity.acquire(blocking=False)

    def release(self) -> None:
        self._capacity.release()

    def submit_reserved(self, function: Callable[[], None]) -> None:
        def run() -> None:
            try:
                function()
            finally:
                self.release()

        try:
            self._executor.submit(run)
        except BaseException:
            self.release()
            raise

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
