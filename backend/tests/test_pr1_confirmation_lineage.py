from pathlib import Path

import pytest

from backend.app.contratos.modelos import ReviewRequest, TableConfirmedValue
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs, evaluate_table_program
from backend.app.servicios.repository import DemoRepository


def _values(analysis):
    first, second = analysis.measures[:2]
    return (
        TableConfirmedValue(confirmation_id="confirmation-shared", target_id=first.id, value_mm=10, reason="Primera"),
        TableConfirmedValue(confirmation_id="confirmation-shared", target_id=second.id, value_mm=20, reason="Segunda"),
    )


def test_review_request_rejects_duplicate_non_null_confirmation_ids() -> None:
    fixture = Path(__file__).resolve().parents[2] / "data/planos_demo/mesa_demo_001.dxf"
    analysis = analyze_mounted_table(extract_drawing(fixture, input_kind="mounted_orthographic_views"))
    program = catalog_table_programs(analysis)[0]
    with pytest.raises(ValueError, match="duplicate table confirmation ids"):
        ReviewRequest(
            base_result_revision=1, reviewer_name="alice", table_program_id=program.id,
            table_confirmed_values=_values(analysis), notes="No admite lineage ambiguo",
        )


def test_repository_updates_confirmation_owner_within_one_request(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "data/planos_demo/mesa_demo_001.dxf"
    extraction = extract_drawing(fixture, input_kind="mounted_orthographic_views")
    analysis = analyze_mounted_table(extraction)
    program = catalog_table_programs(analysis)[0]
    repository = DemoRepository(tmp_path / "lineage.sqlite3")
    repository.create_run(
        "run-lineage", "geometry_only", extraction, (), table_analysis=analysis,
        table_programs=(program,), evaluated_table_program=evaluate_table_program(analysis, program),
    )
    bypassed = ReviewRequest.model_construct(
        base_result_revision=1, reviewer_name="alice", table_program_id=program.id,
        table_confirmed_values=_values(analysis), notes="Simula payload previo al hardening",
    )
    with pytest.raises(ValueError, match="duplicate_confirmation_id"):
        repository.review("run-lineage", bypassed)
