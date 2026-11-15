from __future__ import annotations

import json

import pytest

from tools.backfill_library import (
    BackfillError,
    KNOWN_NON_REAL_SOURCE_SHA256,
    assess_candidate,
    library_save_payload,
    load_manifest,
    library_items_from_response,
    require_apply_preconditions,
    verify_published_items,
)


def _manifest_entry() -> dict[str, object]:
    return {
        "run_id": "run-11111111111111111111111111111111",
        "result_revision": 2,
        "label": "Armario proyecto A revisado",
        "embedding_mode": "embeddinggemma2",
        "provenance": {
            "source_kind": "real_furniture",
            "document_sha256": "a" * 64,
            "authorization_reference": "aprobacion-cliente-2026-11-14",
            "evidence_reference": "orden-trabajo-123",
            "attested_by": "operador",
            "approved_for_public_library": True,
        },
    }


def _api_evidence() -> tuple[dict, list[dict], dict, dict]:
    run = {
        "run": {
            "id": "run-11111111111111111111111111111111",
            "document_id": "doc-22222222222222222222222222222222",
        }
    }
    revisions = [
        {
            "run_id": run["run"]["id"],
            "result_revision": 2,
            "state": "completed",
            "review": {
                "reviewer_name": "revisor-humano",
                "reason": "Medidas y despiece contrastados con la orden de trabajo.",
            },
        }
    ]
    document = {"source": {"sha256": "a" * 64, "filename": "armario-a.dxf"}}
    drawing = {"synthetic": False}
    return run, revisions, document, drawing


def test_manifest_requires_explicit_real_source_authorization(tmp_path) -> None:
    payload = {"schema_version": "1.0", "backup_reference": None, "entries": [_manifest_entry()]}
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = load_manifest(path)

    assert manifest.entries[0].provenance.source_kind == "real_furniture"
    assert manifest.entries[0].provenance.approved_for_public_library is True


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("source_kind", "demo", "source_not_real_furniture"),
        ("approved_for_public_library", False, "public_library_not_approved"),
        ("authorization_reference", "", "missing_authorization_reference"),
        ("evidence_reference", "", "missing_evidence_reference"),
    ],
)
def test_manifest_rejects_demo_or_unproven_selection(tmp_path, field, value, error) -> None:
    entry = _manifest_entry()
    entry["provenance"][field] = value
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps({"schema_version": "1.0", "backup_reference": None, "entries": [entry]}),
        encoding="utf-8",
    )

    with pytest.raises(BackfillError, match=error):
        load_manifest(path)


def test_assessment_accepts_only_matching_non_synthetic_reviewed_revision(tmp_path) -> None:
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps({"schema_version": "1.0", "backup_reference": None, "entries": [_manifest_entry()]}),
        encoding="utf-8",
    )
    entry = load_manifest(path).entries[0]
    run, revisions, document, drawing = _api_evidence()

    assessment = assess_candidate(entry, run, revisions, document, drawing)

    assert assessment.eligible is True
    assert assessment.reviewer_name == "revisor-humano"
    assert assessment.source_sha256 == "a" * 64


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("unreviewed", "review_required"),
        ("needs_review", "completed_revision_required"),
        ("synthetic", "synthetic_drawing_not_allowed"),
        ("hash_mismatch", "document_sha256_mismatch"),
        ("known_demo", "known_non_real_source"),
    ],
)
def test_assessment_rejects_unreviewed_synthetic_or_demo_source(
    tmp_path, mutation, expected_reason
) -> None:
    entry_payload = _manifest_entry()
    run, revisions, document, drawing = _api_evidence()
    if mutation == "unreviewed":
        revisions[0]["review"] = None
    elif mutation == "needs_review":
        revisions[0]["state"] = "needs_review"
    elif mutation == "synthetic":
        drawing["synthetic"] = True
    elif mutation == "hash_mismatch":
        document["source"]["sha256"] = "b" * 64
    else:
        known = next(iter(KNOWN_NON_REAL_SOURCE_SHA256))
        entry_payload["provenance"]["document_sha256"] = known
        document["source"]["sha256"] = known
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps({"schema_version": "1.0", "backup_reference": None, "entries": [entry_payload]}),
        encoding="utf-8",
    )
    entry = load_manifest(path).entries[0]

    assessment = assess_candidate(entry, run, revisions, document, drawing)

    assert assessment.eligible is False
    assert expected_reason in assessment.reasons


def test_library_response_supports_legacy_and_counted_envelopes() -> None:
    item = {"id": "library-run-1", "run_id": "run-1"}

    assert library_items_from_response({"data": [item]}) == [item]
    assert library_items_from_response({"data": {"items": [item], "design_count": 1}}) == [item]


def test_apply_requires_concrete_pre_import_backup_reference(tmp_path) -> None:
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps({"schema_version": "1.0", "backup_reference": None, "entries": [_manifest_entry()]}),
        encoding="utf-8",
    )

    with pytest.raises(BackfillError, match="backup_reference_required_for_apply"):
        require_apply_preconditions(load_manifest(path))


def test_save_payload_carries_accountable_publication_gate(tmp_path) -> None:
    payload = {"schema_version": "1.0", "backup_reference": "backup-v2-20261114", "entries": [_manifest_entry()]}
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    request = library_save_payload(load_manifest(path).entries[0])

    assert request["publication"] == {
        "source_kind": "real_furniture",
        "source_reference": "orden-trabajo-123",
        "approved_for_public_library": True,
    }


def test_post_apply_verification_requires_server_attestation(tmp_path) -> None:
    payload = {"schema_version": "1.0", "backup_reference": "backup-v2-20261114", "entries": [_manifest_entry()]}
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = load_manifest(path)
    published_without_attestation = {
        manifest.entries[0].run_id: {
            "run_id": manifest.entries[0].run_id,
            "result_revision": 2,
            "publication": None,
        }
    }

    with pytest.raises(BackfillError, match="library_publication_verification_failed"):
        verify_published_items(manifest, published_without_attestation)





