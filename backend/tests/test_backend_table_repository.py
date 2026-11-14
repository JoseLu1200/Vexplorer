from pathlib import Path

import pytest

from backend.app.contratos.modelos import ReviewRequest, TableReviewDecision
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs, evaluate_table_program
from backend.app.servicios.repository import DemoRepository


FIXTURE = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "mesa_demo_001.dxf"


def _setup(repository: DemoRepository):
    extraction = extract_drawing(FIXTURE, input_kind="mounted_orthographic_views")
    analysis = analyze_mounted_table(extraction)
    programs = catalog_table_programs(analysis)
    selected = programs[0]
    repository.create_run("run-table", "geometry_only", extraction, (), document_id="doc-" + "a" * 32, table_analysis=analysis, table_programs=(selected,), evaluated_table_program=evaluate_table_program(analysis, selected))
    return analysis, selected


def _accept_all(program):
    return (
        TableReviewDecision(target_kind="program", target_id=program.id, action="accept", reason="Selecciona topología y bindings"),
        *(TableReviewDecision(target_kind="component", target_id=item.id, action="accept", reason="Acepta componente propuesto") for item in program.components),
        *(TableReviewDecision(target_kind="premise", target_id=item.id, action="accept", reason="Acepta premisa explícita") for item in program.premises),
    )


def test_table_review_recalculates_and_preserves_prior_revision(tmp_path):
    repository = DemoRepository(tmp_path / "table.sqlite3")
    _, program = _setup(repository)
    before = repository.get_result("run-table", 1)
    assert before.evaluated_table_program.state == "hypothesis"

    reviewed = repository.review("run-table", ReviewRequest(base_result_revision=1, reviewer_name="Técnica local", table_program_id=program.id, table_decisions=_accept_all(program), notes="Acepta mesa de soportes laterales"))
    assert reviewed.result_revision == 2 and reviewed.state == "completed"
    assert reviewed.evaluated_table_program.state == "completed"
    assert reviewed.selected_table_program_id == program.id
    assert repository.get_result("run-table", 1) == before

    unchanged = repository.review("run-table", ReviewRequest(base_result_revision=2, reviewer_name="Técnica local", table_program_id=program.id, notes="Conserva decisiones previas"))
    assert unchanged.state == "completed"
    assert unchanged.table_review_decisions == reviewed.table_review_decisions
    assert repository.get_result("run-table", 2) == reviewed


def test_table_review_rejects_stale_revision(tmp_path):
    repository = DemoRepository(tmp_path / "table.sqlite3")
    _, program = _setup(repository)
    repository.review("run-table", ReviewRequest(base_result_revision=1, reviewer_name="Técnica", table_program_id=program.id, table_decisions=_accept_all(program), notes="Acepta"))
    with pytest.raises(ValueError, match="stale_result_revision"):
        repository.review("run-table", ReviewRequest(base_result_revision=1, reviewer_name="Técnica", table_program_id=program.id, notes="Obsoleta"))
