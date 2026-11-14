from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from backend.app.operacion.public_access import (
    PublicAdmissionLimits,
    PublicAdmissionStore,
)


class MutableClock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _limits(**changes: int) -> PublicAdmissionLimits:
    return replace(PublicAdmissionLimits(), **changes)


def test_upload_limit_persists_across_store_restart_and_hashes_ip(tmp_path: Path) -> None:
    path = tmp_path / "vexplorer.sqlite3"
    clock = MutableClock(100_000)
    limits = _limits(per_ip_uploads_daily=2, global_uploads_daily=10)
    first = PublicAdmissionStore(path, limits=limits, clock=clock)

    assert first.admit_mutation("203.0.113.8", "upload").allowed
    assert first.admit_mutation("203.0.113.8", "upload").allowed

    restarted = PublicAdmissionStore(path, limits=limits, clock=clock)
    rejected = restarted.admit_mutation("203.0.113.8", "upload")
    assert not rejected.allowed
    assert rejected.status_code == 429
    assert rejected.code == "public_upload_daily_limit"
    assert rejected.retry_after_seconds == 86_400
    with sqlite3.connect(path) as database:
        stored = database.execute(
            "SELECT DISTINCT ip_hash FROM public_admission_events"
        ).fetchall()
        key_count = database.execute(
            "SELECT COUNT(*) FROM public_admission_metadata WHERE name = 'ip_hash_key'"
        ).fetchone()[0]
    assert key_count == 1
    assert stored and all(len(row[0]) == 64 for row in stored)
    assert all("203.0.113.8" not in row[0] for row in stored)


def test_rolling_windows_expire_at_the_boundary(tmp_path: Path) -> None:
    clock = MutableClock(200_000)
    store = PublicAdmissionStore(
        tmp_path / "vexplorer.sqlite3",
        limits=_limits(
            per_ip_uploads_daily=1,
            global_uploads_daily=10,
            per_ip_mutations_minute=2,
        ),
        clock=clock,
    )
    assert store.admit_mutation("198.51.100.2", "upload").allowed
    blocked = store.admit_mutation("198.51.100.2", "other")
    assert blocked.allowed
    minute_limited = store.admit_mutation("198.51.100.2", "job")
    assert minute_limited.code == "public_mutation_rate_limited"
    assert minute_limited.retry_after_seconds == 60

    clock.value += 60
    assert store.admit_mutation("198.51.100.2", "other").allowed
    daily_limited = store.admit_mutation("198.51.100.2", "upload")
    assert daily_limited.code == "public_upload_daily_limit"
    assert daily_limited.retry_after_seconds == 86_340

    clock.value += 86_340
    assert store.admit_mutation("198.51.100.2", "upload").allowed


def test_global_job_quota_is_atomic_under_concurrency(tmp_path: Path) -> None:
    store = PublicAdmissionStore(
        tmp_path / "vexplorer.sqlite3",
        limits=_limits(
            global_jobs_daily=7,
            per_ip_jobs_daily=7,
            per_ip_mutations_minute=100,
        ),
        clock=lambda: 300_000,
    )

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(executor.map(
            lambda index: store.admit_mutation(f"192.0.2.{index + 1}", "job"),
            range(20),
        ))

    assert sum(decision.allowed for decision in decisions) == 7
    assert {decision.code for decision in decisions if not decision.allowed} == {
        "public_job_daily_limit"
    }
    with sqlite3.connect(tmp_path / "vexplorer.sqlite3") as database:
        assert database.execute(
            "SELECT COUNT(*) FROM public_admission_events WHERE action = 'job'"
        ).fetchone()[0] == 7


@pytest.mark.parametrize(
    ("content_length", "status_code", "code"),
    [
        (str(21 * 1024 * 1024 + 1), 413, "upload_content_length_exceeded"),
        ("9" * 10_000, 413, "upload_content_length_exceeded"),
        ("not-a-number", 400, "invalid_content_length"),
        (-1, 400, "invalid_content_length"),
    ],
)
def test_upload_content_length_is_rejected_before_quota_consumption(
    tmp_path: Path,
    content_length: str | int,
    status_code: int,
    code: str,
) -> None:
    path = tmp_path / f"{code}-{status_code}.sqlite3"
    store = PublicAdmissionStore(path, clock=lambda: 400_000)

    rejected = store.admit_mutation("203.0.113.9", "upload", content_length=content_length)

    assert not rejected.allowed
    assert rejected.status_code == status_code
    assert rejected.code == code
    assert rejected.retry_after_seconds is None
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT COUNT(*) FROM public_admission_events").fetchone()[0] == 0


def test_upload_content_length_allows_multipart_overhead_at_21_mib(tmp_path: Path) -> None:
    store = PublicAdmissionStore(tmp_path / "vexplorer.sqlite3", clock=lambda: 500_000)

    decision = store.admit_mutation(
        "203.0.113.10",
        "upload",
        content_length=str(21 * 1024 * 1024),
    )

    assert decision.allowed


def test_cleanup_deletes_only_a_bounded_batch_of_expired_rows(tmp_path: Path) -> None:
    path = tmp_path / "vexplorer.sqlite3"
    clock = MutableClock(1_000_000)
    store = PublicAdmissionStore(
        path,
        limits=_limits(cleanup_batch_size=2),
        clock=clock,
        ip_hash_key=b"test-key-material-that-is-long-enough",
    )
    with sqlite3.connect(path) as database:
        database.executemany(
            "INSERT INTO public_admission_events (occurred_at, ip_hash, action) VALUES (?, ?, 'other')",
            [(1.0 + index, "0" * 64) for index in range(5)],
        )

    assert store.admit_mutation("203.0.113.11", "other").allowed

    with sqlite3.connect(path) as database:
        expired = database.execute(
            "SELECT COUNT(*) FROM public_admission_events WHERE occurred_at < ?",
            (clock.value - 86_400,),
        ).fetchone()[0]
    assert expired == 3


def test_caller_transaction_controls_admission_rollback_and_commit(tmp_path: Path) -> None:
    path = tmp_path / "vexplorer.sqlite3"
    store = PublicAdmissionStore(path, clock=lambda: 1_100_000)
    database = sqlite3.connect(path, isolation_level=None)
    try:
        database.execute("BEGIN IMMEDIATE")
        assert store.admit_mutation("203.0.113.12", "job", database=database).allowed
        database.rollback()
        assert database.execute("SELECT COUNT(*) FROM public_admission_events").fetchone()[0] == 0

        database.execute("BEGIN IMMEDIATE")
        assert store.admit_mutation("203.0.113.12", "job", database=database).allowed
        database.commit()
        assert database.execute("SELECT COUNT(*) FROM public_admission_events").fetchone()[0] == 1
    finally:
        database.close()


@pytest.mark.parametrize(
    "limits",
    [
        _limits(global_uploads_daily=0),
        _limits(per_ip_uploads_daily=101, global_uploads_daily=100),
        _limits(per_ip_jobs_daily=101, global_jobs_daily=100),
        _limits(per_ip_mutations_minute=0),
        _limits(max_content_length_bytes=0),
        _limits(cleanup_batch_size=0),
    ],
)
def test_invalid_limits_fail_closed(limits: PublicAdmissionLimits) -> None:
    with pytest.raises(ValueError, match="invalid_public_admission_limits"):
        PublicAdmissionStore(Path("unused.sqlite3"), limits=limits)


def test_invalid_explicit_hash_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid_ip_hash_key"):
        PublicAdmissionStore(tmp_path / "vexplorer.sqlite3", ip_hash_key=b"short")
