from __future__ import annotations

import json

import pytest

from tools.audit_autonomous import (
    AcceptanceFailure,
    _assert_no_machine_confirmed,
    _assert_occurrence_authority,
    _extract_image_hashes,
    _parse_sse_events,
    _validate_history_scenarios,
    _validate_provisional_exports,
)


def test_sse_parser_preserves_checkpoint_lineage_and_real_image_hashes() -> None:
    image_hash = "a" * 64
    body = "".join(
        (
            "id: 1\nevent: general_proposal_committed\n",
            'data: {"sequence":1,"proposal_revision":1,"provider_model":"gpt-live"}\n\n',
            "id: 2\nevent: general_auto_semantic_repair_committed\n",
            'data: {"sequence":2,"proposal_revision":2,"visual_artifact_sha256s":["',
            image_hash,
            '"]}\n\n',
            "id: 3\nevent: general_auto_review_completed\n",
            'data: {"sequence":3,"proposal_revision":2,"review_revision":1,"reviewer_kind":"machine"}\n\n',
        )
    )

    events = _parse_sse_events(body)

    assert [item["event_type"] for item in events] == [
        "general_proposal_committed",
        "general_auto_semantic_repair_committed",
        "general_auto_review_completed",
    ]
    assert events[1]["data"]["proposal_revision"] == 2
    assert _extract_image_hashes(events) == (image_hash,)


def test_machine_review_rejects_forged_confirmed_state_at_any_depth() -> None:
    valid = {
        "reviewer_kind": "machine",
        "components": [
            {
                "length": {"value_mm": 800, "state": "hypothesis"},
                "width": {"value_mm": None, "state": "unknown"},
                "quantity": {"value": 2, "state": "hypothesis"},
            }
        ],
    }
    _assert_no_machine_confirmed(valid)

    forged = json.loads(json.dumps(valid))
    forged["components"][0]["quantity"]["state"] = "confirmed"
    with pytest.raises(AcceptanceFailure, match="machine_confirmed_fact"):
        _assert_no_machine_confirmed(forged)


def test_occurrence_authority_accepts_observed_quantity_and_rejects_hypothesis_physical() -> None:
    observed = {
        "components": [{"id": "panel", "quantity": {"value": 2, "state": "observed"}}],
        "occurrences": [
            {"id": "panel:1", "component_id": "panel", "occurrence_index": 1},
            {"id": "panel:2", "component_id": "panel", "occurrence_index": 2},
        ],
        "scenario_occurrences": [],
    }
    evidence = _assert_occurrence_authority(observed)
    assert evidence == {"physical": 2, "provisional": 0}

    hypothesis = {
        "components": [
            {"id": "panel", "quantity": {"value": 2, "state": "hypothesis"}}
        ],
        "occurrences": [
            {"id": "panel:1", "component_id": "panel", "occurrence_index": 1}
        ],
        "scenario_occurrences": [],
    }
    with pytest.raises(AcceptanceFailure, match="physical_occurrence_without_authority"):
        _assert_occurrence_authority(hypothesis)


def test_provisional_exports_require_honest_csv_and_svg_labels() -> None:
    csv_payload = (
        b"component_id,occurrence_status,quantity_state,physical_occurrence_ids,scenario_occurrence_ids\r\n"
        b"panel-1,provisional,hypothesis,,provisional:panel-1:1\r\n"
    )
    svg_payload = (
        b'<svg><text>schematic; not manufacturing-ready</text>'
        b'<text>panel-1 [provisional scenario]</text></svg>'
    )

    evidence = _validate_provisional_exports(csv_payload, svg_payload)

    assert evidence["csv_occurrence_states"] == ["provisional"]
    assert evidence["svg_label"] == "provisional scenario"
    with pytest.raises(AcceptanceFailure, match="forged confirmed"):
        _validate_provisional_exports(
            csv_payload.replace(b"provisional", b"confirmed"), svg_payload
        )


def test_history_scenarios_accept_missing_numbers_but_require_exact_snapshot_provenance() -> None:
    response = {
        "run_id": "run-1",
        "proposal_revision": 2,
        "review_revision": 1,
        "status": "provisional",
        "missing_data": ["cost_scope"],
        "scenarios": [
            {
                "comparable_id": "published-19",
                "cost_subtotal": None,
                "manufacturing_hours": None,
                "result_provenance": [
                    {"record_id": "published-19", "origin": "published"}
                ],
            }
        ],
    }

    evidence = _validate_history_scenarios(response, "run-1", 2, 1)

    assert evidence["scenario_count"] == 1
    assert evidence["numeric_cost_count"] == 0
    assert evidence["numeric_hours_count"] == 0
    assert evidence["provenance_origins"] == ["published"]
