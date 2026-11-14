from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.app.agente.replay import MAX_RECORDED_TRANSCRIPT_BYTES
from backend.app.servicios.repository import DemoRepository


def _reserve(repository: DemoRepository, reservation_id: str) -> bool:
    try:
        repository.reserve_agent_recording(
            reservation_id,
            fingerprint="a" * 64,
            actor="alice",
            max_count=1,
            max_bytes=MAX_RECORDED_TRANSCRIPT_BYTES,
            reserved_bytes=MAX_RECORDED_TRANSCRIPT_BYTES,
        )
    except ValueError as exc:
        assert str(exc) == "recording_storage_exhausted"
        return False
    return True


def test_concurrent_recording_reservations_do_not_overcommit_one_slot(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "reservations.sqlite3")
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(
            lambda index: _reserve(repository, f"reservation-{index}"), range(2),
        ))
    assert sorted(outcomes) == [False, True]
    assert repository.recording_storage_usage() == {
        "recording_count": 0, "recording_bytes": 0,
        "reservation_count": 1, "reserved_bytes": MAX_RECORDED_TRANSCRIPT_BYTES,
    }


def test_failed_live_releases_reservation_and_restart_clears_stale_reservations(tmp_path: Path) -> None:
    path = tmp_path / "reservations.sqlite3"
    repository = DemoRepository(path)
    assert _reserve(repository, "reservation-failed") is True
    repository.release_agent_recording_reservation("reservation-failed")
    assert repository.recording_storage_usage()["reservation_count"] == 0

    assert _reserve(repository, "reservation-interrupted") is True
    restarted = DemoRepository(path)
    assert restarted.release_stale_agent_recording_reservations() == 1
    assert _reserve(restarted, "reservation-after-restart") is True


def test_reservation_parameters_fail_closed(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "reservations.sqlite3")
    with pytest.raises(ValueError, match="invalid_recording_storage_policy"):
        repository.reserve_agent_recording(
            "reservation-invalid", fingerprint="a" * 64, actor="alice",
            max_count=15, max_bytes=1, reserved_bytes=MAX_RECORDED_TRANSCRIPT_BYTES,
        )
