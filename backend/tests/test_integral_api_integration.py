from __future__ import annotations

import json
import io
import sqlite3
from pathlib import Path
import time

import fitz
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.agente.provider import ProviderError, ProviderResponse, ToolCall
from backend.app.main import create_app
from backend.app.operacion.auth import hash_password
from backend.app.ingesta import DwgConversionResult


ROOT = Path(__file__).resolve().parents[2]
DXF_FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


class _GeneralLiveProvider:
    def __init__(self) -> None:
        self.visual_page_count = 0
        self.review_visual_page_count = 0
        self.proposer_visual_metadata = []
        self.reviewer_visual_metadata = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        if tools[0]["name"] == "entregar_revision_autonoma":
            context = json.loads(input_items[0]["content"][0]["text"])
            self.reviewer_visual_metadata.extend(context.get("visual_artifacts", []))
            self.review_visual_page_count += sum(
                item.get("type") == "input_image" for item in input_items[0]["content"]
            )
            source = context["draft"]["components"][0]
            component = {
                **{key: value for key, value in source.items() if key != "premise_ids"},
                "id": f"auto-{source['id']}", "replaces_component_ids": [source["id"]],
                "material": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
                "finish": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
            }
            arguments = {
                "scenario_id": "scenario-autonomous-1",
                "checks": [], "field_reviews": [],
                "unresolved": ["quantity", "material", "finish"], "status": "incomplete",
            }
            return ProviderResponse(
                id="general-review-response-1",
                tool_calls=(ToolCall(call_id="general-review-call-1", name="entregar_revision_autonoma", arguments_json=json.dumps(arguments)),),
                model="test-general-reviewer", input_tokens=120, output_tokens=80,
            )
        context = json.loads(input_items[0]["content"][0]["text"])
        self.proposer_visual_metadata.extend(context.get("visual_pages", []))
        self.visual_page_count += sum(
            item.get("type") == "input_image" for item in input_items[0]["content"]
        )
        dimension = context["dimensions"][0] if context["dimensions"] else None
        view = context["views"][0] if context["views"] else None
        observation = context["observations"][0] if context["observations"] else None
        visual_refs = [item["reference"] for item in context.get("visual_pages", [])]
        arguments = {
            "bindings": ([{"id": "length", "operation": "copy", "operand_refs": [f"dimension:{dimension['id']}"]}] if dimension else []),
            "components": [{
                "id": "panel", "label": "Panel propuesto", "kind": "panel", "role": "unknown",
                "length_binding_id": "length" if dimension else None, "width_binding_id": None, "thickness_binding_id": None,
                "quantity": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
                "premise_ids": ["premise"], "source_view_ids": [view["id"]] if view else [],
                "source_observation_ids": [observation["id"]] if observation else [], "source_contour_ids": [],
                "source_evidence_ids": dimension["evidence_ids"] if dimension else [], "source_dimension_ids": [dimension["id"]] if dimension else [],
                "source_document_refs": visual_refs, "assumptions": ["Rol pendiente de revisión."],
                "unknown_fields": (["width", "thickness", "quantity", "material", "finish", "placement"] if dimension else ["length", "width", "thickness", "quantity", "material", "finish", "placement"]),
            }],
            "premises": [{"id": "premise", "description": "La vista puede corresponder a un panel.", "required": True, "blocking": True}],
            "assumptions": ["Propuesta revisable."],
        }
        return ProviderResponse(
            id="general-response-1",
            tool_calls=(ToolCall(call_id="general-call-1", name="proponer_mueble_general", arguments_json=json.dumps(arguments)),),
            model="test-general-live",
        )


class _CountingAssemblyProvider:
    def __init__(self) -> None:
        self.calls = 0

    def create_response(self, **kwargs):
        self.calls += 1
        raise AssertionError("insufficient reviewed geometry must fail before provider spend")


class _FailingGeneralProvider:
    def create_response(self, **kwargs):
        raise ProviderError(
            "provider_response_incomplete", status_code=200,
            request_id="req-internal", response_id="resp-internal",
            incomplete_reason="max_output_tokens",
        )


class _SemanticRepairProvider(_GeneralLiveProvider):
    def __init__(self) -> None:
        super().__init__()
        self.review_context = None

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        if tools[0]["name"] != "entregar_revision_autonoma":
            return super().create_response(input_items=input_items, tools=tools, previous_response_id=previous_response_id, timeout_s=timeout_s)
        if "content" in input_items[0]:
            context = json.loads(input_items[0]["content"][0]["text"])
            self.review_context = context
            source = context["draft"]["components"][0]
            component = {
                **{key: value for key, value in source.items() if key != "premise_ids"},
                "id": f"critic-{source['id']}", "replaces_component_ids": [source["id"]],
                "material": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
                "finish": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
            }
            visual_ref = context["visual_artifacts"][0]["reference"]
            repair_fields = ("length", "width", "thickness", "quantity")
            arguments = {
                "scenario_id": "scenario-repair-1",
                "checks": [{
                    "id": f"semantic-conflict-{field}",
                    "kind": "visual_consistency", "outcome": "fail",
                    "method": "model_visual",
                    "target_refs": [f"component:{source['id']}.{field}"],
                    "source_refs": [visual_ref],
                    "summary": "La asignación semántica requiere reparación.",
                } for field in repair_fields],
                "field_reviews": [{
                    "target_ref": f"component:{source['id']}.{field}",
                    "status": "rejected",
                    "check_ids": [f"semantic-conflict-{field}"],
                } for field in repair_fields],
                "unresolved": ["repairable:semantic_assignment"],
                "status": "conflict",
            }
            return ProviderResponse(id="critic-response-1", model="test-general-reviewer", tool_calls=(ToolCall(call_id="critic-call-1", name="entregar_revision_autonoma", arguments_json=json.dumps(arguments)),))
        output = json.loads(input_items[0]["output"])
        if output.get("ok") is False:
            raise AssertionError(output)
        if output["status"] == "repair_requested":
            proposal = self.review_context["proposal"]
            components = [dict(item) for item in proposal["components"]]
            original_binding = proposal["bindings"][0]
            repaired_binding = {**original_binding, "id": "repaired-length"}
            components[0]["length_binding_id"] = repaired_binding["id"]
            arguments = {
                "bindings": [repaired_binding], "components": components,
                "premises": proposal["premises"],
                "assumptions": proposal["assumptions"],
            }
            return ProviderResponse(id="repair-response-1", model="test-general-reviewer", tool_calls=(ToolCall(call_id="repair-call-1", name="proponer_mueble_general", arguments_json=json.dumps(arguments)),))
        draft = output["draft"]
        source = draft["components"][0]
        component = {
            **{key: value for key, value in source.items() if key != "premise_ids"},
            "id": f"reviewed-{source['id']}", "replaces_component_ids": [source["id"]],
            "material": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
            "finish": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
        }
        arguments = {
            "scenario_id": "scenario-repair-2",
            "checks": [], "field_reviews": [],
            "unresolved": ["quantity", "material", "finish"], "status": "incomplete",
        }
        return ProviderResponse(id="critic-response-2", model="test-general-reviewer", tool_calls=(ToolCall(call_id="critic-call-2", name="entregar_revision_autonoma", arguments_json=json.dumps(arguments)),))


class _FailingAfterSemanticRepairProvider(_SemanticRepairProvider):
    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        if tools[0]["name"] == "entregar_revision_autonoma" and "output" in input_items[0]:
            output = json.loads(input_items[0]["output"])
            if output.get("status") == "proposal_repaired":
                raise RuntimeError("reviewer unavailable after semantic repair")
        return super().create_response(
            input_items=input_items, tools=tools,
            previous_response_id=previous_response_id, timeout_s=timeout_s,
        )


class _ProvisionalScenarioProvider(_SemanticRepairProvider):
    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        if tools[0]["name"] == "entregar_revision_autonoma" and "output" in input_items[0]:
            output = json.loads(input_items[0]["output"])
            if output.get("status") == "repair_requested":
                proposal = self.review_context["proposal"]
                component = dict(proposal["components"][0])
                quantity_premise = component["premise_ids"][0]
                component.update({
                    "length_binding_id": "scenario-length", "width_binding_id": "scenario-width",
                    "thickness_binding_id": "scenario-thickness",
                    "quantity": {"value": 2, "state": "hypothesis", "dependency_refs": [f"premise:{quantity_premise}"], "evidence_ids": []},
                    "unknown_fields": ["material", "finish"],
                })
                observed_operand_refs = proposal["bindings"][0]["operand_refs"]
                arguments = {
                    "bindings": [
                        {"id": "scenario-length", "operation": "copy", "operand_refs": observed_operand_refs},
                        {"id": "scenario-width", "operation": "copy", "operand_refs": observed_operand_refs},
                        {"id": "scenario-thickness", "operation": "copy", "operand_refs": observed_operand_refs},
                    ],
                    "components": [component],
                    "premises": proposal["premises"],
                    "assumptions": proposal["assumptions"],
                }
                return ProviderResponse(id="scenario-repair", model="test-general-reviewer", tool_calls=(ToolCall(call_id="scenario-repair-call", name="proponer_mueble_general", arguments_json=json.dumps(arguments)),))
            if output.get("status") == "proposal_repaired":
                source = output["draft"]["components"][0]
                component = {
                    **{key: value for key, value in source.items() if key != "premise_ids"},
                    "id": "scenario-reviewed-panel", "replaces_component_ids": [source["id"]],
                    "material": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
                    "finish": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
                }
                visual_ref = self.review_context["visual_artifacts"][0]["reference"]
                checks = [
                    {"id": "quantity-basis", "kind": "quantity_basis", "outcome": "pass", "method": "model_visual", "target_refs": ["component:panel.quantity"], "source_refs": [visual_ref], "summary": "Dos grupos visuales distintos."},
                    {"id": "duplicate-scan", "kind": "duplicate_scan", "outcome": "pass", "method": "model_visual", "target_refs": ["component:panel.quantity"], "source_refs": [visual_ref], "summary": "No se tratan como vistas duplicadas."},
                ]
                field_reviews = [{"target_ref": "component:panel.quantity", "status": "accepted", "check_ids": ["quantity-basis", "duplicate-scan"]}]
                for name in ("length", "width", "thickness"):
                    check_id = f"visual-{name}"
                    checks.append({"id": check_id, "kind": "visual_consistency", "outcome": "pass", "method": "model_visual", "target_refs": [f"component:panel.{name}"], "source_refs": [visual_ref], "summary": "Asignación dimensional coherente con el escenario."})
                    field_reviews.append({"target_ref": f"component:panel.{name}", "status": "accepted", "check_ids": [check_id]})
                arguments = {
                    "scenario_id": "scenario-two-items",
                    "checks": checks, "field_reviews": field_reviews,
                    "unresolved": ["material", "finish"], "status": "incomplete",
                }
                return ProviderResponse(id="scenario-review", model="test-general-reviewer", tool_calls=(ToolCall(call_id="scenario-review-call", name="entregar_revision_autonoma", arguments_json=json.dumps(arguments)),))
        return super().create_response(input_items=input_items, tools=tools, previous_response_id=previous_response_id, timeout_s=timeout_s)


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=100)
    page.draw_rect(fitz.Rect(20, 20, 180, 80))
    page.insert_text((24, 45), "VISTA A")
    payload = document.tobytes()
    document.close()
    return payload


def _raster_pdf_bytes() -> bytes:
    image = Image.new("RGB", (80, 40), "white")
    image_stream = io.BytesIO()
    image.save(image_stream, format="PNG")
    document = fitz.open()
    page = document.new_page(width=200, height=100)
    page.insert_image(fitz.Rect(20, 20, 180, 80), stream=image_stream.getvalue())
    payload = document.tobytes()
    document.close()
    return payload


def test_config_advertises_integral_capabilities_without_exposing_evaluation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none"))

    response = client.get("/api/v1/config")

    assert response.status_code == 200
    capabilities = response.json()["data"]["capabilities"]
    assert capabilities["documents"]["formats"] == ["dxf", "dwg", "pdf"]
    assert capabilities["documents"]["preserves_original"] is True
    assert capabilities["documents"]["normalized_dxf_formats"] == ["dxf", "dwg"]
    assert capabilities["general_furniture"]["available"] is True
    assert capabilities["general_furniture"]["autonomous_review"]["default_for_model_generated_live"] is True
    assert capabilities["general_furniture"]["autonomous_review"]["human_required"] is False
    assert capabilities["general_furniture"]["autonomous_review"]["max_visual_artifacts"] == 4
    assert capabilities["general_furniture"]["autonomous_review"]["limits"] == {
        "max_model_calls": 5, "max_validation_repairs": 2, "job_timeout_s": 300.0,
    }
    assert capabilities["history"]["available"] is True
    assert capabilities["evaluation"]["available"] is False


def test_dxf_upload_preserves_legacy_flow_and_exposes_source_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none"))

    response = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["source"]["filename"] == "cabinet.dxf"
    assert payload["source"]["format"] == "dxf"
    assert payload["ingestion"]["state"] == "ready"
    assert payload["artifacts"]["original"]["url"].endswith("/original")
    assert payload["artifacts"]["normalized_dxf"]["url"].endswith("/normalized.dxf")
    assert client.get(payload["artifacts"]["original"]["url"]).content == DXF_FIXTURE.read_bytes()
    assert client.get(payload["artifacts"]["normalized_dxf"]["url"]).content == DXF_FIXTURE.read_bytes()

    created = client.post(
        "/api/v1/runs",
        json={"document_id": payload["document_id"], "mode": "geometry_only"},
    )
    assert created.status_code == 201
    legacy_run_id = created.json()["data"]["run"]["id"]
    wrong_pipeline = client.post(
        f"/api/v1/runs/{legacy_run_id}/general/proposals",
        json={"mode": "live", "proposal": None, "base_proposal_revision": 0},
    )
    assert wrong_pipeline.status_code == 404

    restarted = TestClient(create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none"))
    metadata = restarted.get(f"/api/v1/documents/{payload['document_id']}")
    assert metadata.status_code == 200
    assert metadata.json()["data"]["source"]["sha256"] == payload["source"]["sha256"]


def test_pdf_upload_selects_scaled_vector_page_as_immutable_child_document(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none"))
    source = _pdf_bytes()

    response = client.post(
        "/api/v1/documents",
        files={"file": ("drawing.pdf", source, "application/pdf")},
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["ingestion"]["state"] == "needs_review"
    assert payload["ingestion"]["capabilities"]["geometry_analysis"] is False
    assert payload["source"]["unit"] == "unknown"
    assert payload["artifacts"]["normalized_dxf"] is None
    assert payload["artifacts"]["pages"][0]["normalized_dxf"] is not None
    assert client.get(payload["artifacts"]["original"]["url"]).content == source
    preview = client.get(payload["artifacts"]["preview"]["url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"

    selected = client.post(
        f"/api/v1/documents/{payload['document_id']}/pdf-pages/1/normalize",
        json={"mm_per_pdf_point": 0.5, "confirmed_by": "Técnica", "reason": "Escala comprobada contra cota visible"},
    )
    assert selected.status_code == 200
    child = selected.json()["data"]
    assert child["document_id"] != payload["document_id"]
    assert child["source"]["parent_document_id"] == payload["document_id"]
    assert child["source"]["unit"] == "mm"
    assert child["ingestion"]["scale_provenance"]["confirmed_by"] == "Técnica"
    assert child["audit"]["selection_reason"] == "Escala comprobada contra cota visible"
    assert client.get(child["artifacts"]["normalized_dxf"]["url"]).status_code == 200
    assert client.get(child["artifacts"]["original"]["url"]).content == source
    parent_after = client.get(f"/api/v1/documents/{payload['document_id']}").json()["data"]
    assert parent_after["artifacts"]["normalized_dxf"] is None


def test_pdf_quota_counts_original_preview_and_page_artifacts(tmp_path: Path, monkeypatch) -> None:
    import backend.app.main as main_module

    source = _pdf_bytes()
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setattr(main_module, "MAX_UPLOAD_BYTES", len(source) + 1)
    monkeypatch.setenv("VEXPLORER_MAX_STORAGE_BYTES", str(len(source) + 1))
    data = tmp_path / "data"
    client = TestClient(create_app(data_dir=data, frontend_dir=tmp_path / "none"))

    response = client.post(
        "/api/v1/documents",
        files={"file": ("drawing.pdf", source, "application/pdf")},
    )

    assert response.status_code == 507
    assert response.json()["error"]["code"] == "storage_quota_exceeded"
    assert list((data / "documents").iterdir()) == []


def test_dwg_upload_reports_missing_converter_without_persisting_source(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setenv("VEXPLORER_DWG_CONVERTER", "oda")
    monkeypatch.setenv("VEXPLORER_ODA_EXECUTABLE", str(tmp_path / "missing-oda.exe"))
    data = tmp_path / "data"
    client = TestClient(create_app(data_dir=data, frontend_dir=tmp_path / "none"))

    response = client.post(
        "/api/v1/documents",
        files={"file": ("drawing.dwg", b"not-a-real-dwg", "application/acad")},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dwg_converter_unavailable"
    assert list((data / "documents").iterdir()) == []


def test_dwg_upload_accepts_absolute_converter_output_with_relative_data_dir(
    tmp_path: Path, monkeypatch
) -> None:
    import backend.app.ingesta as ingestion

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VEXPLORER_ENV", "local")

    def convert(source: Path, output_dir: Path):
        output = output_dir.resolve() / "source.dxf"
        output.write_bytes(DXF_FIXTURE.read_bytes())
        return DwgConversionResult(
            source_path=source.resolve(), source_name=source.name,
            source_media_type="application/acad", source_size_bytes=source.stat().st_size,
            source_sha256="a" * 64, dxf_path=output, dxf_sha256="b" * 64,
            converter="test_converter", converter_executable=(tmp_path / "converter.exe"),
            warnings=("original_source_preserved",),
        )

    monkeypatch.setattr(ingestion, "convert_dwg_to_dxf", convert)
    client = TestClient(create_app(data_dir=Path("relative-data"), frontend_dir=tmp_path / "none"))

    response = client.post(
        "/api/v1/documents",
        files={"file": ("drawing.dwg", b"dwg-source", "application/acad")},
    )

    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    assert client.get(payload["artifacts"]["original"]["url"]).content == b"dwg-source"
    assert client.get(payload["artifacts"]["normalized_dxf"]["url"]).status_code == 200


def test_general_live_failure_does_not_leave_a_run_ghost(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    data = tmp_path / "data"
    client = TestClient(create_app(
        data_dir=data, frontend_dir=tmp_path / "none", agent_provider=_FailingGeneralProvider()
    ))
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
    )

    response = client.post(
        "/api/v1/runs",
        json={
            "document_id": upload.json()["data"]["document_id"], "mode": "live",
            "input_kind": "general_furniture", "proposal_mode": "model_generated",
        },
    )

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "general_live_provider_failed"
    assert error["reason_code"] == "provider_response_incomplete"
    assert error["provider_status_code"] == 200
    assert error["provider_incomplete_reason"] == "max_output_tokens"
    assert "req-internal" not in response.text
    assert "resp-internal" not in response.text
    with sqlite3.connect(data / "vexplorer.sqlite3") as database:
        assert database.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_production_upload_records_authenticated_actor_in_document_audit(
    tmp_path: Path, monkeypatch
) -> None:
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"alice": hash_password("correct horse")}), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))

    response = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
        auth=("alice", "correct horse"),
        headers={"Origin": "https://vexplorer.example"},
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["audit"]["uploaded_by"] == "alice"
    stored = client.get(
        f"/api/v1/documents/{payload['document_id']}", auth=("alice", "correct horse")
    )
    assert stored.json()["data"]["audit"]["uploaded_by"] == "alice"


def test_history_router_is_authenticated_mounted_before_static_and_uses_server_actor(
    tmp_path: Path, monkeypatch
) -> None:
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"alice": hash_password("correct horse")}), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    monkeypatch.setenv("VEXPLORER_ROOT_PATH", "/vexplorer")
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=ROOT / "frontend"))
    record = {
        "record_id": "real-001", "project_id": "project-001", "revision": "r1",
        "family": "cabinet", "quantity": 1, "currency": "EUR", "actual_cost": 120,
        "cost_basis": "actual", "manufacturing_hours": 4, "origin": "actual",
            "included_scope": ["labor"], "cost_scope": ["labor"], "hours_scope": ["labor"],
        "provenance": {"source": "ERP WO-1", "source_date": "2026-11-01", "imported_by": "forged-client"},
        "concepts": [{"concept_id": "assembly", "kind": "labor", "driver": "item", "cost": 120, "hours": 4}],
    }

    denied = client.get("/api/v1/history")
    imported = client.post(
        "/api/v1/history/import/json", json={"records": [record]},
        auth=("alice", "correct horse"), headers={"Origin": "https://vexplorer.example"},
    )
    listed = client.get("/api/v1/history", auth=("alice", "correct horse"))

    assert denied.status_code == 401
    assert imported.status_code == 200
    assert listed.status_code == 200
    assert listed.headers["content-type"].startswith("application/json")
    assert listed.json()["data"]["items"][0]["provenance"]["imported_by"] == "alice"
    assert (tmp_path / "data" / "history.sqlite3").is_file()


def test_json_body_limit_does_not_trust_content_length(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none"))

    response = client.post(
        "/api/v1/history/import/json",
        content=b'{"records":[' + b" " * (5 * 1024 * 1024) + b"]}",
        headers={"Content-Type": "application/json", "Content-Length": "1"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "history_import_too_large"


def test_general_autonomous_semantic_repair_preserves_p1_and_reviews_p2(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    provider = _SemanticRepairProvider()
    app = create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none", agent_provider=provider)
    client = TestClient(app)
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
    )
    document_id = upload.json()["data"]["document_id"]

    created = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "live", "input_kind": "general_furniture", "proposal_mode": "model_generated"},
    )

    assert created.status_code == 201, created.text
    run_id = created.json()["data"]["run"]["id"]
    original = app.state.general_furniture_repository.get(run_id, proposal_revision=1)
    repaired = app.state.general_furniture_repository.get(run_id, proposal_revision=2)
    assert original is not None and original.review is None
    assert repaired is not None and repaired.review is not None
    assert repaired.review.proposal_revision == 2
    assert repaired.review.reviewer_kind == "machine"
    events = client.get(f"/api/v1/runs/{run_id}/events").text
    assert "event: general_auto_semantic_repair" in events
    assert "event: general_auto_semantic_repair_committed" in events
    direct_retry = client.post(
        f"/api/v1/runs/{run_id}/general/auto-review",
        json={"base_proposal_revision": 2, "base_review_revision": 1},
    )
    assert direct_retry.status_code == 409
    assert direct_retry.json()["detail"] == "general_auto_review_requires_durable_job"


def test_general_assembly_phase_persists_failure_and_retry_uses_durable_job(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    assembly_provider = _CountingAssemblyProvider()
    app = create_app(
        data_dir=tmp_path,
        frontend_dir=tmp_path / "none",
        agent_provider=_GeneralLiveProvider(),
        general_assembly_provider=assembly_provider,
    )
    client = TestClient(app)
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
    ).json()["data"]
    created = client.post(
        "/api/v1/runs",
        json={
            "document_id": uploaded["document_id"],
            "mode": "live",
            "input_kind": "general_furniture",
            "proposal_mode": "model_generated",
        },
    )

    assert created.status_code == 201, created.text
    run_id = created.json()["data"]["run"]["id"]
    record = client.get(f"/api/v1/runs/{run_id}/general").json()["data"]
    query = (
        f"proposal_revision={record['proposal_revision']}"
        f"&review_revision={record['review_revision']}"
    )
    first = client.get(f"/api/v1/runs/{run_id}/general/assembly?{query}")
    again = client.get(f"/api/v1/runs/{run_id}/general/assembly?{query}")

    assert first.status_code == 200
    assert first.json()["current"]["report"]["status"] == "incomplete"
    assert first.json()["current"]["report"]["scene"] is None
    assert first.json()["current"]["report"]["issues"][0]["code"].startswith("assembly_")
    assert first.json()["current"]["report"]["issues"][0]["code"] != "assembly_runtime_failed"
    assert again.json()["assembly_revision"] == 1
    assert assembly_provider.calls == 0

    submitted = client.post(
        f"/api/v1/runs/{run_id}/general/assembly/retry",
        json={
            "base_proposal_revision": record["proposal_revision"],
            "base_review_revision": record["review_revision"],
        },
    )
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["data"]["id"]
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["state"] in {"succeeded", "failed", "interrupted"}:
            break
        time.sleep(0.01)
    latest = client.get(f"/api/v1/runs/{run_id}/general/assembly?{query}")
    assert job["state"] == "failed"
    assert latest.status_code == 200
    assert latest.json()["assembly_revision"] == 2


def test_failed_c2_job_keeps_run_p1_p2_and_no_successful_review(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    app = create_app(
        data_dir=tmp_path, frontend_dir=tmp_path / "none",
        agent_provider=_FailingAfterSemanticRepairProvider(),
    )
    client = TestClient(app)
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
    ).json()["data"]
    submitted = client.post(
        "/api/v1/jobs",
        json={"document_id": uploaded["document_id"], "mode": "live", "input_kind": "general_furniture", "proposal_mode": "model_generated"},
    )
    job_id = submitted.json()["data"]["id"]
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["state"] in {"succeeded", "failed", "interrupted"}:
            break
        time.sleep(0.02)

    assert job["state"] == "failed"
    assert job["run_id"] is not None
    assert job["error"]["code"] == "general_auto_review_failed"
    assert job["error"]["run_id"] == job["run_id"]
    original = app.state.general_furniture_repository.get(job["run_id"], proposal_revision=1)
    repaired = app.state.general_furniture_repository.get(job["run_id"], proposal_revision=2)
    assert original is not None and original.review is None
    assert repaired is not None and repaired.review is None
    events = client.get(f"/api/v1/runs/{job['run_id']}/events").text
    assert "event: general_auto_semantic_repair_committed" in events
    assert "event: general_auto_review_failed" in events


def test_machine_provisional_bom_reaches_historical_scenario_with_exact_revisions(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    app = create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none", agent_provider=_ProvisionalScenarioProvider())
    client = TestClient(app)
    reference = {
        "record_id": "reference-actual-1", "project_id": "reference-project", "revision": "r1",
        "family": "cabinet", "material": "plywood", "finish": "varnish",
        "length_mm": 1000, "area_mm2": 1_000_000, "volume_mm3": 18_000_000,
        "quantity": 1, "currency": "EUR", "actual_cost": 500, "cost_basis": "actual",
        "manufacturing_hours": 8, "origin": "actual",
        "included_scope": ["material", "labor", "indirect"],
        "cost_scope": ["material", "labor", "indirect"], "hours_scope": ["labor"],
        "provenance": {"source": "ERP reference", "source_date": "2026-10-01"},
        "concepts": [
            {"concept_id": "material", "kind": "material", "driver": "area", "cost": 300},
            {"concept_id": "labor", "kind": "labor", "driver": "item", "cost": 160, "hours": 8},
            {"concept_id": "indirect", "kind": "indirect", "driver": "item", "cost": 40},
        ],
    }
    imported = client.post("/api/v1/history/import/json", json={"records": [reference]})
    assert imported.status_code == 200, imported.text
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
    ).json()["data"]
    created = client.post(
        "/api/v1/runs",
        json={"document_id": uploaded["document_id"], "mode": "live", "input_kind": "general_furniture", "proposal_mode": "model_generated"},
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["data"]["run"]["id"]
    record = client.get(f"/api/v1/runs/{run_id}/general").json()["data"]

    response = client.post("/api/v1/history/scenarios", json={
        "run_id": run_id, "proposal_revision": record["proposal_revision"],
        "review_revision": record["review_revision"], "limit": 5, "retrieval_method": "attribute",
    })

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["run_id"] == run_id
    assert data["proposal_revision"] == 2 and data["review_revision"] == 1
    assert data["status"] == "provisional"
    assert len(data["scenarios"]) == 1
    scenario = data["scenarios"][0]
    assert scenario["cost_subtotal"] is not None
    assert scenario["manufacturing_hours"] is not None
    assert scenario["result_provenance"]
    assert scenario["scaling_basis"]["scenario_occurrence_ids"]


def test_production_job_integrates_general_review_derived_and_history_persistently(
    tmp_path: Path, monkeypatch
) -> None:
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"alice": hash_password("correct horse")}), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    monkeypatch.setenv("VEXPLORER_ROOT_PATH", "/vexplorer")
    data = tmp_path / "data"
    auth = ("alice", "correct horse")
    mutation_headers = {"Origin": "https://vexplorer.example", "Idempotency-Key": "general-job-1"}
    provider = _GeneralLiveProvider()
    client = TestClient(create_app(
        data_dir=data, frontend_dir=ROOT / "frontend", agent_provider=provider
    ))
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
        auth=auth, headers={"Origin": "https://vexplorer.example"},
    )
    document_id = upload.json()["data"]["document_id"]

    submitted = client.post(
        "/api/v1/jobs",
        json={"document_id": document_id, "mode": "live", "input_kind": "general_furniture", "proposal_mode": "model_generated"},
        auth=auth, headers=mutation_headers,
    )
    assert submitted.status_code == 202
    job_id = submitted.json()["data"]["id"]
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}", auth=auth).json()["data"]
        if job["state"] in {"succeeded", "failed", "interrupted"}:
            break
        time.sleep(0.02)
    assert job["state"] == "succeeded", job
    run_id = job["run_id"]
    event_history = client.get(f"/api/v1/runs/{run_id}/events", auth=auth).text
    assert "event: general_tool_completed" in event_history
    assert "event: general_proposal_committed" in event_history
    assert "event: general_auto_review_started" in event_history
    assert "event: general_auto_review_tool_completed" in event_history
    assert "event: general_auto_review_completed" in event_history
    assert "test-general-reviewer" in event_history
    assert "test-general-live" in event_history
    assert "arguments_json" not in event_history
    assert provider.visual_page_count == 3
    assert provider.review_visual_page_count == 3
    assert all(item["source_view_ids"] for item in provider.proposer_visual_metadata)
    assert all(item["crop_bounds_source"] for item in provider.proposer_visual_metadata)
    assert all(item["source_view_ids"] for item in provider.reviewer_visual_metadata)
    assert provider.proposer_visual_metadata[0]["sha256"] in event_history

    raster_upload = client.post(
        "/api/v1/documents",
        files={"file": ("scan.pdf", _raster_pdf_bytes(), "application/pdf")},
        auth=auth, headers={"Origin": "https://vexplorer.example"},
    )
    raster_parent = raster_upload.json()["data"]
    raster_child_response = client.post(
        f"/api/v1/documents/{raster_parent['document_id']}/pdf-pages/1/normalize",
        json={"confirmed_by": "forged-client", "reason": "Página raster elegida para revisión visual."},
        auth=auth, headers={"Origin": "https://vexplorer.example", "Idempotency-Key": "raster-page-1"},
    )
    assert raster_child_response.status_code == 200
    raster_child = raster_child_response.json()["data"]
    assert raster_child["artifacts"]["normalized_dxf"] is None
    raster_job_response = client.post(
        "/api/v1/jobs",
        json={"document_id": raster_child["document_id"], "mode": "live", "input_kind": "general_furniture", "proposal_mode": "model_generated"},
        auth=auth, headers={"Origin": "https://vexplorer.example", "Idempotency-Key": "raster-general-job-1"},
    )
    raster_job_id = raster_job_response.json()["data"]["id"]
    for _ in range(100):
        raster_job = client.get(f"/api/v1/jobs/{raster_job_id}", auth=auth).json()["data"]
        if raster_job["state"] in {"succeeded", "failed", "interrupted"}:
            break
        time.sleep(0.02)
    assert raster_job["state"] == "succeeded", raster_job
    assert client.get(f"/api/v1/runs/{raster_job['run_id']}/general", auth=auth).status_code == 200
    assert provider.visual_page_count == 4
    assert provider.review_visual_page_count == 4

    general = client.get(f"/api/v1/runs/{run_id}/general", auth=auth)
    assert general.status_code == 200
    record = general.json()["data"]
    assert record["review"]["reviewer_kind"] == "machine"
    assert record["review"]["reviewer_name"] == "autonomous-reviewer"
    assert record["review"]["auto_review_status"] == "incomplete"
    assert record["review"]["machine_provenance"]["model"] == "test-general-reviewer"
    proposal_revision = record["proposal_revision"]
    provisional = client.post(
        "/api/v1/history/scenarios",
        json={"run_id": run_id, "proposal_revision": proposal_revision, "review_revision": 1, "limit": 3, "retrieval_method": "attribute"},
        auth=auth, headers={"Origin": "https://vexplorer.example", "Idempotency-Key": "general-scenario-1"},
    )
    assert provisional.status_code == 200, provisional.text
    assert provisional.json()["data"]["run_id"] == run_id
    assert provisional.json()["data"]["status"] == "not_estimable"
    stale_snapshot = client.post(
        "/api/v1/history/scenarios",
        json={"run_id": run_id, "proposal_revision": proposal_revision, "review_revision": 99},
        auth=auth, headers={"Origin": "https://vexplorer.example", "Idempotency-Key": "general-scenario-stale"},
    )
    assert stale_snapshot.status_code == 404
    draft = record["review"]["components"][0]
    reviewed_component = {
        "id": "panel-reviewed", "label": draft["label"], "kind": draft["kind"], "role": "unknown",
        "length": draft["length"], "width": draft["width"], "thickness": draft["thickness"],
        "quantity": draft["quantity"],
        "material": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
        "finish": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
        "replaces_component_ids": [draft["id"]],
        "source_view_ids": draft["source_view_ids"], "source_observation_ids": draft["source_observation_ids"],
        "source_contour_ids": draft["source_contour_ids"], "source_evidence_ids": draft["source_evidence_ids"],
        "source_dimension_ids": draft["source_dimension_ids"], "source_document_refs": draft["source_document_refs"],
        "assumptions": draft["assumptions"], "unknown_fields": draft["unknown_fields"],
    }
    reviewed = client.post(
        f"/api/v1/runs/{run_id}/general/reviews",
        json={
            "base_proposal_revision": proposal_revision, "base_review_revision": 1,
            "reviewer_name": "forged-client", "reason": "Mantiene incógnitas para revisión técnica.",
            "operations": [{"kind": "replace", "source_component_ids": [draft["id"]], "result_component_ids": ["panel-reviewed"], "reason": "Registra revisión sin inventar medidas."}],
            "components": [reviewed_component],
        },
        auth=auth, headers={"Origin": "https://vexplorer.example", "Idempotency-Key": "general-review-1"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["review"]["reviewer_name"] == "alice"
    derived = client.get(
        f"/api/v1/runs/{run_id}/general/derived?proposal_revision={proposal_revision}&review_revision=2", auth=auth
    )
    assert derived.status_code == 200
    assert derived.json()["data"]["package"]["status"] == "incomplete"
    assert derived.json()["data"]["historical_target"]["basis_revision"] == f"proposal:{proposal_revision};review:2"
    artifact_id = derived.json()["data"]["package"]["artifacts"][0]["id"]
    artifact = client.get(
        f"/api/v1/runs/{run_id}/general/artifacts/{artifact_id}?proposal_revision={proposal_revision}&review_revision=2",
        auth=auth,
    )
    assert artifact.status_code == 200

    historical = {
        "record_id": "actual-1", "project_id": "old-project", "revision": "r1", "family": "cabinet",
        "quantity": 1, "currency": "EUR", "actual_cost": 100, "cost_basis": "actual",
        "manufacturing_hours": 2, "origin": "actual",
            "included_scope": ["labor"], "cost_scope": ["labor"], "hours_scope": ["labor"],
        "provenance": {"source": "ERP WO-1", "source_date": "2026-10-01"},
        "concepts": [{"concept_id": "assembly", "kind": "labor", "driver": "item", "cost": 100, "hours": 2}],
    }
    imported = client.post(
        "/api/v1/history/import/json", json={"records": [historical]}, auth=auth,
        headers={"Origin": "https://vexplorer.example", "Idempotency-Key": "history-1"},
    )
    assert imported.status_code == 200
    target = {
        "family": "cabinet", "quantity": 1, "currency": "EUR",
        "basis_revision": "proposal:1;review:1",
        "required_cost_scope": ["labor"], "required_hours_scope": ["labor"],
    }
    estimated = client.post(
        "/api/v1/history/estimate", json={"target": target, "comparable_ids": ["actual-1"]},
        auth=auth, headers={"Origin": "https://vexplorer.example", "Idempotency-Key": "estimate-1"},
    )
    assert estimated.status_code == 200
    assert estimated.json()["data"]["cost_subtotal"] == 100
    assert estimated.json()["data"]["manufacturing_hours"] == 2

    restarted = TestClient(create_app(
        data_dir=data, frontend_dir=ROOT / "frontend", agent_provider=_GeneralLiveProvider()
    ))
    persisted = restarted.get(f"/api/v1/runs/{run_id}/general", auth=auth)
    assert persisted.status_code == 200
    assert persisted.json()["data"]["review"]["reviewer_name"] == "alice"
