"""Reproducible black-box audit of the Vexplorer HTTP API.

This script intentionally uses only public demo fixtures and HTTP. It never
loads evaluator references, provider credentials, or the runtime database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "planos_demo"
DEFAULT_OUTPUT = ROOT / "docs" / "auditoria" / "2026-11-14" / "api.json"


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Client:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> HTTPResult:
        request_headers = dict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return HTTPResult(
                    response.status,
                    {key.casefold(): value for key, value in response.headers.items()},
                    response.read(),
                )
        except urllib.error.HTTPError as exc:
            return HTTPResult(
                exc.code,
                {key.casefold(): value for key, value in exc.headers.items()},
                exc.read(),
            )

    def get(self, path: str) -> HTTPResult:
        return self.request("GET", path)

    def post_json(self, path: str, value: Any) -> HTTPResult:
        return self.request("POST", path, json_body=value)

    def upload(self, path: Path, filename: str | None = None) -> HTTPResult:
        boundary = f"vexplorer-audit-{uuid.uuid4().hex}"
        public_name = filename or path.name
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{public_name}"\r\n'
            "Content-Type: application/dxf\r\n\r\n"
        ).encode("utf-8")
        payload = prefix + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
        return self.request(
            "POST",
            "/api/v1/documents",
            body=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    def upload_bytes(self, content: bytes, filename: str) -> HTTPResult:
        temp_boundary = f"vexplorer-audit-{uuid.uuid4().hex}"
        prefix = (
            f"--{temp_boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        payload = prefix + content + f"\r\n--{temp_boundary}--\r\n".encode("ascii")
        return self.request(
            "POST",
            "/api/v1/documents",
            body=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={temp_boundary}"},
        )


class Audit:
    def __init__(self, base_url: str) -> None:
        self.started = time.monotonic()
        self.report: dict[str, Any] = {
            "audit_schema": "vexplorer-api-audit-1",
            "generated_at": datetime.now(UTC).isoformat(),
            "target": base_url,
            "policy": {
                "transport": "real_http",
                "run_mode": "geometry_only",
                "embedding_mode": "offline",
                "provider_calls": False,
                "private_reference_reads": False,
                "assumes_empty_library": False,
            },
            "checks": [],
            "resources": {"documents": {}, "runs": {}, "library_items": {}},
            "capabilities": {},
            "findings": [],
        }

    def check(
        self,
        name: str,
        condition: bool,
        expected: Any,
        observed: Any,
        *,
        endpoint: str | None = None,
        severity: str = "important",
    ) -> None:
        entry = {
            "name": name,
            "status": "pass" if condition else "fail",
            "expected": expected,
            "observed": observed,
        }
        if endpoint is not None:
            entry["endpoint"] = endpoint
        self.report["checks"].append(entry)
        if not condition:
            self.report["findings"].append(
                {"severity": severity, "check": name, "expected": expected, "observed": observed}
            )

    def capability(self, name: str, state: str, evidence: str) -> None:
        self.report["capabilities"][name] = {"state": state, "evidence": evidence}

    def finish(self) -> dict[str, Any]:
        counts = Counter(item["status"] for item in self.report["checks"])
        self.report["summary"] = {
            "passed": counts["pass"],
            "failed": counts["fail"],
            "duration_ms": round((time.monotonic() - self.started) * 1000),
            "result": "pass" if counts["fail"] == 0 else "findings",
        }
        return self.report


def error_code(response: HTTPResult) -> str | None:
    try:
        return response.json().get("error", {}).get("code")
    except (json.JSONDecodeError, AttributeError):
        return None


def upload(client: Client, audit: Audit, key: str, filename: str) -> str:
    response = client.upload(FIXTURES / filename)
    audit.check(
        f"upload.{key}",
        response.status == 201,
        {"status": 201},
        {"status": response.status, "error": error_code(response)},
        endpoint="POST /api/v1/documents",
    )
    if response.status != 201:
        raise RuntimeError(f"upload failed for {filename}: {response.status}")
    data = response.json()["data"]
    expected_hash = hashlib.sha256((FIXTURES / filename).read_bytes()).hexdigest()
    audit.check(
        f"upload.{key}.integrity",
        data["sha256"] == expected_hash and data["size_bytes"] == (FIXTURES / filename).stat().st_size,
        {"sha256": expected_hash, "size_bytes": (FIXTURES / filename).stat().st_size},
        {"sha256": data["sha256"], "size_bytes": data["size_bytes"]},
    )
    audit.report["resources"]["documents"][key] = data["document_id"]
    return data["document_id"]


def start_run(client: Client, audit: Audit, key: str, document_id: str) -> tuple[str, dict[str, Any]]:
    response = client.post_json(
        "/api/v1/runs", {"document_id": document_id, "mode": "geometry_only"}
    )
    audit.check(
        f"run.{key}.create",
        response.status == 201,
        {"status": 201, "mode": "geometry_only"},
        {"status": response.status, "error": error_code(response)},
        endpoint="POST /api/v1/runs",
    )
    if response.status != 201:
        raise RuntimeError(f"run failed for {key}: {response.status}")
    data = response.json()["data"]
    run_id = data["run"]["id"]
    audit.report["resources"]["runs"][key] = run_id
    return run_id, data["result"]


def review(client: Client, audit: Audit, key: str, run_id: str) -> dict[str, Any]:
    response = client.post_json(
        f"/api/v1/runs/{run_id}/reviews",
        {
            "base_result_revision": 1,
            "scenario_id": "scenario-between-sides",
            "confirmed_thickness_mm": 18,
            "material": "tablero sintético",
            "finish": "melamina sintética",
            "notes": "Decisión controlada de auditoría API; no validación técnica humana",
            "reviewer_name": "Auditoría API 2026-11-14",
        },
    )
    audit.check(
        f"review.{key}",
        response.status == 201,
        {"status": 201, "result_revision": 2},
        {"status": response.status, "error": error_code(response)},
        endpoint="POST /api/v1/runs/{run_id}/reviews",
    )
    if response.status != 201:
        raise RuntimeError(f"review failed for {key}: {response.status}")
    return response.json()["data"]


def save_library(
    client: Client, audit: Audit, key: str, run_id: str, label: str
) -> dict[str, Any]:
    response = client.post_json(
        f"/api/v1/runs/{run_id}/library",
        {"result_revision": 2, "label": label, "embedding_mode": "offline"},
    )
    audit.check(
        f"library.{key}.save_offline",
        response.status == 201,
        {"status": 201, "embedding": None},
        {"status": response.status, "error": error_code(response)},
        endpoint="POST /api/v1/runs/{run_id}/library",
    )
    if response.status != 201:
        raise RuntimeError(f"library save failed for {key}: {response.status}")
    item = response.json()["data"]
    audit.report["resources"]["library_items"][key] = item["id"]
    return item


def audit_http(base_url: str, timeout: float) -> dict[str, Any]:
    client = Client(base_url, timeout)
    audit = Audit(base_url)
    private_route_marker = "/".join(("evaluation", "reference"))

    health = client.get("/api/v1/health")
    audit.check(
        "service.health",
        health.status == 200 and health.json().get("data", {}).get("status") == "ok",
        {"status": 200, "data.status": "ok"},
        {"status": health.status, "data": health.json().get("data") if health.status == 200 else None},
        endpoint="GET /api/v1/health",
    )
    config_response = client.get("/api/v1/config")
    config = config_response.json().get("data", {}) if config_response.status == 200 else {}
    audit.check(
        "service.config_safe_shape",
        config_response.status == 200
        and "geometry_only" in config.get("modes", [])
        and "api_key" not in json.dumps(config).casefold(),
        {"status": 200, "geometry_only": True, "credential_fields": False},
        {
            "status": config_response.status,
            "modes": config.get("modes"),
            "live_available": config.get("live_available"),
            "semantic_available": config.get("semantic", {}).get("available"),
        },
        endpoint="GET /api/v1/config",
    )

    invalid_format = client.upload_bytes(b"not a dxf", "audit.txt")
    audit.check(
        "negative.unsupported_upload_format",
        invalid_format.status == 415 and error_code(invalid_format) == "unsupported_format",
        {"status": 415, "code": "unsupported_format"},
        {"status": invalid_format.status, "code": error_code(invalid_format)},
        endpoint="POST /api/v1/documents",
    )
    invalid_dxf_upload = client.upload_bytes(b"invalid dxf bytes", "invalid-audit.dxf")
    invalid_dxf_id = invalid_dxf_upload.json().get("data", {}).get("document_id")
    audit.check(
        "negative.invalid_dxf_upload_is_stored_not_interpreted",
        invalid_dxf_upload.status == 201 and bool(invalid_dxf_id),
        {"status": 201, "document_id": "present"},
        {"status": invalid_dxf_upload.status, "document_id": bool(invalid_dxf_id)},
        endpoint="POST /api/v1/documents",
        severity="minor",
    )
    invalid_drawing = client.get(f"/api/v1/documents/{invalid_dxf_id}/drawing")
    invalid_preview = client.get(f"/api/v1/documents/{invalid_dxf_id}/preview.svg")
    audit.check(
        "negative.invalid_dxf_rejected_by_drawing",
        invalid_drawing.status == 422 and error_code(invalid_drawing) == "invalid_dxf",
        {"status": 422, "code": "invalid_dxf"},
        {"status": invalid_drawing.status, "code": error_code(invalid_drawing)},
        endpoint="GET /api/v1/documents/{document_id}/drawing",
    )
    audit.check(
        "negative.invalid_dxf_rejected_by_preview",
        invalid_preview.status == 422 and error_code(invalid_preview) == "invalid_dxf",
        {"status": 422, "code": "invalid_dxf"},
        {"status": invalid_preview.status, "code": error_code(invalid_preview)},
        endpoint="GET /api/v1/documents/{document_id}/preview.svg",
    )

    original_id = upload(client, audit, "original", "estanteria_montada.dxf")
    drawing_response = client.get(f"/api/v1/documents/{original_id}/drawing")
    drawing = drawing_response.json().get("data", {}) if drawing_response.status == 200 else {}
    audit.check(
        "drawing.original_observations",
        drawing_response.status == 200
        and drawing.get("source_unit") == "mm"
        and len(drawing.get("views", [])) == 3
        and len(drawing.get("dimensions", [])) == 4,
        {"status": 200, "source_unit": "mm", "views": 3, "dimensions": 4},
        {
            "status": drawing_response.status,
            "source_unit": drawing.get("source_unit"),
            "views": len(drawing.get("views", [])),
            "dimensions": len(drawing.get("dimensions", [])),
        },
        endpoint="GET /api/v1/documents/{document_id}/drawing",
    )
    preview = client.get(f"/api/v1/documents/{original_id}/preview.svg")
    preview_text = preview.text().lstrip()
    audit.check(
        "preview.original_svg_security",
        preview.status == 200
        and "image/svg+xml" in preview.headers.get("content-type", "")
        and preview_text.startswith("<?xml")
        and "default-src 'none'" in preview.headers.get("content-security-policy", "")
        and preview.headers.get("x-content-type-options") == "nosniff",
        {"status": 200, "svg": True, "csp": "default-src 'none'", "nosniff": True},
        {
            "status": preview.status,
            "content_type": preview.headers.get("content-type"),
            "bytes": len(preview.body),
            "csp": preview.headers.get("content-security-policy"),
            "nosniff": preview.headers.get("x-content-type-options"),
        },
        endpoint="GET /api/v1/documents/{document_id}/preview.svg",
    )

    unknown_id = upload(client, audit, "unknown_units", "mueble_demo_unidades_desconocidas.dxf")
    unknown_response = client.get(f"/api/v1/documents/{unknown_id}/drawing")
    unknown = unknown_response.json().get("data", {}) if unknown_response.status == 200 else {}
    unknown_mm_values = [
        value
        for graphic in unknown.get("dimension_graphics", [])
        for key, value in graphic.items()
        if key.endswith("_mm") and value is not None
    ]
    audit.check(
        "drawing.unknown_units_preserved",
        unknown_response.status == 200
        and unknown.get("source_unit") == "unknown"
        and unknown.get("coordinate_unit") == "source"
        and all(item.get("points_mm") is None for item in unknown.get("entities", []))
        and all(item.get("value_mm") is None for item in unknown.get("dimensions", []))
        and not unknown_mm_values,
        {"source_unit": "unknown", "coordinate_unit": "source", "metric_values": 0},
        {
            "status": unknown_response.status,
            "source_unit": unknown.get("source_unit"),
            "coordinate_unit": unknown.get("coordinate_unit"),
            "metric_graphic_values": len(unknown_mm_values),
        },
        endpoint="GET /api/v1/documents/{document_id}/drawing",
    )
    unknown_preview = client.get(f"/api/v1/documents/{unknown_id}/preview.svg")
    audit.check(
        "preview.unknown_units_still_visible",
        unknown_preview.status == 200 and len(unknown_preview.body) > 100,
        {"status": 200, "nonempty_svg": True},
        {"status": unknown_preview.status, "bytes": len(unknown_preview.body)},
        endpoint="GET /api/v1/documents/{document_id}/preview.svg",
    )

    trapezoid_id = upload(client, audit, "trapezoid", "mueble_demo_trapecio.dxf")
    trapezoid_drawing = client.get(f"/api/v1/documents/{trapezoid_id}/drawing")
    trapezoid_preview = client.get(f"/api/v1/documents/{trapezoid_id}/preview.svg")
    trapezoid_run = client.post_json(
        "/api/v1/runs", {"document_id": trapezoid_id, "mode": "geometry_only"}
    )
    audit.check(
        "drawing.trapezoid_visible_but_not_decomposed",
        trapezoid_drawing.status == 200
        and trapezoid_preview.status == 200
        and trapezoid_run.status == 422
        and error_code(trapezoid_run) == "unsupported_geometry",
        {"drawing": 200, "preview": 200, "run": 422, "code": "unsupported_geometry"},
        {
            "drawing": trapezoid_drawing.status,
            "preview": trapezoid_preview.status,
            "run": trapezoid_run.status,
            "code": error_code(trapezoid_run),
        },
        endpoint="POST /api/v1/runs",
    )

    incomplete_id = upload(client, audit, "incomplete", "estanteria_incompleta.dxf")
    incomplete_run_id, incomplete_result = start_run(client, audit, "incomplete", incomplete_id)
    incomplete_scene_response = client.get(
        f"/api/v1/runs/{incomplete_run_id}/scene?result_revision=1"
    )
    incomplete_scene = incomplete_scene_response.json().get("data", {})
    unknown_thicknesses = [
        component.get("thickness_mm")
        for scenario in incomplete_result.get("scenarios", [])
        for component in scenario.get("components", [])
    ]
    audit.check(
        "run.incomplete_keeps_unknown_and_has_no_solids",
        incomplete_result.get("state") == "needs_review"
        and unknown_thicknesses
        and all(value is None for value in unknown_thicknesses)
        and incomplete_scene_response.status == 200
        and incomplete_scene.get("state") == "unavailable"
        and incomplete_scene.get("objects") == [],
        {"state": "needs_review", "thicknesses": "all null", "scene_objects": 0},
        {
            "state": incomplete_result.get("state"),
            "thickness_values": sorted({str(value) for value in unknown_thicknesses}),
            "scene_state": incomplete_scene.get("state"),
            "scene_objects": len(incomplete_scene.get("objects", [])),
        },
        endpoint="GET /api/v1/runs/{run_id}/scene?result_revision=1",
    )

    run_id, initial = start_run(client, audit, "primary", original_id)
    pre_scene_response = client.get(f"/api/v1/runs/{run_id}/scene?result_revision=1")
    pre_scene = pre_scene_response.json().get("data", {})
    audit.check(
        "scene.pre_review_unavailable",
        pre_scene_response.status == 200
        and pre_scene.get("state") == "unavailable"
        and pre_scene.get("objects") == [],
        {"status": 200, "state": "unavailable", "objects": 0},
        {
            "status": pre_scene_response.status,
            "state": pre_scene.get("state"),
            "objects": len(pre_scene.get("objects", [])),
        },
        endpoint="GET /api/v1/runs/{run_id}/scene?result_revision=1",
    )
    reviewed = review(client, audit, "primary", run_id)
    stale = client.post_json(
        f"/api/v1/runs/{run_id}/reviews",
        {
            "base_result_revision": 1,
            "scenario_id": "scenario-between-sides",
            "confirmed_thickness_mm": 18,
            "notes": "Intento obsoleto controlado",
            "reviewer_name": "Auditoría API 2026-11-14",
        },
    )
    snapshot_response = client.get(f"/api/v1/runs/{run_id}")
    snapshot = snapshot_response.json().get("data", {})
    audit.check(
        "review.stale_rejected_without_mutation",
        stale.status == 409
        and error_code(stale) == "stale_result_revision"
        and snapshot.get("result", {}).get("result_revision") == 2,
        {"status": 409, "code": "stale_result_revision", "current_revision": 2},
        {
            "status": stale.status,
            "code": error_code(stale),
            "current_revision": snapshot.get("result", {}).get("result_revision"),
        },
        endpoint="POST /api/v1/runs/{run_id}/reviews",
    )
    revisions_response = client.get(f"/api/v1/runs/{run_id}/revisions")
    revisions = revisions_response.json().get("data", [])
    audit.check(
        "review.history_preserved",
        revisions_response.status == 200
        and [item.get("result_revision") for item in revisions] == [1, 2],
        {"revisions": [1, 2]},
        {"status": revisions_response.status, "revisions": [item.get("result_revision") for item in revisions]},
        endpoint="GET /api/v1/runs/{run_id}/revisions",
    )

    scene_response = client.get(f"/api/v1/runs/{run_id}/scene?result_revision=2")
    scene = scene_response.json().get("data", {})
    role_counts = Counter(item.get("role") for item in scene.get("objects", []))
    volume = sum(
        item["dimensions_mm"]["x"]
        * item["dimensions_mm"]["y"]
        * item["dimensions_mm"]["z"]
        for item in scene.get("objects", [])
    )
    audit.check(
        "scene.reviewed_physical_occurrences",
        scene_response.status == 200
        and scene.get("state") == "ready"
        and role_counts == {"side_panel": 2, "top_panel": 1, "base_panel": 1, "shelf": 2}
        and abs(volume - 31_622_400.0) < 0.001,
        {
            "state": "ready",
            "roles": {"side_panel": 2, "top_panel": 1, "base_panel": 1, "shelf": 2},
            "volume_mm3": 31_622_400.0,
        },
        {"status": scene_response.status, "state": scene.get("state"), "roles": role_counts, "volume_mm3": volume},
        endpoint="GET /api/v1/runs/{run_id}/scene?result_revision=2",
    )
    explanations_response = client.get(
        f"/api/v1/runs/{run_id}/explanations?result_revision=2"
    )
    explanations = explanations_response.json().get("data", {})
    shelf_explanation = next(
        (piece for piece in explanations.get("pieces", []) if piece.get("role") == "shelf"), {}
    )
    shelf_formula = (shelf_explanation.get("formulas") or [{}])[0]
    audit.check(
        "explanations.shelf_formula_and_sources",
        explanations_response.status == 200
        and shelf_formula.get("expression") == "overall_width_mm - 2 * confirmed_thickness_mm"
        and shelf_formula.get("result_mm") == 864.0
        and bool(shelf_explanation.get("evidence_ids")),
        {"formula": "overall_width_mm - 2 * confirmed_thickness_mm", "result_mm": 864.0, "evidence": True},
        {
            "status": explanations_response.status,
            "formula": shelf_formula.get("expression"),
            "result_mm": shelf_formula.get("result_mm"),
            "evidence_count": len(shelf_explanation.get("evidence_ids", [])),
        },
        endpoint="GET /api/v1/runs/{run_id}/explanations?result_revision=2",
    )

    comparables_response = client.get(f"/api/v1/runs/{run_id}/comparables")
    comparables = comparables_response.json().get("data", [])
    audit.check(
        "economy.synthetic_comparables_identified",
        comparables_response.status == 200
        and len(comparables) == 3
        and all(item.get("synthetic") is True for item in comparables),
        {"status": 200, "count": 3, "all_synthetic": True},
        {
            "status": comparables_response.status,
            "count": len(comparables),
            "ids": [item.get("id") for item in comparables],
            "all_synthetic": bool(comparables) and all(item.get("synthetic") is True for item in comparables),
        },
        endpoint="GET /api/v1/runs/{run_id}/comparables",
    )
    estimate_first_response = client.post_json(
        f"/api/v1/runs/{run_id}/estimate", {"result_revision": 2}
    )
    estimate_second_response = client.post_json(
        f"/api/v1/runs/{run_id}/estimate", {"result_revision": 2}
    )
    estimate_first = estimate_first_response.json().get("data", {})
    estimate_second = estimate_second_response.json().get("data", {})
    concept_ids = [item.get("id") for item in estimate_first.get("concepts", [])]
    concept_sum = round(sum(item.get("amount", 0) for item in estimate_first.get("concepts", [])), 2)
    audit.check(
        "economy.estimate_idempotent_without_double_concepts",
        estimate_first_response.status == 201
        and estimate_second_response.status == 201
        and estimate_first == estimate_second
        and len(concept_ids) == len(set(concept_ids)) == 2
        and concept_sum == estimate_first.get("total") == 127.84,
        {"statuses": [201, 201], "concept_ids": ["setup", "material"], "total_eur": 127.84},
        {
            "statuses": [estimate_first_response.status, estimate_second_response.status],
            "concept_ids": concept_ids,
            "concept_sum": concept_sum,
            "total": estimate_first.get("total"),
            "responses_equal": estimate_first == estimate_second,
        },
        endpoint="POST /api/v1/runs/{run_id}/estimate",
    )

    primary_library = save_library(
        client, audit, "primary", run_id, "audit-api-20261114-primary"
    )
    library_cases = {
        "translated": "mueble_demo_004.dxf",
        "dimensional": "mueble_demo_002.dxf",
        "structural": "mueble_demo_003.dxf",
    }
    own_items = {"primary": primary_library}
    own_runs = {"primary": run_id}
    for key, filename in library_cases.items():
        document_id = upload(client, audit, key, filename)
        candidate_run_id, _ = start_run(client, audit, key, document_id)
        review(client, audit, key, candidate_run_id)
        own_runs[key] = candidate_run_id
        own_items[key] = save_library(
            client, audit, key, candidate_run_id, f"audit-api-20261114-{key}"
        )

    audit.check(
        "library.translated_descriptor_invariance",
        primary_library.get("descriptor") == own_items["translated"].get("descriptor")
        and primary_library.get("descriptor_fingerprint")
        == own_items["translated"].get("descriptor_fingerprint"),
        {"descriptor_equal": True, "fingerprint_equal": True},
        {
            "descriptor_equal": primary_library.get("descriptor") == own_items["translated"].get("descriptor"),
            "fingerprint_equal": primary_library.get("descriptor_fingerprint")
            == own_items["translated"].get("descriptor_fingerprint"),
        },
    )
    descriptor_text = json.dumps(
        [item.get("descriptor") for item in own_items.values()], ensure_ascii=False
    ).casefold()
    forbidden_descriptor_fragments = [
        "audit-api-20261114",
        "mueble_demo",
        "estanteria_montada",
        private_route_marker,
        "doc-",
        "run-",
    ]
    audit.check(
        "library.descriptor_has_no_ids_paths_or_private_answers",
        not any(fragment in descriptor_text for fragment in forbidden_descriptor_fragments),
        {"forbidden_fragments_found": []},
        {"forbidden_fragments_found": [fragment for fragment in forbidden_descriptor_fragments if fragment in descriptor_text]},
    )
    listing_response = client.get("/api/v1/library")
    listing = listing_response.json().get("data", [])
    listed_ids = {item.get("id") for item in listing}
    own_library_ids = {item["id"] for item in own_items.values()}
    audit.check(
        "library.list_contains_own_offline_items_without_assuming_empty_state",
        listing_response.status == 200
        and own_library_ids <= listed_ids
        and all(item.get("embedding") is None for item in listing if item.get("id") in own_library_ids),
        {"own_items_present": 4, "own_embeddings": "all null"},
        {
            "status": listing_response.status,
            "library_total": len(listing),
            "own_items_present": len(own_library_ids & listed_ids),
        },
        endpoint="GET /api/v1/library",
    )
    similarity_response = client.post_json(
        f"/api/v1/runs/{run_id}/similarity",
        {"result_revision": 2, "mode": "geometric", "limit": 50},
    )
    matches = similarity_response.json().get("data", [])
    own_scores = {
        item.get("run_id"): item.get("score")
        for item in matches
        if item.get("run_id") in set(own_runs.values())
    }
    audit.check(
        "library.geometric_similarity_ranks_own_controls",
        similarity_response.status == 200
        and own_scores.get(own_runs["translated"]) == 1.0
        and own_scores.get(own_runs["dimensional"], -1)
        > own_scores.get(own_runs["structural"], -1),
        {"translated_score": 1.0, "dimensional_gt_structural": True},
        {
            "status": similarity_response.status,
            "own_scores": {key: own_scores.get(value) for key, value in own_runs.items() if key != "primary"},
            "all_match_count": len(matches),
        },
        endpoint="POST /api/v1/runs/{run_id}/similarity",
    )
    semantic_response = client.post_json(
        f"/api/v1/runs/{run_id}/similarity",
        {"result_revision": 2, "mode": "semantic", "limit": 10},
    )
    audit.check(
        "library.offline_item_does_not_fallback_to_semantic",
        semantic_response.status == 409 and error_code(semantic_response) == "semantic_embedding_missing",
        {"status": 409, "code": "semantic_embedding_missing"},
        {"status": semantic_response.status, "code": error_code(semantic_response)},
        endpoint="POST /api/v1/runs/{run_id}/similarity",
    )
    groups_first_response = client.post_json(
        "/api/v1/library/groups", {"mode": "geometric", "threshold": 0.999999}
    )
    groups_second_response = client.post_json(
        "/api/v1/library/groups", {"mode": "geometric", "threshold": 0.999999}
    )
    groups_first = groups_first_response.json().get("data", [])
    groups_second = groups_second_response.json().get("data", [])
    paired_group = next(
        (
            item
            for item in groups_first
            if {primary_library["id"], own_items["translated"]["id"]}
            <= set(item.get("member_ids", []))
        ),
        None,
    )
    audit.check(
        "library.geometric_groups_reproducible_for_own_controls",
        groups_first_response.status == 200
        and groups_second_response.status == 200
        and groups_first == groups_second
        and paired_group is not None,
        {"statuses": [200, 200], "responses_equal": True, "own_pair_grouped": True},
        {
            "statuses": [groups_first_response.status, groups_second_response.status],
            "responses_equal": groups_first == groups_second,
            "group_count": len(groups_first),
            "own_pair_group_id": paired_group.get("id") if paired_group else None,
        },
        endpoint="POST /api/v1/library/groups",
    )

    export_json_response = client.get(f"/api/v1/runs/{run_id}/exports?format=json")
    export_csv_response = client.get(f"/api/v1/runs/{run_id}/exports?format=csv")
    export_bundle = export_json_response.json() if export_json_response.status == 200 else {}
    audit.check(
        "export.revision_bound_complete_bundle",
        export_json_response.status == 200
        and export_bundle.get("result_revision") == 2
        and export_bundle.get("result") == reviewed
        and export_bundle.get("estimate") == estimate_first
        and export_bundle.get("scene", {}).get("state") == "ready"
        and export_bundle.get("explanations", {}).get("result_revision") == 2
        and export_bundle.get("descriptor") == primary_library.get("descriptor")
        and export_bundle.get("library_item", {}).get("id") == primary_library.get("id"),
        {"status": 200, "revision": 2, "required_sections": "coherent"},
        {
            "status": export_json_response.status,
            "revision": export_bundle.get("result_revision"),
            "sections": sorted(export_bundle.keys()),
            "scene_state": export_bundle.get("scene", {}).get("state"),
            "library_item_id": export_bundle.get("library_item", {}).get("id"),
        },
        endpoint="GET /api/v1/runs/{run_id}/exports?format=json",
    )
    audit.check(
        "export.csv_available_and_revision_marked",
        export_csv_response.status == 200
        and "text/csv" in export_csv_response.headers.get("content-type", "")
        and "result_revision" in export_csv_response.text()
        and ",2," in export_csv_response.text(),
        {"status": 200, "content_type": "text/csv", "revision": 2},
        {
            "status": export_csv_response.status,
            "content_type": export_csv_response.headers.get("content-type"),
            "bytes": len(export_csv_response.body),
        },
        endpoint="GET /api/v1/runs/{run_id}/exports?format=csv",
    )
    events_response = client.get(f"/api/v1/runs/{run_id}/events")
    events_text = events_response.text()
    audit.check(
        "events.audit_actions_visible",
        events_response.status == 200
        and "human_review_committed" in events_text
        and "estimate_committed" in events_text
        and "library_item_saved" in events_text,
        {"status": 200, "events": ["human_review_committed", "estimate_committed", "library_item_saved"]},
        {
            "status": events_response.status,
            "content_type": events_response.headers.get("content-type"),
            "contains_review": "human_review_committed" in events_text,
            "contains_estimate": "estimate_committed" in events_text,
            "contains_library": "library_item_saved" in events_text,
        },
        endpoint="GET /api/v1/runs/{run_id}/events",
    )

    invalid_id = client.post_json(
        "/api/v1/runs", {"document_id": "../private", "mode": "geometry_only"}
    )
    missing_document = client.get(
        "/api/v1/documents/doc-00000000000000000000000000000000/drawing"
    )
    traversal = client.get("/api/v1/documents/..%2Fprivate/drawing")
    replay = client.post_json(
        "/api/v1/runs", {"document_id": original_id, "mode": "recorded_replay"}
    )
    extra_field = client.post_json(
        "/api/v1/runs",
        {"document_id": original_id, "mode": "geometry_only", "private_path": "blocked"},
    )
    invalid_export = client.get(f"/api/v1/runs/{run_id}/exports?format=pdf")
    missing_revision = client.get(f"/api/v1/runs/{run_id}/scene?result_revision=999")
    negative_expectations = [
        ("negative.invalid_document_id", invalid_id, 422, None),
        ("negative.missing_document", missing_document, 404, "document_not_found"),
        ("negative.encoded_traversal", traversal, (404, 422), None),
        ("negative.recorded_replay_explicitly_unavailable", replay, 409, "recorded_replay_unavailable"),
        ("negative.extra_request_field_rejected", extra_field, 422, None),
        ("negative.invalid_export_format", invalid_export, 422, None),
        ("negative.missing_revision", missing_revision, 404, "result_not_found"),
    ]
    for name, response, expected_status, expected_code in negative_expectations:
        allowed = expected_status if isinstance(expected_status, tuple) else (expected_status,)
        condition = response.status in allowed and (
            expected_code is None or error_code(response) == expected_code
        )
        audit.check(
            name,
            condition,
            {"status": expected_status, "code": expected_code},
            {"status": response.status, "code": error_code(response)},
            severity="important",
        )

    openapi = client.get("/openapi.json")
    exposed_text = "\n".join(
        [config_response.text(), openapi.text() if openapi.status == 200 else ""]
    ).casefold()
    private_fragments = [
        private_route_marker,
        ".runtime/audit-20261114",
        "openai_api_key",
        "library_reference.json",
        "private_id",
    ]
    private_routes = [
        client.get(f"/{private_route_marker}/library_reference.json"),
        client.get(f"/api/v1/{private_route_marker}/library_reference.json"),
    ]
    audit.check(
        "privacy.config_and_openapi_do_not_expose_private_paths_or_secrets",
        config_response.status == 200
        and openapi.status == 200
        and not any(fragment in exposed_text for fragment in private_fragments),
        {"statuses": [200, 200], "private_fragments_found": []},
        {
            "statuses": [config_response.status, openapi.status],
            "private_fragments_found": [fragment for fragment in private_fragments if fragment in exposed_text],
        },
        endpoint="GET /api/v1/config + GET /openapi.json",
    )
    audit.check(
        "privacy.reference_routes_not_served",
        all(response.status == 404 for response in private_routes),
        {"statuses": [404, 404]},
        {"statuses": [response.status for response in private_routes]},
    )

    audit.capability("document_upload", "works", "valid DXF stored with matching SHA-256 and size")
    audit.capability("drawing_and_svg_preview", "works", "metric, unknown-unit and trapezoid previews observed")
    audit.capability("rectangular_decomposition", "works_for_declared_demo_subset", "geometry_only created two-scenario runs; trapezoid abstained")
    audit.capability("revision_history_and_stale_guard", "works", "revisions 1/2 preserved; stale write returned 409")
    audit.capability("reconstruction", "works_after_review", "six physical occurrences and independent volume matched")
    audit.capability("economy", "synthetic_demo_only", "three synthetic comparables; repeat estimate 127.84 EUR without duplicated concepts")
    audit.capability("offline_library_and_geometric_similarity", "works", "own translated/dimensional/structural controls located among shared library state")
    audit.capability("semantic_similarity", "not_exercised", "offline item returned semantic_embedding_missing; no provider call made")
    audit.capability("live_agent", "not_exercised", "provider configuration was read but live mode was intentionally not called")
    audit.capability("recorded_replay", "not_implemented", "explicit recorded_replay_unavailable response")
    audit.capability("dwg_pdf_and_non_rectangular_decomposition", "not_implemented_for_demo", "upload accepts DXF only; trapezoid run rejected")
    audit.capability(
        "separate_piece_views_without_mounted_model",
        "not_implemented",
        "audited workflow derives assembly scenarios from a mounted furniture drawing; it does not accept the newly requested piece-only multi-view quantity contract",
    )
    return audit.finish()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = audit_http(args.base_url, args.timeout)
    except Exception as exc:  # Preserve a sanitized fatal result for interrupted audits.
        report = {
            "audit_schema": "vexplorer-api-audit-1",
            "generated_at": datetime.now(UTC).isoformat(),
            "target": args.base_url,
            "summary": {"result": "fatal", "passed": 0, "failed": 1},
            "findings": [
                {
                    "severity": "critical",
                    "check": "audit_runner",
                    "observed": f"{type(exc).__name__}: {exc}",
                }
            ],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.get("summary", {}), ensure_ascii=False, sort_keys=True))
    return 0 if report.get("summary", {}).get("result") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
