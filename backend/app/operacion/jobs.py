from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import BoundedSemaphore, Lock
from typing import Callable


@dataclass
class _SubmittedJob:
    future: Future[None] | None = None
    running: bool = False


class BoundedJobExecutor:
    """Process-local workers with bounded admission and queued cancellation."""

    def __init__(self, max_pending: int, max_workers: int = 1) -> None:
        if not 1 <= max_pending <= 100:
            raise ValueError("invalid_job_max_pending")
        if not 1 <= max_workers <= min(4, max_pending):
            raise ValueError("invalid_job_max_workers")
        self._capacity = BoundedSemaphore(max_pending)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="vexplorer-job"
        )
        self._lock = Lock()
        self._submitted: OrderedDict[str, _SubmittedJob] = OrderedDict()
        self._anonymous_sequence = 0

    def reserve(self) -> bool:
        return self._capacity.acquire(blocking=False)

    def release(self) -> None:
        self._capacity.release()

    def submit_reserved(
        self, function: Callable[[], None], *, job_id: str | None = None
    ) -> None:
        job_id = job_id or getattr(function, "__vexplorer_job_id__", None)
        with self._lock:
            if job_id is None:
                self._anonymous_sequence += 1
                key = f"anonymous-{self._anonymous_sequence}"
            else:
                key = job_id
            if key in self._submitted:
                self.release()
                raise ValueError("job_already_submitted")
            submitted = _SubmittedJob()
            self._submitted[key] = submitted

        def run() -> None:
            with self._lock:
                submitted.running = True
            try:
                function()
            finally:
                with self._lock:
                    self._submitted.pop(key, None)
                self.release()

        try:
            with self._lock:
                submitted.future = self._executor.submit(run)
        except BaseException:
            with self._lock:
                self._submitted.pop(key, None)
            self.release()
            raise

    def cancel_queued(self, job_id: str) -> bool:
        """Remove a submitted job only while the worker has not started it."""
        with self._lock:
            submitted = self._submitted.get(job_id)
            if (
                submitted is None
                or submitted.running
                or submitted.future is None
                or not submitted.future.cancel()
            ):
                return False
            self._submitted.pop(job_id, None)
        self.release()
        return True

    def queue_position(self, job_id: str) -> int | None:
        """Return a one-based position among process-local queued jobs."""
        with self._lock:
            position = 0
            for key, submitted in self._submitted.items():
                if submitted.running:
                    continue
                position += 1
                if key == job_id:
                    return position
        return None

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
