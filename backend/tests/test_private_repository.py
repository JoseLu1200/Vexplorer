from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pytest

from backend.app.contratos.modelos import (
    Bounds2D,
    ComponentProposal,
    DecompositionScenario,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingObservation,
    DrawingView,
    Evidence,
    ObservedDimension,
    Point2D,
    ReviewDecision,
    ReviewRequest,
    TableConfirmedValue,
    TableReviewDecision,
)
from backend.app.estimacion.service import estimate_result
from backend.app.historico.service import find_comparables
from backend.app.servicios.repository import DemoRepository
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs, evaluate_table_program


def _extraction() -> DrawingExtraction:
    points = (
        Point2D(x=0, y=0), Point2D(x=900, y=0),
        Point2D(x=900, y=1800), Point2D(x=0, y=1800),
    )
    return DrawingExtraction(
        drawing_id="drawing-private", status="ready", source_unit="mm",
        unit_scale_to_mm=1, coordinate_unit="mm",
        entities=(DrawingEntity(id="entity-front", kind="LWPOLYLINE", layer="VIEW_GEOMETRY", source_points=points, points_mm=points),),
        views=(DrawingView(id="view-front", label="FRONT", entity_ids=("entity-front",), bounds_source=Bounds2D(min_x=0, min_y=0, max_x=900, max_y=1800), bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=900, max_y=1800)),),
        contours=(DrawingContour(id="contour-front", view_id="view-front", source_entity_ids=("entity-front",), points_source=points, points_mm=points, closed=True),),
        dimensions=(ObservedDimension(id="dim-width", kind="overall", value_mm=900, source_entity_ids=("entity-front",), evidence_ids=("evidence-front",), origin="observed"),),
        evidence=(Evidence(id="evidence-front", kind="geometry", source_entity_ids=("entity-front",), description="Contorno observado"),),
        observations=(DrawingObservation(id="observation-front", view_id="view-front", contour_ids=("contour-front",), dimension_ids=("dim-width",)),),
        warnings=("mounting_ambiguous",), synthetic=True,
    )


def _scenario() -> DecompositionScenario:
    return DecompositionScenario(
        id="scenario-basic", title="Escenario",
        components=(ComponentProposal(
            id="proposal-panel", label="Panel", role="unknown", quantity=None,
            length_mm=900, width_mm=None, thickness_mm=None,
            source_observation_ids=("observation-front",),
            source_contour_ids=("contour-front",), evidence_ids=("evidence-front",),
            assumptions=("Requiere confirmación",),
        ),), assumptions=("Requiere confirmación",),
    )


def _review(*, width: float = 320, reviewer: str = "spoofed") -> ReviewRequest:
    return ReviewRequest(
        base_result_revision=1, reviewer_name=reviewer,
        decisions=(ReviewDecision(
            proposal_id="proposal-panel", action="confirm", role="shelf", quantity=2,
            length_mm=900, width_mm=width, thickness_mm=19,
            material="tablero sintético", finish="melamina sintética", notes="Confirmado",
        ),),
    )


def _repository(tmp_path: Path) -> DemoRepository:
    repository = DemoRepository(tmp_path / "private.sqlite3")
    repository.create_run("run-private", "geometry_only", _extraction(), (_scenario(),))
    return repository


def _append_without_error(repository: DemoRepository, index: int) -> str | None:
    try:
        repository.append_event("run-private", "parallel", {"index": index})
    except Exception as exc:  # pragma: no cover - returned as assertion evidence
        return type(exc).__name__
    return None


def test_parallel_events_receive_contiguous_unique_sequences(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with ThreadPoolExecutor(max_workers=20) as executor:
        failures = list(executor.map(
            lambda index: _append_without_error(repository, index), range(100)
        ))

    assert failures == [None] * 100
    events = repository.get_events("run-private")
    assert [event["sequence"] for event in events] == list(range(1, 104))


def test_review_and_audit_event_commit_atomically_with_authenticated_actor(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    result = repository.review(
        "run-private", _review(), idempotency_key="review-1", actor="alice"
    )

    assert result.review is not None and result.review.reviewer_name == "alice"
    event = repository.get_events("run-private")[-1]
    assert event["event_type"] == "human_review_committed"
    assert event["data"]["result_revision"] == 2
    assert event["data"]["reviewer_name"] == "alice"


def test_review_idempotency_replays_same_request_and_rejects_key_reuse(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    first = repository.review(
        "run-private", _review(), idempotency_key="review-1", actor="alice"
    )
    replay = repository.review(
        "run-private", _review(), idempotency_key="review-1", actor="alice"
    )

    assert replay == first
    assert len(repository.get_results("run-private")) == 2
    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        repository.review(
            "run-private", _review(width=321), idempotency_key="review-1", actor="alice"
        )


def test_economic_revision_cannot_be_silently_overwritten(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    reviewed = repository.review(
        "run-private", _review(), idempotency_key="review-1", actor="alice"
    )
    estimate = estimate_result(reviewed, find_comparables(reviewed))
    repository.save_estimate("run-private", estimate)

    repository.save_estimate("run-private", estimate)
    changed = estimate.model_copy(update={"total": estimate.total + 1})
    with pytest.raises(ValueError, match="economic_revision_conflict"):
        repository.save_estimate("run-private", changed)

    assert repository.get_estimate("run-private", reviewed.result_revision) == estimate


def test_economic_snapshot_rolls_back_when_audit_event_fails(tmp_path: Path, monkeypatch) -> None:
    repository = _repository(tmp_path)
    reviewed = repository.review(
        "run-private", _review(), idempotency_key="review-1", actor="alice"
    )
    estimate = estimate_result(reviewed, find_comparables(reviewed))
    monkeypatch.setattr(
        repository,
        "_append_event_in_transaction",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("event_fault")),
    )

    with pytest.raises(RuntimeError, match="event_fault"):
        repository.save_estimate("run-private", estimate)

    with pytest.raises(KeyError):
        repository.get_estimate("run-private", reviewed.result_revision)


def test_table_confirmation_chain_replaces_effective_value_and_preserves_history(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "mesa_demo_001.dxf"
    extraction = extract_drawing(fixture, input_kind="mounted_orthographic_views")
    analysis = analyze_mounted_table(extraction)
    program = catalog_table_programs(analysis)[1]
    repository = DemoRepository(tmp_path / "table-chain.sqlite3")
    repository.create_run(
        "run-table", "geometry_only", extraction, (), table_analysis=analysis,
        table_programs=(program,), evaluated_table_program=evaluate_table_program(analysis, program),
    )
    decisions = (
        TableReviewDecision(target_kind="program", target_id=program.id, action="accept", reason="Acepta programa"),
        *(TableReviewDecision(target_kind="component", target_id=item.id, action="accept", reason="Acepta componente") for item in program.components),
        *(TableReviewDecision(target_kind="premise", target_id=item.id, action="accept", reason="Acepta premisa") for item in program.premises),
    )
    slot = next(item for item in analysis.measures if item.semantic == "support_depth")
    first = TableConfirmedValue(
        confirmation_id="confirmation-r2", target_id=slot.id, value_mm=60,
        reason="Primera medición",
    )
    amended = TableConfirmedValue(
        confirmation_id="confirmation-r3", supersedes_confirmation_id=first.confirmation_id,
        target_id=slot.id, value_mm=70, reason="Medición repetida",
    )

    revision_two = repository.review(
        "run-table",
        ReviewRequest(base_result_revision=1, reviewer_name="alice", table_program_id=program.id, table_decisions=decisions, table_confirmed_values=(first,), notes="Primera revisión"),
        idempotency_key="r2", actor="alice",
    )
    revision_three = repository.review(
        "run-table",
        ReviewRequest(base_result_revision=2, reviewer_name="alice", table_program_id=program.id, table_confirmed_values=(amended,), notes="Corrige valor humano"),
        idempotency_key="r3", actor="alice",
    )

    assert revision_two.table_confirmed_values == (first,)
    assert revision_three.table_confirmed_values == (amended,)
    assert repository.get_result("run-table", 2) == revision_two
    support_r2 = next(item for item in revision_two.evaluated_table_program.components if item.role == "corner_support")
    support_r3 = next(item for item in revision_three.evaluated_table_program.components if item.role == "corner_support")
    assert support_r2.width.value_mm == 60
    assert support_r3.width.value_mm == 70
    raw_slot = next(item for item in revision_three.table_analysis.measures if item.id == slot.id)
    assert raw_slot.value_mm is None and raw_slot.state == "unknown"


def test_repository_upgrades_legacy_cost_primary_key_without_losing_payload(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE table_cost_estimates (run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (run_id, revision))"
        )
        db.execute(
            "INSERT INTO table_cost_estimates VALUES ('run-old', 2, ?)",
            ('{"schema_version":"0.5.0","estimate_id":null}',),
        )

    DemoRepository(path)

    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(table_cost_estimates)")}
        row = db.execute(
            "SELECT run_id,revision,estimate_id,payload FROM table_cost_estimates"
        ).fetchone()
    assert columns == {"run_id", "revision", "estimate_id", "payload"}
    assert row[:2] == ("run-old", 2)
    assert len(row[2]) == 64
    assert row[3] == '{"schema_version":"0.5.0","estimate_id":null}'
