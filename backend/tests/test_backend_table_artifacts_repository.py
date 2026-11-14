from backend.app.contratos.modelos import (
    TableCostConcept,
    TableCostEstimate,
    TableCostScope,
    TableDrawingArtifactData,
    TableDrawingExports,
    TableDrawingFormatLink,
    TableDrawingManifest,
    TableDrawingManifestSheet,
)
from backend.app.servicios.repository import DemoRepository
from backend.tests.test_backend_semantic import _completed_table_result


def test_table_cost_and_drawing_artifacts_are_revision_and_hash_bound(tmp_path, monkeypatch):
    repository = DemoRepository(tmp_path / "table-artifacts.sqlite3")
    result = _completed_table_result()
    monkeypatch.setattr(repository, "get_result", lambda run_id, revision=None: result)
    program_hash = result.evaluated_table_program.program_hash
    cost = TableCostEstimate(
        result_revision=2, program_hash=program_hash, catalog_version="table-costs-v1", scope=TableCostScope(),
        concepts=(TableCostConcept(id="missing-material", label="Material", concept_type="material_area", formula="area", quantity=2, quantity_unit="m2", rate_unit="EUR/m2", state="unknown", required=True),),
        known_subtotal_eur=0, total_state="partial",
    )
    repository.save_table_cost_estimate("run-table", cost)
    assert repository.get_table_cost_estimate("run-table", 2) == cost

    link = TableDrawingFormatLink(format="svg", media_type="image/svg+xml", url="/api/v1/runs/run-table/table-drawings/general.svg?result_revision=2")
    manifest = TableDrawingManifest(run_id="run-table", result_revision=2, program_hash=program_hash, sheets=(TableDrawingManifestSheet(sheet_id="general", kind="general", title="Plano general", page=1, result_revision=2, program_hash=program_hash, status="ready", formats=(link,)),))
    exports = TableDrawingExports(result_revision=2, program_hash=program_hash, artifacts=(TableDrawingArtifactData(sheet_id="general", format="svg", media_type="image/svg+xml", filename="general.svg", content=b"<svg/>") ,))
    repository.save_table_drawings("run-table", manifest, exports)
    assert repository.get_table_drawing_manifest("run-table", 2) == manifest
    content, media_type, filename = repository.get_table_drawing_artifact("run-table", 2, "general", "svg", program_hash)
    assert (content, media_type, filename) == (b"<svg/>", "image/svg+xml", "general.svg")


def test_table_artifact_hash_mismatch_is_rejected(tmp_path, monkeypatch):
    repository = DemoRepository(tmp_path / "table-artifacts.sqlite3")
    result = _completed_table_result()
    monkeypatch.setattr(repository, "get_result", lambda run_id, revision=None: result)
    wrong = TableCostEstimate(result_revision=2, program_hash="b" * 64, catalog_version="v1", scope=TableCostScope(), concepts=(), known_subtotal_eur=0, grand_total_eur=0, total_state="complete")
    try:
        repository.save_table_cost_estimate("run-table", wrong)
    except ValueError as exc:
        assert str(exc) == "table_program_revision_mismatch"
    else:
        raise AssertionError("mismatched program hash was accepted")
