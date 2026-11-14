"""Opt-in HTTP acceptance for one unscaled raster PDF and the paid provider.

Run only against a disposable local Vexplorer instance. The report contains
hashes, identifiers, states and bounded component facts; it never reads or
writes provider credentials, prompts, raw provider bodies or hidden reasoning.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx


def _data(response: httpx.Response, expected: int) -> dict:
    if response.status_code != expected:
        raise RuntimeError(f"unexpected_http_status:{response.status_code}")
    body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        raise RuntimeError("invalid_http_envelope")
    return body["data"]


def _component_summary(component: dict) -> dict:
    return {
        "id": component.get("id"),
        "source_view_ids": component.get("source_view_ids", []),
        "source_document_refs": component.get("source_document_refs", []),
        "dimension_states": {
            name: component.get(name, {}).get("state")
            for name in ("length", "width", "thickness")
        },
        "dimension_values_mm": {
            name: component.get(name, {}).get("value_mm")
            for name in ("length", "width", "thickness")
        },
    }


def run_acceptance(
    client: httpx.Client,
    source: Path,
    *,
    timeout_s: float = 360,
    poll_interval_s: float = 2,
) -> dict:
    source_bytes = source.read_bytes()
    parent = _data(
        client.post(
            "/api/v1/documents",
            files={"file": (source.name, source_bytes, "application/pdf")},
        ),
        201,
    )
    child = _data(
        client.post(
            f"/api/v1/documents/{parent['document_id']}/pdf-pages/1/normalize",
            json={"mm_per_pdf_point": None, "reason": "Aceptación raster sin escala."},
        ),
        200,
    )
    geometry_analysis = child["ingestion"]["capabilities"]["geometry_analysis"]
    scale_provenance = child["ingestion"].get("scale_provenance")
    normalized_dxf = child.get("artifacts", {}).get("normalized_dxf")
    if (
        geometry_analysis is not False
        or scale_provenance is not None
        or normalized_dxf is not None
    ):
        raise AssertionError("raster_acceptance_unexpected_metric_authority")
    submitted = _data(
        client.post(
            "/api/v1/jobs",
            json={
                "document_id": child["document_id"],
                "mode": "live",
                "input_kind": "general_furniture",
                "proposal_mode": "model_generated",
            },
        ),
        202,
    )
    deadline = time.monotonic() + timeout_s
    while True:
        job = _data(client.get(f"/api/v1/jobs/{submitted['id']}"), 200)
        if job["state"] not in {"queued", "running"}:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("raster_acceptance_timeout")
        time.sleep(poll_interval_s)
    if job["state"] != "succeeded" or not job.get("run_id"):
        raise RuntimeError(f"raster_job_{job['state']}")
    general = _data(client.get(f"/api/v1/runs/{job['run_id']}/general"), 200)
    components = general["draft"]["components"]
    summaries = [_component_summary(item) for item in components]
    if not components:
        raise AssertionError("raster_acceptance_has_no_components")
    if any(item["source_view_ids"] for item in summaries):
        raise AssertionError("raster_acceptance_fabricated_ledger_view")
    if any(
        value is not None
        for item in summaries
        for value in item["dimension_values_mm"].values()
    ):
        raise AssertionError("raster_acceptance_fabricated_metric_dimension")
    if any(
        state != "unknown"
        for item in summaries
        for state in item["dimension_states"].values()
    ):
        raise AssertionError("raster_acceptance_metric_dimension_not_unknown")
    proposal_revision = general["proposal_revision"]
    review_revision = general["review_revision"]
    derived = _data(
        client.get(
            f"/api/v1/runs/{job['run_id']}/general/derived",
            params={
                "proposal_revision": proposal_revision,
                "review_revision": review_revision,
            },
        ),
        200,
    )
    package = derived["package"]
    return {
        "date_utc": datetime.now(UTC).isoformat(),
        "source": {"sha256": sha256(source_bytes).hexdigest(), "size_bytes": len(source_bytes)},
        "parent": {"document_id": parent["document_id"], "state": parent["ingestion"]["state"]},
        "child": {
            "document_id": child["document_id"],
            "state": child["ingestion"]["state"],
            "geometry_analysis": geometry_analysis,
            "scale_provenance": scale_provenance,
            "normalized_dxf": normalized_dxf,
        },
        "job": job,
        "general": {
            "status": general["status"],
            "proposal_revision": proposal_revision,
            "review_revision": review_revision,
            "components": summaries,
        },
        "derived": {
            "package_status": package["status"],
            "bom_row_count": len(package["bom_rows"]),
            "scene_status": package["scene"]["status"],
            "cost_basis_status": package["cost_basis"]["status"],
        },
        "assertions": {
            "complete_http_path": True,
            "no_fabricated_ledger_views": True,
            "metric_dimensions_remain_unknown": True,
            "unscaled_raster_has_no_metric_authority": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8772")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--invoke-paid-provider", action="store_true", required=True)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        report = run_acceptance(client, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    args.output.write_bytes(encoded)
    print(json.dumps({
        "output": str(args.output),
        "sha256": sha256(encoded).hexdigest(),
        "job_state": report["job"]["state"],
        "run_id": report["job"]["run_id"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
