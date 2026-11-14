"""Audit the public parts-only workflow through real HTTP requests."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "planos_demo"
DEFAULT_OUTPUT = ROOT / "docs" / "auditoria" / "2026-11-14" / "parts-api.json"


class AuditStop(RuntimeError):
    pass


class Audit:
    def __init__(self, target: str) -> None:
        self.started = time.monotonic()
        self.data: dict[str, Any] = {
            "audit_schema": "vexplorer-parts-api-audit-1",
            "generated_at": datetime.now(UTC).isoformat(),
            "target": target,
            "policy": {
                "transport": "real_http",
                "run_mode": "geometry_only",
                "embedding_mode": "offline",
                "provider_calls": False,
                "private_reference_reads": False,
                "public_fixtures_only": True,
            },
            "checks": [],
            "findings": [],
            "resources": {"documents": {}, "runs": {}, "library_items": {}},
            "capabilities": {},
        }

    def check(self, name: str, ok: bool, expected: Any, observed: Any, endpoint: str = "") -> bool:
        item = {
            "name": name,
            "status": "pass" if ok else "fail",
            "expected": expected,
            "observed": observed,
        }
        if endpoint:
            item["endpoint"] = endpoint
        self.data["checks"].append(item)
        if not ok:
            self.data["findings"].append(
                {"severity": "important", "check": name, "expected": expected, "observed": observed}
            )
        return ok

    def require(self, name: str, ok: bool, expected: Any, observed: Any, endpoint: str = "") -> None:
        if not self.check(name, ok, expected, observed, endpoint):
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


def code(response: httpx.Response) -> str | None:
    return body(response).get("error", {}).get("code")


def sse_events(response: httpx.Response) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    event_type: str | None = None
    for line in response.text.splitlines():
        if line.startswith("event: "):
            event_type = line.removeprefix("event: ")
        elif line.startswith("data: "):
            try:
                payload = json.loads(line.removeprefix("data: "))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                values.append({"event_type": event_type, **payload})
            event_type = None
    return values


def upload(client: httpx.Client, audit: Audit, key: str, filename: str) -> str:
    with (FIXTURES / filename).open("rb") as stream:
        response = client.post(
            "/api/v1/documents", files={"file": (filename, stream, "application/dxf")}
        )
    data = body(response).get("data", {})
    audit.require(
        f"upload.{key}",
        response.status_code == 201 and bool(data.get("document_id")),
        {"status": 201, "document_id": "present"},
        {"status": response.status_code, "code": code(response)},
        "POST /api/v1/documents",
    )
    audit.data["resources"]["documents"][key] = data["document_id"]
    return data["document_id"]


def start(client: httpx.Client, audit: Audit, key: str, document_id: str) -> tuple[str, dict[str, Any]]:
    response = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "geometry_only", "input_kind": "separated_part_views"},
    )
    data = body(response).get("data", {})
    audit.require(
        f"run.{key}",
        response.status_code == 201
        and data.get("run", {}).get("input_kind") == "separated_part_views"
        and data.get("result", {}).get("input_semantics") == "separated_part_views",
        {"status": 201, "input_kind": "separated_part_views"},
        {"status": response.status_code, "code": code(response)},
        "POST /api/v1/runs",
    )
    run_id = data["run"]["id"]
    audit.data["resources"]["runs"][key] = run_id
    return run_id, data["result"]


def parts(client: httpx.Client, audit: Audit, run_id: str, revision: int, key: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/runs/{run_id}/parts", params={"result_revision": revision})
    data = body(response).get("data", {})
    audit.require(
        f"parts.{key}.r{revision}",
        response.status_code == 200 and data.get("part_analysis", {}).get("schema_version") == "0.4.0",
        {"status": 200, "schema_version": "0.4.0"},
        {"status": response.status_code, "code": code(response)},
        "GET /api/v1/runs/{run_id}/parts",
    )
    return data


def candidate(snapshot: dict[str, Any]) -> dict[str, Any]:
    observation_ids = {item["id"] for item in snapshot["part_analysis"]["observations"]}
    for item in sorted(snapshot["assembly_candidates"], key=lambda value: value["id"]):
        covered = {use["part_observation_id"] for use in item["uses"]} | set(
            item["unassigned_part_observation_ids"]
        )
        if (
            covered == observation_ids
            and not item["unassigned_part_observation_ids"]
            and all(value["status"] == "pass" for value in item["constraints"])
            and all(value["state"] == "derived" for value in item["derived_dimensions"])
        ):
            return item
    raise AuditStop("compatible_candidate_missing")


def review(
    client: httpx.Client, audit: Audit, run_id: str, candidate_id: str, key: str
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Auditoría HTTP parts-only",
            "assembly_candidate_id": candidate_id,
            "material": "tablero sintético",
            "finish": "melamina sintética",
            "notes": "Selección controlada de hipótesis; no validación industrial",
        },
    )
    data = body(response).get("data", {})
    audit.require(
        f"review.{key}",
        response.status_code == 201
        and data.get("result_revision") == 2
        and data.get("selected_assembly_candidate_id") == candidate_id,
        {"status": 201, "revision": 2, "candidate_selected": True},
        {"status": response.status_code, "code": code(response), "state": data.get("state")},
        "POST /api/v1/runs/{run_id}/reviews",
    )
    return data


def audit_complete(client: httpx.Client, audit: Audit) -> None:
    document_id = upload(client, audit, "complete", "piezas_completo.dxf")
    preview = client.get(f"/api/v1/documents/{document_id}/preview.svg")
    audit.check(
        "preview.complete",
        preview.status_code == 200
        and "image/svg+xml" in preview.headers.get("content-type", "")
        and len(preview.content) > 100,
        {"status": 200, "svg": True},
        {"status": preview.status_code, "bytes": len(preview.content)},
    )
    run_id, _ = start(client, audit, "complete", document_id)
    drawing = client.get(f"/api/v1/runs/{run_id}/drawing")
    drawing_data = body(drawing).get("data", {})
    audit.check(
        "drawing.parts_semantics",
        drawing.status_code == 200
        and drawing_data.get("input_kind") == "separated_part_views"
        and len(drawing_data.get("views", [])) == 9,
        {"status": 200, "input_kind": "separated_part_views", "views": 9},
        {
            "status": drawing.status_code,
            "input_kind": drawing_data.get("input_kind"),
            "views": len(drawing_data.get("views", [])),
        },
    )
    initial = parts(client, audit, run_id, 1, "complete")
    observations = initial["part_analysis"]["observations"]
    quantities = [item["quantity"]["value"] for item in observations]
    audit.check(
        "parts.observations_views_and_quantities",
        len(observations) == 3
        and quantities == [2, 2, 2]
        and all(len(item["views"]) == 3 for item in observations)
        and sum(quantities) == 6,
        {"observations": 3, "views_each": 3, "quantities": [2, 2, 2], "occurrences": 6},
        {
            "observations": len(observations),
            "views_each": [len(item["views"]) for item in observations],
            "quantities": quantities,
        },
    )
    selected = candidate(initial)
    allocations: dict[str, list[dict[str, Any]]] = {}
    for use in selected["uses"]:
        allocations.setdefault(use["part_observation_id"], []).append(use)
    allocation_ok = all(
        len({item["source_quantity"] for item in uses}) == 1
        and sum(item["allocated_quantity"] for item in uses) == uses[0]["source_quantity"]
        and sorted(index for item in uses for index in item["occurrence_indices"])
        == list(range(1, uses[0]["source_quantity"] + 1))
        for uses in allocations.values()
    )
    audit.check(
        "candidate.coverage_and_allocations",
        allocation_ok and len(allocations) == 3,
        {"covered_observations": 3, "allocations_equal_source_quantity": True},
        {"covered_observations": len(allocations), "allocations_equal_source_quantity": allocation_ok},
    )
    pre_scene = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 1})
    pre_scene_data = body(pre_scene).get("data", {})
    audit.check(
        "scene.pre_review_unavailable",
        pre_scene.status_code == 200
        and pre_scene_data.get("state") == "unavailable"
        and pre_scene_data.get("objects") == [],
        {"status": 200, "state": "unavailable", "objects": 0},
        {
            "status": pre_scene.status_code,
            "state": pre_scene_data.get("state"),
            "objects": len(pre_scene_data.get("objects", [])),
        },
    )
    reviewed = review(client, audit, run_id, selected["id"], "complete")
    latest = parts(client, audit, run_id, 2, "complete")
    audit.check(
        "review.completed_versioned_snapshot",
        reviewed.get("state") == "completed"
        and latest.get("selected_assembly_candidate_id") == selected["id"]
        and sum(item["quantity"] for item in reviewed.get("pieces", [])) == 6,
        {"state": "completed", "selected": True, "occurrences": 6},
        {
            "state": reviewed.get("state"),
            "selected": latest.get("selected_assembly_candidate_id") == selected["id"],
            "occurrences": sum(item.get("quantity") or 0 for item in reviewed.get("pieces", [])),
        },
    )
    events_response = client.get(f"/api/v1/runs/{run_id}/events")
    committed = [
        item
        for item in sse_events(events_response)
        if item.get("event_type") == "human_review_committed"
        and item.get("result_revision") == 2
    ]
    audit.check(
        "review.sse_records_selected_assembly_candidate",
        events_response.status_code == 200
        and len(committed) == 1
        and committed[0].get("selected_assembly_candidate_id") == selected["id"],
        {"status": 200, "review_events": 1, "selected_candidate_recorded": True},
        {
            "status": events_response.status_code,
            "review_events": len(committed),
            "selected_candidate_recorded": bool(committed)
            and committed[0].get("selected_assembly_candidate_id") == selected["id"],
        },
    )
    observed_use = next(
        use for use in selected["uses"] if use["quantity_source"] == "observed_annotation"
    )
    override = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 2,
            "reviewer_name": "Auditoría HTTP parts-only",
            "assembly_candidate_id": selected["id"],
            "decisions": [
                {
                    "proposal_id": observed_use["id"],
                    "action": "confirm",
                    "role": observed_use["role"],
                    "quantity": 5,
                    "notes": "Intento de contradecir una cantidad observada",
                }
            ],
            "notes": "Control negativo de cantidad observada",
        },
    )
    audit.check(
        "review.observed_quantity_override_rejected",
        override.status_code in {400, 409, 422},
        {"status": [400, 409, 422], "accepted": False},
        {"status": override.status_code, "code": code(override), "accepted": override.is_success},
    )
    stale = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Auditoría HTTP parts-only",
            "assembly_candidate_id": selected["id"],
            "notes": "Intento obsoleto",
        },
    )
    missing = client.get(f"/api/v1/runs/{run_id}/parts", params={"result_revision": 999})
    audit.check(
        "review.stale_and_missing_revision_errors",
        stale.status_code == 409
        and code(stale) == "stale_result_revision"
        and missing.status_code == 404
        and code(missing) == "result_not_found",
        {"stale": [409, "stale_result_revision"], "missing": [404, "result_not_found"]},
        {"stale": [stale.status_code, code(stale)], "missing": [missing.status_code, code(missing)]},
    )
    scene = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2})
    scene_data = body(scene).get("data", {})
    source_counts = Counter(item.get("part_observation_id") for item in scene_data.get("objects", []))
    audit.check(
        "scene.six_traceable_occurrences",
        scene.status_code == 200
        and scene_data.get("state") == "ready"
        and len(scene_data.get("objects", [])) == sum(quantities)
        and sorted(source_counts.values()) == [2, 2, 2]
        and all(item.get("placement_status") == "human_selected" for item in scene_data.get("objects", [])),
        {"status": 200, "state": "ready", "objects": 6, "source_counts": [2, 2, 2]},
        {
            "status": scene.status_code,
            "state": scene_data.get("state"),
            "objects": len(scene_data.get("objects", [])),
            "source_counts": sorted(source_counts.values()),
        },
    )
    comparables = client.get(f"/api/v1/runs/{run_id}/comparables")
    estimate = client.post(f"/api/v1/runs/{run_id}/estimate", json={"result_revision": 2})
    comparable_values = body(comparables).get("data", [])
    estimate_data = body(estimate).get("data", {})
    concepts = {item["id"]: item for item in estimate_data.get("concepts", [])}
    selected_comparable = next(
        (
            item
            for item in comparable_values
            if item.get("id") in estimate_data.get("comparable_ids", [])
        ),
        {},
    )
    reference_rate = (
        selected_comparable.get("material_cost_eur", 0)
        * 1_000_000
        / selected_comparable.get("reference_area_mm2", 1)
    )
    audit.check(
        "cost.area_rate_and_single_setup",
        comparables.status_code == 200
        and estimate.status_code == 201
        and set(concepts) == {"setup", "material"}
        and concepts["setup"]["amount"] == 40.0
        and reference_rate == 50.0
        and concepts["material"]["base_amount"] == 60.0
        and concepts["material"]["factor"] == 1.464
        and concepts["material"]["amount"] == 87.84
        and estimate_data.get("total") == 127.84,
        {"setup": 40.0, "rate_eur_m2": 50.0, "factor": 1.464, "material": 87.84, "total": 127.84},
        {
            "comparables_status": comparables.status_code,
            "estimate_status": estimate.status_code,
            "concept_ids": sorted(concepts),
            "setup": concepts.get("setup", {}).get("amount"),
            "rate_eur_m2": reference_rate,
            "factor": concepts.get("material", {}).get("factor"),
            "material": concepts.get("material", {}).get("amount"),
            "total": estimate_data.get("total"),
        },
    )
    explanations = client.get(f"/api/v1/runs/{run_id}/explanations", params={"result_revision": 2})
    explanations_data = body(explanations).get("data", {})
    audit.check(
        "explanations.reviewed_parts",
        explanations.status_code == 200
        and explanations_data.get("result_revision") == 2
        and len(explanations_data.get("pieces", [])) == len(reviewed.get("pieces", [])),
        {"status": 200, "revision": 2, "pieces": len(reviewed.get("pieces", []))},
        {
            "status": explanations.status_code,
            "revision": explanations_data.get("result_revision"),
            "pieces": len(explanations_data.get("pieces", [])),
        },
    )
    exported = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "json"})
    export_data = body(exported)
    audit.check(
        "export.complete_revision_bundle",
        exported.status_code == 200
        and export_data.get("result_revision") == 2
        and export_data.get("scene", {}).get("state") == "ready"
        and export_data.get("estimate", {}).get("total") == 127.84
        and export_data.get("descriptor", {}).get("descriptor_version") == "furniture-v2",
        {"status": 200, "revision": 2, "scene": "ready", "total": 127.84, "descriptor": "furniture-v2"},
        {
            "status": exported.status_code,
            "revision": export_data.get("result_revision"),
            "scene": export_data.get("scene", {}).get("state"),
            "total": export_data.get("estimate", {}).get("total"),
            "descriptor": export_data.get("descriptor", {}).get("descriptor_version"),
        },
    )


def audit_library(client: httpx.Client, audit: Audit) -> None:
    fixtures = {
        "library_base": "piezas_completo.dxf",
        "library_translated": "piezas_ids_trasladados.dxf",
        "library_dimensions": "piezas_dimensiones_variante.dxf",
        "library_thickness": "piezas_espesor_36.dxf",
    }
    runs: dict[str, str] = {}
    items: dict[str, dict[str, Any]] = {}
    for key, filename in fixtures.items():
        document_id = upload(client, audit, key, filename)
        run_id, _ = start(client, audit, key, document_id)
        response = client.post(
            f"/api/v1/runs/{run_id}/library",
            json={"result_revision": 1, "label": f"audit-parts-{key}", "embedding_mode": "offline"},
        )
        data = body(response).get("data", {})
        audit.require(
            f"library.{key}",
            response.status_code == 201
            and data.get("embedding") is None
            and data.get("descriptor", {}).get("descriptor_version") == "furniture-v2",
            {"status": 201, "embedding": None, "descriptor": "furniture-v2"},
            {"status": response.status_code, "code": code(response)},
        )
        runs[key] = run_id
        items[key] = data
        audit.data["resources"]["library_items"][key] = data["id"]
    base = items["library_base"]
    translated = items["library_translated"]
    audit.check(
        "library.keys_and_translation_invariant",
        base["descriptor"] == translated["descriptor"]
        and base["descriptor_fingerprint"] == translated["descriptor_fingerprint"],
        {"descriptor_equal": True, "fingerprint_equal": True},
        {
            "descriptor_equal": base["descriptor"] == translated["descriptor"],
            "fingerprint_equal": base["descriptor_fingerprint"] == translated["descriptor_fingerprint"],
        },
    )
    thick = items["library_thickness"]
    audit.check(
        "library.dimensions_and_thickness_controls",
        base["descriptor_fingerprint"] != items["library_dimensions"]["descriptor_fingerprint"]
        and base["descriptor_fingerprint"] != thick["descriptor_fingerprint"]
        and base["descriptor"]["dimensions"]["width_mm"] == 900.0
        and thick["descriptor"]["dimensions"]["width_mm"] == 900.0
        and base["descriptor"]["thicknesses_mm"] == [18.0]
        and thick["descriptor"]["thicknesses_mm"] == [36.0],
        {"fingerprints_differ": True, "widths": [900.0, 900.0], "thicknesses": [[18.0], [36.0]]},
        {
            "dimension_differs": base["descriptor_fingerprint"]
            != items["library_dimensions"]["descriptor_fingerprint"],
            "thickness_differs": base["descriptor_fingerprint"] != thick["descriptor_fingerprint"],
            "widths": [base["descriptor"]["dimensions"]["width_mm"], thick["descriptor"]["dimensions"]["width_mm"]],
            "thicknesses": [base["descriptor"]["thicknesses_mm"], thick["descriptor"]["thicknesses_mm"]],
        },
    )
    descriptor_text = json.dumps([item["descriptor"] for item in items.values()]).casefold()
    forbidden = ("k1", "r7", "piezas_", "missing", "unknown_qty")
    audit.check(
        "library.descriptor_excludes_keys_filenames_case_hints",
        all(token not in descriptor_text for token in forbidden),
        {"forbidden_tokens_found": []},
        {"forbidden_tokens_found": [token for token in forbidden if token in descriptor_text]},
    )
    similarity = client.post(
        f"/api/v1/runs/{runs['library_base']}/similarity",
        json={"result_revision": 1, "mode": "geometric", "limit": 50},
    )
    matches = body(similarity).get("data", [])
    translated_match = next(
        (item for item in matches if item.get("run_id") == runs["library_translated"]), None
    )
    groups = client.post(
        "/api/v1/library/groups", json={"mode": "geometric", "threshold": 0.999999}
    )
    group_values = body(groups).get("data", [])
    paired = next(
        (
            item
            for item in group_values
            if {base["id"], translated["id"]} <= set(item.get("member_ids", []))
        ),
        None,
    )
    audit.check(
        "library.geometric_similarity_and_group",
        similarity.status_code == 200
        and translated_match is not None
        and translated_match.get("score") == 1.0
        and groups.status_code == 200
        and paired is not None
        and items["library_dimensions"]["id"] not in paired["member_ids"]
        and thick["id"] not in paired["member_ids"],
        {"translated_score": 1.0, "translated_grouped": True, "variants_excluded": True},
        {
            "similarity_status": similarity.status_code,
            "translated_score": translated_match.get("score") if translated_match else None,
            "groups_status": groups.status_code,
            "paired_group_id": paired.get("id") if paired else None,
        },
    )


def audit_partial(client: httpx.Client, audit: Audit) -> None:
    for key, filename, field in (
        ("qty_unknown", "piezas_qty_desconocida.dxf", "quantity"),
        ("thickness_unknown", "piezas_espesor_desconocido.dxf", "thickness"),
    ):
        document_id = upload(client, audit, key, filename)
        run_id, _ = start(client, audit, key, document_id)
        initial = parts(client, audit, run_id, 1, key)
        observations = initial["part_analysis"]["observations"]
        unknown = [
            item
            for item in observations
            if (
                item["quantity"]["value"] is None
                if field == "quantity"
                else item["dimensions"]["thickness"]["value_mm"] is None
            )
        ]
        audit.check(
            f"partial.{key}.null_preserved",
            len(unknown) == 1,
            {"unknown_observations": 1},
            {"unknown_observations": len(unknown)},
        )
        selected = candidate(initial)
        reviewed = review(client, audit, run_id, selected["id"], key)
        scene = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2})
        scene_data = body(scene).get("data", {})
        unknown_id = unknown[0]["id"] if unknown else None
        audit.check(
            f"partial.{key}.no_fabricated_solid",
            reviewed.get("state") == "needs_review"
            and scene.status_code == 200
            and scene_data.get("state") == "incomplete"
            and unknown_id
            not in {item.get("part_observation_id") for item in scene_data.get("objects", [])},
            {"result_state": "needs_review", "scene_state": "incomplete", "unknown_solid": False},
            {
                "result_state": reviewed.get("state"),
                "scene_status": scene.status_code,
                "scene_state": scene_data.get("state"),
                "objects": len(scene_data.get("objects", [])),
            },
        )
        if unknown:
            observation = unknown[0]
            dimensions = observation["dimensions"]
            affected_uses = [
                use
                for use in selected["uses"]
                if use["part_observation_id"] == observation["id"]
            ]
            decisions = [
                {
                    "proposal_id": use["id"],
                    "action": "confirm",
                    "role": use["role"],
                    "quantity": use["allocated_quantity"]
                    if use["allocated_quantity"] is not None
                    else 2,
                    "length_mm": dimensions["length"]["value_mm"],
                    "width_mm": dimensions["width"]["value_mm"],
                    "thickness_mm": dimensions["thickness"]["value_mm"] or 18.0,
                    "material": "tablero sintético",
                    "finish": "melamina sintética",
                    "notes": "Premisa aportada por revisión humana de auditoría",
                }
                for use in affected_uses
            ]
            completed_response = client.post(
                f"/api/v1/runs/{run_id}/reviews",
                json={
                    "base_result_revision": 2,
                    "reviewer_name": "Auditoría HTTP parts-only",
                    "assembly_candidate_id": selected["id"],
                    "decisions": decisions,
                    "material": "tablero sintético",
                    "finish": "melamina sintética",
                    "notes": "Completa solo la premisa ausente mediante entrada humana",
                },
            )
            completed = body(completed_response).get("data", {})
            completed_scene = client.get(
                f"/api/v1/runs/{run_id}/scene", params={"result_revision": 3}
            )
            completed_scene_data = body(completed_scene).get("data", {})
            audit.check(
                f"partial.{key}.human_input_enables_scene",
                completed_response.status_code == 201
                and completed.get("result_revision") == 3
                and completed.get("state") == "completed"
                and completed_scene.status_code == 200
                and completed_scene_data.get("state") == "ready"
                and len(completed_scene_data.get("objects", [])) == 6
                and unknown_id
                in {
                    item.get("part_observation_id")
                    for item in completed_scene_data.get("objects", [])
                },
                {
                    "review_status": 201,
                    "revision": 3,
                    "result_state": "completed",
                    "scene_state": "ready",
                    "objects": 6,
                    "reviewed_solid": True,
                },
                {
                    "review_status": completed_response.status_code,
                    "code": code(completed_response),
                    "revision": completed.get("result_revision"),
                    "result_state": completed.get("state"),
                    "scene_status": completed_scene.status_code,
                    "scene_state": completed_scene_data.get("state"),
                    "objects": len(completed_scene_data.get("objects", [])),
                    "reviewed_solid": unknown_id
                    in {
                        item.get("part_observation_id")
                        for item in completed_scene_data.get("objects", [])
                    },
                },
            )
            frozen_ledger = parts(client, audit, run_id, 3, f"{key}_reviewed")
            frozen_observation = next(
                item
                for item in frozen_ledger["part_analysis"]["observations"]
                if item["id"] == observation["id"]
            )
            exported = client.get(
                f"/api/v1/runs/{run_id}/exports", params={"format": "json"}
            )
            descriptor = body(exported).get("descriptor", {})
            descriptor_field = "quantity" if field == "quantity" else "thickness_mm"
            expected_value = 2 if field == "quantity" else 18.0
            confirmed_features = [
                feature
                for feature in descriptor.get("part_features", [])
                if feature.get(descriptor_field) == expected_value
                and feature.get("field_states", {}).get(descriptor_field) == "confirmed"
                and descriptor_field not in feature.get("unknown_fields", [])
            ]
            unresolved_suffix = "quantity" if field == "quantity" else "thickness"
            descriptor_unknowns = descriptor.get("unknown_fields", [])
            ledger_value = (
                frozen_observation["quantity"]["value"]
                if field == "quantity"
                else frozen_observation["dimensions"]["thickness"]["value_mm"]
            )
            audit.check(
                f"partial.{key}.descriptor_uses_resolved_value_ledger_stays_null",
                exported.status_code == 200
                and descriptor.get("descriptor_version") == "furniture-v2"
                and descriptor.get("classification_status") == "confirmed"
                and len(confirmed_features) == 1
                and not any(
                    item.endswith(f".{unresolved_suffix}") for item in descriptor_unknowns
                )
                and ledger_value is None,
                {
                    "status": 200,
                    "descriptor": "furniture-v2",
                    "classification": "confirmed",
                    "confirmed_feature_value": expected_value,
                    "resolved_unknown_removed": True,
                    "ledger_value": None,
                },
                {
                    "status": exported.status_code,
                    "descriptor": descriptor.get("descriptor_version"),
                    "classification": descriptor.get("classification_status"),
                    "confirmed_features": len(confirmed_features),
                    "remaining_matching_unknowns": [
                        item
                        for item in descriptor_unknowns
                        if item.endswith(f".{unresolved_suffix}")
                    ],
                    "ledger_value": ledger_value,
                },
            )
    document_id = upload(client, audit, "unassociated", "piezas_ambigua_sin_id.dxf")
    run_id, _ = start(client, audit, "unassociated", document_id)
    snapshot = parts(client, audit, run_id, 1, "unassociated")
    observations = snapshot["part_analysis"]["observations"]
    audit.check(
        "unassociated.not_grouped_and_loose_qty_ignored",
        len(observations) == 3
        and all(item["part_key"] is None for item in observations)
        and all(item["association_basis"] == "unassociated" for item in observations)
        and all(len(item["views"]) == 1 for item in observations)
        and all(item["quantity"]["value"] is None for item in observations)
        and snapshot["assembly_candidates"] == [],
        {"observations": 3, "views_each": 1, "keys": None, "quantities": None, "candidates": 0},
        {
            "observations": len(observations),
            "views_each": [len(item["views"]) for item in observations],
            "keys": [item["part_key"] for item in observations],
            "quantities": [item["quantity"]["value"] for item in observations],
            "candidates": len(snapshot["assembly_candidates"]),
        },
    )
    scene = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 1})
    scene_data = body(scene).get("data", {})
    audit.check(
        "unassociated.no_3d_before_evidence_review",
        scene.status_code == 200
        and scene_data.get("state") == "unavailable"
        and scene_data.get("objects") == [],
        {"status": 200, "state": "unavailable", "objects": 0},
        {
            "status": scene.status_code,
            "state": scene_data.get("state"),
            "objects": len(scene_data.get("objects", [])),
        },
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
            audit_library(client, audit)
            audit_partial(client, audit)
    except AuditStop:
        pass
    except Exception as exc:
        audit.data["checks"].append(
            {"name": "audit_runner", "status": "fail", "expected": "completed", "observed": type(exc).__name__}
        )
        audit.data["findings"].append(
            {"severity": "critical", "check": "audit_runner", "observed": type(exc).__name__}
        )
    audit.capability("separated_part_observations", "audited", "keyed local views, dimensions and quantities checked")
    audit.capability("assembly_candidates", "hypotheses_only", "coverage checked without binding opaque keys to roles")
    audit.capability("reviewed_scene", "schematic", "six traceable occurrences; not manufacturing validation")
    audit.capability("economy", "synthetic_demo_only", "area normalization and one setup concept checked")
    audit.capability("offline_similarity", "audited", "translation, dimensions and thickness controls checked")
    audit.capability("live_agent", "not_exercised", "no provider call made")
    audit.capability("semantic_embeddings", "not_exercised", "all library writes used offline mode")
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
