from __future__ import annotations

import pytest

from backend.app.contratos import modelos


def _source_payload() -> dict:
    return {
        "recording_id": "recording-" + "a" * 64,
        "recording_version": 1,
        "source_live_run_id": "run-" + "b" * 32,
        "source_result_revision": 1,
        "source_actor": "operadora",
        "provider_model": "model-test",
        "provider_response_ids": ["response-1"],
        "transcript_sha256": "c" * 64,
        "fingerprint": "d" * 64,
        "recorded_at": "2026-11-14T12:00:00+00:00",
    }


def test_recorded_replay_snapshot_requires_verifiable_live_source() -> None:
    replay_source_type = getattr(modelos, "ReplaySource", None)
    assert replay_source_type is not None
    source = replay_source_type.model_validate(_source_payload())
    replay = modelos.RunSnapshot(
        id="run-" + "e" * 32,
        mode="recorded_replay",
        state="needs_review",
        candidate_revision="ledger-1",
        result_revision=1,
        created_at="2026-11-14T12:01:00+00:00",
        replay_source=source,
    )
    assert replay.replay_source.source_live_run_id == "run-" + "b" * 32
    with pytest.raises(ValueError):
        modelos.RunSnapshot(
            id="run-" + "f" * 32,
            mode="recorded_replay",
            state="needs_review",
            candidate_revision="ledger-1",
            result_revision=1,
            created_at="2026-11-14T12:01:00+00:00",
        )
    with pytest.raises(ValueError):
        modelos.RunSnapshot(
            id="run-" + "1" * 32,
            mode="live",
            state="needs_review",
            candidate_revision="ledger-1",
            result_revision=1,
            created_at="2026-11-14T12:01:00+00:00",
            replay_source=source,
        )


def test_compare_candidates_args_require_revision_and_two_distinct_ids() -> None:
    args_type = getattr(modelos, "CompareCandidatesArgs", None)
    assert args_type is not None
    args = args_type(candidate_revision="ledger-1", candidate_ids=("candidate-a", "candidate-b"))
    assert args.candidate_ids == ("candidate-a", "candidate-b")
    with pytest.raises(ValueError):
        args_type(candidate_revision="ledger-1", candidate_ids=("candidate-a", "candidate-a"))
    with pytest.raises(ValueError):
        args_type(candidate_revision="ledger-1", candidate_ids=("candidate-a",))
    with pytest.raises(ValueError):
        args_type(candidate_revision="", candidate_ids=("candidate-a", "candidate-b"))
