"""Audit the mounted-table workflow through real HTTP using public DXF only."""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ezdxf
import httpx


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "planos_demo"
DEFAULT_OUTPUT = ROOT / "docs" / "auditoria" / "2026-11-14" / "table-api.json"


class AuditStop(RuntimeError):
    pass


class Audit:
    def __init__(self, target: str) -> None:
        self.started = time.monotonic()
        self.data: dict[str, Any] = {
            "audit_schema": "vexplorer-table-api-audit-1",
            "generated_at": datetime.now(UTC).isoformat(),
            "target": target,
            "policy": {
                "transport": "real_http",
                "run_mode": "geometry_only",
                "proposal_mode": "catalog_baseline",
                "provider_calls": False,
                "public_fixtures_only": True,
                "evaluator_oracle_reads": False,
            },
            "checks": [],
            "findings": [],
            "resources": {"documents": {}, "runs": {}},
            "capabilities": {},
        }

    def check(self, name: str, ok: bool, expected: Any, observed: Any) -> bool:
        item = {
            "name": name,
            "status": "pass" if ok else "fail",
            "expected": expected,
            "observed": observed,
        }
        self.data["checks"].append(item)
        if not ok:
            self.data["findings"].append(
                {"severity": "important", "check": name, "expected": expected, "observed": observed}
            )
        return ok

    def require(self, name: str, ok: bool, expected: Any, observed: Any) -> None:
        if not self.check(name, ok, expected, observed):
            raise AuditStop(name)

    def capability(self, name: str, state: str, evidence: str) -> None:
        self.data["capabilities"][name] = {"state": state, "evidence": evidence}

    def finish(self) -> dict[str, Any]:
        counts = Counter(item["status"] for item in self.data["checks"])
        self.data["summary"] = {
            "passed": counts["pass"],
            "failed": counts["fail"],
            "duration_ms": round((time.monotonic() - self.started) * 1000),
            "result": "pass" if counts["fail"] == 0 else "findings",
        }
        return self.data


def body(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def error_code(response: httpx.Response) -> str | None:
    return body(response).get("error", {}).get("code")


def upload(client: httpx.Client, audit: Audit, key: str, filename: str) -> str:
    with (FIXTURES / filename).open("rb") as stream:
        response = client.post(
            "/api/v1/documents", files={"file": ("source.dxf", stream, "application/dxf")}
        )
    data = body(response).get("data", {})
    audit.require(
        f"upload.{key}",
        response.status_code == 201 and bool(data.get("document_id")),
        {"status": 201, "document_id": "present"},
        {"status": response.status_code, "code": error_code(response)},
    )
    audit.data["resources"]["documents"][key] = data["document_id"]
    return data["document_id"]


def start(
    client: httpx.Client,
    audit: Audit,
    key: str,
    document_id: str,
    template: str = "side_supports_v1",
) -> tuple[str, dict[str, Any]]:
    response = client.post(
        "/api/v1/runs",
        json={
            "document_id": document_id,
            "mode": "geometry_only",
            "input_kind": "mounted_orthographic_views",
            "table_profile": "rectangular_table_v1",
            "proposal_mode": "catalog_baseline",
            "table_template_id": template,
        },
    )
    data = body(response).get("data", {})
    audit.require(
        f"run.{key}",
        response.status_code == 201
        and data.get("run", {}).get("input_kind") == "mounted_orthographic_views"
        and data.get("result", {}).get("input_semantics") == "mounted_orthographic_views",
        {"status": 201, "input_kind": "mounted_orthographic_views"},
        {"status": response.status_code, "code": error_code(response)},
    )
    run_id = data["run"]["id"]
    audit.data["resources"]["runs"][key] = run_id
    return run_id, data["result"]


def table(client: httpx.Client, audit: Audit, run_id: str, revision: int, key: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/runs/{run_id}/table", params={"result_revision": revision})
    data = body(response).get("data", {})
    audit.require(
        f"table.{key}.r{revision}",
        response.status_code == 200
        and data.get("table_analysis", {}).get("schema_version") == "0.5.0",
        {"status": 200, "schema_version": "0.5.0"},
        {"status": response.status_code, "code": error_code(response)},
    )
    return data


def decisions(program: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "target_kind": "program",
            "target_id": program["id"],
            "action": "accept",
            "reason": "Explicit audit selection",
        },
        *(
            {
                "target_kind": "component",
                "target_id": item["id"],
                "action": "accept",
                "reason": "Explicit audit component acceptance",
            }
            for item in program["components"]
        ),
        *(
            {
                "target_kind": "premise",
                "target_id": item["id"],
                "action": "accept",
                "reason": "Explicit audit premise acceptance",
            }
            for item in program["premises"]
        ),
    ]


def review(
    client: httpx.Client,
    audit: Audit,
    run_id: str,
    program: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "HTTP table audit",
            "table_program_id": program["id"],
            "table_decisions": decisions(program),
            "notes": "Versioned review; not manufacturing certification",
        },
    )
    data = body(response).get("data", {})
    audit.require(
        f"review.{key}",
        response.status_code == 201 and data.get("result_revision") == 2,
        {"status": 201, "revision": 2},
        {"status": response.status_code, "code": error_code(response)},
    )
    return data


def audit_complete(client: httpx.Client, audit: Audit) -> None:
    document_id = upload(client, audit, "complete", "mesa_demo_001.dxf")
    run_id, initial = start(client, audit, "complete", document_id)
    snapshot = table(client, audit, run_id, 1, "complete")
    measures = {
        item["semantic"]: item
        for item in snapshot["table_analysis"]["measures"]
        if item["semantic"] in {"overall_width", "overall_height", "overall_depth"}
    }
    observed = {key: [item["state"], item["value_mm"]] for key, item in measures.items()}
    audit.check(
        "source.overall_dimensions_are_observed_with_provenance",
        observed
        == {
            "overall_width": ["observed", 1200.0],
            "overall_height": ["observed", 750.0],
            "overall_depth": ["observed", 700.0],
        }
        and all(item["measurement_ids"] and item["view_ids"] and item["evidence_ids"] for item in measures.values()),
        {"width": 1200.0, "height": 750.0, "depth": 700.0, "provenance": True},
        {"measures": observed, "provenance": all(bool(item["evidence_ids"]) for item in measures.values())},
    )
    program = snapshot["table_programs"][0]
    bounded = all(
        set(binding) == {"id", "operation", "operand_refs"}
        and all(set(ref) == {"ref_type", "ref_id"} for ref in binding["operand_refs"])
        for binding in program["bindings"]
    )
    audit.check(
        "program.catalog_baseline_is_bounded_and_unreviewed",
        initial.get("state") == "needs_review"
        and program.get("proposal_origin") == "catalog_baseline"
        and program.get("table_template_id") == "side_supports_v1"
        and bounded
        and len(snapshot["evaluated_table_program"]["occurrences"]) == 3,
        {"state": "needs_review", "origin": "catalog_baseline", "bounded": True, "occurrences": 3},
        {
            "state": initial.get("state"),
            "origin": program.get("proposal_origin"),
            "bounded": bounded,
            "occurrences": len(snapshot["evaluated_table_program"]["occurrences"]),
        },
    )
    reviewed = review(client, audit, run_id, program, "complete")
    evaluated = reviewed.get("evaluated_table_program", {})
    audit.check(
        "review.completed_recalculates_program",
        reviewed.get("state") == "completed"
        and evaluated.get("state") == "completed"
        and evaluated.get("overall_dimensions")
        == {"width_mm": 1200.0, "depth_mm": 700.0, "height_mm": 750.0}
        and len(evaluated.get("occurrences", [])) == 3,
        {"state": "completed", "dimensions": [1200.0, 700.0, 750.0], "occurrences": 3},
        {
            "result_state": reviewed.get("state"),
            "program_state": evaluated.get("state"),
            "dimensions": evaluated.get("overall_dimensions"),
            "occurrences": len(evaluated.get("occurrences", [])),
        },
    )
    scene_response = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2})
    scene = body(scene_response).get("data", {})
    audit.check(
        "scene.reviewed_three_occurrences",
        scene_response.status_code == 200 and scene.get("state") == "ready" and len(scene.get("objects", [])) == 3,
        {"status": 200, "state": "ready", "objects": 3},
        {"status": scene_response.status_code, "state": scene.get("state"), "objects": len(scene.get("objects", []))},
    )
    drawings_response = client.post(
        f"/api/v1/runs/{run_id}/table-drawings", json={"result_revision": 2}
    )
    drawings = body(drawings_response).get("data", {})
    artifact_ok = drawings_response.status_code == 201
    dxf_units: list[int] = []
    artifact_count = 0
    for sheet in drawings.get("sheets", []):
        for link in sheet.get("formats", []):
            artifact = client.get(link["url"])
            artifact_count += 1
            artifact_ok = artifact_ok and artifact.status_code == 200
            artifact_ok = artifact_ok and artifact.headers.get("content-type", "").split(";")[0] == link["media_type"]
            if link["format"] == "svg":
                artifact_ok = artifact_ok and "<svg" in artifact.text and "data-state=" in artifact.text
            else:
                derived = ezdxf.read(io.StringIO(artifact.text))
                dxf_units.append(derived.units)
                artifact_ok = artifact_ok and len(derived.modelspace()) > 0
    audit.check(
        "drawings.general_components_cut_sheet_roundtrip",
        artifact_ok
        and {item["kind"] for item in drawings.get("sheets", [])} == {"general", "component", "cut_sheet"}
        and all(item["status"] == "ready" for item in drawings.get("sheets", []))
        and artifact_count == 8
        and dxf_units == [4, 4, 4, 4],
        {"sheet_kinds": ["general", "component", "cut_sheet"], "artifacts": 8, "dxf_units": [4, 4, 4, 4]},
        {
            "status": drawings_response.status_code,
            "sheet_kinds": sorted({item["kind"] for item in drawings.get("sheets", [])}),
            "artifacts": artifact_count,
            "dxf_units": dxf_units,
        },
    )
    cost_response = client.post(
        f"/api/v1/runs/{run_id}/table-costs",
        json={
            "result_revision": 2,
            "scope": {
                "material_tariff_id": "demo_board_area_v1",
                "edge_scope": "none",
                "operation_tariff_ids": [],
            },
        },
    )
    cost = body(cost_response).get("data", {})
    concepts = {item["id"]: item for item in cost.get("concepts", [])}
    audit.check(
        "cost.per_component_area_and_single_setup",
        cost_response.status_code == 201
        and concepts.get("fixed:preparation", {}).get("amount_eur") == 25.0
        and concepts.get("material:component-tabletop", {}).get("quantity") == 0.84
        and concepts.get("material:component-tabletop", {}).get("amount_eur") == 35.28
        and concepts.get("material:component-side-support", {}).get("quantity") == 1.008
        and concepts.get("material:component-side-support", {}).get("amount_eur") == 42.34
        and len(concepts.get("material:component-side-support", {}).get("occurrence_ids", [])) == 2
        and cost.get("known_subtotal_eur") == 102.62
        and cost.get("total_state") == "partial"
        and cost.get("grand_total_eur") is None,
        {"setup": 25.0, "top_m2": 0.84, "supports_m2": 1.008, "known_subtotal": 102.62, "total_state": "partial"},
        {
            "status": cost_response.status_code,
            "setup": concepts.get("fixed:preparation", {}).get("amount_eur"),
            "top_m2": concepts.get("material:component-tabletop", {}).get("quantity"),
            "supports_m2": concepts.get("material:component-side-support", {}).get("quantity"),
            "known_subtotal": cost.get("known_subtotal_eur"),
            "total_state": cost.get("total_state"),
        },
    )
    exported = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "json"})
    export_data = body(exported)
    audit.check(
        "export.revision_bound_bundle",
        exported.status_code == 200
        and export_data.get("schema_version") == "0.5.0"
        and export_data.get("table_drawings") == drawings
        and export_data.get("estimate") == cost
        and export_data.get("scene") == scene
        and export_data.get("descriptor", {}).get("descriptor_version") == "furniture-v3",
        {"status": 200, "schema": "0.5.0", "descriptor": "furniture-v3", "revision_bound": True},
        {
            "status": exported.status_code,
            "schema": export_data.get("schema_version"),
            "descriptor": export_data.get("descriptor", {}).get("descriptor_version"),
            "revision_bound": export_data.get("table_drawings") == drawings,
        },
    )
    implicit = client.post(
        "/api/v1/runs",
        json={
            "document_id": document_id,
            "mode": "geometry_only",
            "input_kind": "mounted_orthographic_views",
            "table_profile": "rectangular_table_v1",
            "proposal_mode": "catalog_baseline",
        },
    )
    audit.check(
        "program.implicit_catalog_choice_rejected",
        implicit.status_code == 422,
        {"status": 422},
        {"status": implicit.status_code, "code": error_code(implicit)},
    )


def audit_alternative(client: httpx.Client, audit: Audit) -> None:
    document_id = upload(client, audit, "corner", "mesa_demo_001.dxf")
    _, result = start(client, audit, "corner", document_id, "corner_supports_v1")
    program = result["table_programs"][0]
    audit.check(
        "program.corner_registry_has_five_hypothetical_occurrences",
        result.get("state") == "needs_review"
        and result.get("evaluated_table_program", {}).get("state") == "hypothesis"
        and len(result.get("evaluated_table_program", {}).get("occurrences", [])) == 5
        and {item["quantity_rule_id"] for item in program["components"]}
        == {"top_one", "four_corner_supports"},
        {"state": "needs_review", "program_state": "hypothesis", "occurrences": 5},
        {
            "state": result.get("state"),
            "program_state": result.get("evaluated_table_program", {}).get("state"),
            "occurrences": len(result.get("evaluated_table_program", {}).get("occurrences", [])),
        },
    )


def audit_variants(client: httpx.Client, audit: Audit) -> None:
    document_id = upload(client, audit, "dimensions", "mesa_demo_002.dxf")
    _, result = start(client, audit, "dimensions", document_id)
    audit.check(
        "variant.changed_dimensions_propagate",
        result.get("evaluated_table_program", {}).get("overall_dimensions")
        == {"width_mm": 1400.0, "depth_mm": 800.0, "height_mm": 760.0},
        {"width_mm": 1400.0, "depth_mm": 800.0, "height_mm": 760.0},
        result.get("evaluated_table_program", {}).get("overall_dimensions"),
    )

    document_id = upload(client, audit, "missing_side", "mesa_demo_003.dxf")
    run_id, result = start(client, audit, "missing_side", document_id)
    program = result["table_programs"][0]
    reviewed = review(client, audit, run_id, program, "missing_side")
    scene_response = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2})
    scene = body(scene_response).get("data", {})
    drawings_response = client.post(
        f"/api/v1/runs/{run_id}/table-drawings", json={"result_revision": 2}
    )
    drawings = body(drawings_response).get("data", {})
    audit.check(
        "variant.missing_side_remains_incomplete_with_source_plan_available",
        "missing_required_view:SIDE" in result.get("table_analysis", {}).get("warnings", [])
        and reviewed.get("state") == "needs_review"
        and scene_response.status_code == 200
        and scene.get("state") == "incomplete"
        and scene.get("objects") == []
        and drawings_response.status_code == 201
        and any(item["status"] == "incomplete" for item in drawings.get("sheets", [])),
        {"warning": "missing_required_view:SIDE", "result": "needs_review", "scene": "incomplete", "incomplete_sheet": True},
        {
            "warning_present": "missing_required_view:SIDE" in result.get("table_analysis", {}).get("warnings", []),
            "result": reviewed.get("state"),
            "scene": scene.get("state"),
            "objects": len(scene.get("objects", [])),
            "incomplete_sheets": sum(item["status"] == "incomplete" for item in drawings.get("sheets", [])),
        },
    )

    document_id = upload(client, audit, "conflict", "mesa_demo_004.dxf")
    _, result = start(client, audit, "conflict", document_id)
    width = next(
        item for item in result["table_analysis"]["measures"] if item["semantic"] == "overall_width"
    )
    audit.check(
        "variant.dimension_conflict_is_null_and_traced",
        width.get("state") == "conflict"
        and width.get("value_mm") is None
        and len(width.get("evidence_ids", [])) >= 2
        and "table_measure_conflict" in result.get("table_analysis", {}).get("warnings", []),
        {"state": "conflict", "value_mm": None, "evidence_count_min": 2},
        {"state": width.get("state"), "value_mm": width.get("value_mm"), "evidence_count": len(width.get("evidence_ids", []))},
    )


def run_audit(base_url: str, timeout: float) -> dict[str, Any]:
    audit = Audit(base_url)
    try:
        with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
            health = client.get("/api/v1/health")
            audit.require(
                "service.health",
                health.status_code == 200 and body(health).get("data", {}).get("status") == "ok",
                {"status": 200, "data.status": "ok"},
                {"status": health.status_code},
            )
            audit_complete(client, audit)
            audit_alternative(client, audit)
            audit_variants(client, audit)
    except AuditStop:
        if not any(item["status"] == "fail" for item in audit.data["checks"]):
            audit.data["checks"].append(
                {"name": "audit_incomplete", "status": "fail", "expected": "all steps", "observed": "required_step_unavailable"}
            )
    except Exception as exc:
        audit.data["checks"].append(
            {"name": "audit_runner", "status": "fail", "expected": "completed", "observed": type(exc).__name__}
        )
        audit.data["findings"].append(
            {"severity": "critical", "check": "audit_runner", "observed": type(exc).__name__}
        )
    audit.capability("mounted_source_ledger", "audited", "observed dimensions and provenance checked")
    audit.capability("bounded_catalog_program", "audited", "explicit side/corner templates; no implicit choice")
    audit.capability("review_scene", "schematic", "versioned review and physical occurrence counts checked")
    audit.capability("technical_drawings", "audited", "SVG and mm DXF artifacts reopened through HTTP")
    audit.capability("table_cost", "synthetic_demo_only", "per-component area and single setup checked")
    audit.capability("live_model", "not_exercised", "runner uses geometry_only and makes no provider call")
    return audit.finish()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8768")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = run_audit(args.base_url, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
