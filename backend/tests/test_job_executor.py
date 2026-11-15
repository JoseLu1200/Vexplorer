from __future__ import annotations

from threading import Event, Lock

from backend.app.operacion.jobs import BoundedJobExecutor


def test_executor_runs_two_jobs_concurrently_and_keeps_admission_bounded() -> None:
    executor = BoundedJobExecutor(max_pending=3, max_workers=2)
    release = Event()
    both_started = Event()
    started: list[str] = []
    lock = Lock()

    def work(job_id: str) -> None:
        with lock:
            started.append(job_id)
            if len(started) == 2:
                both_started.set()
        assert release.wait(2)

    try:
        for job_id in ("job-1", "job-2", "job-3"):
            assert executor.reserve() is True
            executor.submit_reserved(lambda value=job_id: work(value), job_id=job_id)

        assert executor.reserve() is False
        assert both_started.wait(2)
        assert set(started) == {"job-1", "job-2"}
        assert executor.queue_position("job-3") == 1
    finally:
        release.set()
        executor.shutdown()


def test_cancelling_queued_job_releases_capacity_without_running_it() -> None:
    executor = BoundedJobExecutor(max_pending=2, max_workers=1)
    release = Event()
    started = Event()
    queued_ran = Event()

    def running() -> None:
        started.set()
        assert release.wait(2)

    try:
        assert executor.reserve() is True
        executor.submit_reserved(running, job_id="job-running")
        assert started.wait(2)
        assert executor.reserve() is True
        executor.submit_reserved(queued_ran.set, job_id="job-queued")

        assert executor.cancel_queued("job-queued") is True
        assert executor.cancel_queued("job-queued") is False
        assert executor.queue_position("job-queued") is None
        assert executor.reserve() is True
        executor.release()
    finally:
        release.set()
        executor.shutdown()

    assert queued_ran.is_set() is False


def test_running_job_cannot_be_cancelled_by_executor() -> None:
    executor = BoundedJobExecutor(max_pending=1, max_workers=1)
    release = Event()
    started = Event()

    def running() -> None:
        started.set()
        assert release.wait(2)

    try:
        assert executor.reserve() is True
        executor.submit_reserved(running, job_id="job-running")
        assert started.wait(2)
        assert executor.cancel_queued("job-running") is False
    finally:
        release.set()
        executor.shutdown()
