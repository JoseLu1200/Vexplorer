"""Opt-in real provider audit, using only the public table DXF and local HTTP API.

Creates local audit records and invokes the configured paid provider. It never
opens evaluator references or credentials. Reviews are agent test decisions,
not an assertion of industrial approval.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8769")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--invoke-paid-provider", action="store_true", required=True)
    parser.add_argument("--reuse-live-run")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = {"date_utc": datetime.now(UTC).isoformat(), "base_url": args.base_url, "checks": [], "assertions": {}}
    client = httpx.Client(base_url=args.base_url + "/api/v1", timeout=160)

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def call(method, path, **kwargs):
        started = time.monotonic()
        response = client.request(method, path, **kwargs)
        report["checks"].append({"method": method, "path": path, "status": response.status_code, "elapsed_s": round(time.monotonic() - started, 3), "response": response.json()})
        save()
        print(f"{method} {path}: {response.status_code}", flush=True)
        response.raise_for_status()
        return response.json()["data"]

    config = call("GET", "/config")
    assert config["live_available"], "Real provider is not configured"
    if args.reuse_live_run:
        created = call("GET", f"/runs/{args.reuse_live_run}")
    else:
        document = call("POST", "/documents", files={"file": ("public-table.dxf", (root / "data/planos_demo/mesa_demo_001.dxf").read_bytes(), "application/dxf")})
        created = call("POST", "/runs", json={"document_id": document["document_id"], "input_kind": "mounted_orthographic_views", "mode": "live", "table_profile": "rectangular_table_v1", "proposal_mode": "model_generated"})
    run_id = created["run"]["id"]
    result = created["result"]
    program = result["table_programs"][0]
    report["live_run_id"] = run_id
    assert program["proposal_origin"] == "model_generated" and program["table_template_id"] is None
    events = client.get(f"/runs/{run_id}/events")
    events.raise_for_status()
    report["live_events_sse"] = events.text
    assert "proponer_descomposicion" in events.text
    report["assertions"]["real_generated_program"] = True
    if result["result_revision"] == 1:
        decisions = [{"target_kind": kind, "target_id": item["id"], "action": "accept", "reason": "Agente auditor: acepta hipótesis en ensayo técnico, no certificación de fabricación."} for kind, items in (("program", [program]), ("component", program["components"]), ("premise", program["premises"])) for item in items]
        result = call("POST", f"/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Agente auditor — ensayo técnico", "table_program_id": program["id"], "table_decisions": decisions, "notes": "Sin rellenar dimensiones desconocidas ni consultar referencia reservada."})
    revision = result["result_revision"]
    report["reviewed_state"] = result["state"]
    call("POST", f"/runs/{run_id}/table-drawings", json={"result_revision": revision})
    call("GET", f"/runs/{run_id}/explanations", params={"result_revision": revision})
    call("GET", f"/runs/{run_id}/scene", params={"result_revision": revision})
    if result["state"] == "completed":
        call("POST", f"/runs/{run_id}/table-costs", json={"result_revision": revision, "scope": {"material_tariff_id": None, "edge_scope": "none", "operation_tariff_ids": []}})
        if config["semantic"]["available"]:
            first = call("POST", f"/runs/{run_id}/library", json={"result_revision": revision, "label": "Mesa generada — ensayo técnico", "embedding_mode": "openai"})
            again = call("POST", f"/runs/{run_id}/library", json={"result_revision": revision, "label": "Mesa generada — caché", "embedding_mode": "openai"})
            assert first["descriptor"]["descriptor_version"] == "furniture-v3"
            assert first["descriptor_fingerprint"] == again["descriptor_fingerprint"]
            assert first["embedding"]["provider"] == "openai"
            assert again["embedding"]["status"] == "cache"
            compared = []
            for filename in ("mesa_demo_001.dxf", "mesa_demo_002.dxf"):
                doc = call("POST", "/documents", files={"file": ("public-comparison.dxf", (root / "data/planos_demo" / filename).read_bytes(), "application/dxf")})
                baseline = call("POST", "/runs", json={"document_id": doc["document_id"], "input_kind": "mounted_orthographic_views", "mode": "geometry_only", "table_profile": "rectangular_table_v1", "proposal_mode": "catalog_baseline", "table_template_id": "side_supports_v1"})
                bid = baseline["run"]["id"]
                bp = baseline["result"]["table_programs"][0]
                bd = [{"target_kind": kind, "target_id": item["id"], "action": "accept", "reason": "Agente auditor: acepta premisa para comparación sintética."} for kind, items in (("program", [bp]), ("component", bp["components"]), ("premise", bp["premises"])) for item in items]
                reviewed = call("POST", f"/runs/{bid}/reviews", json={"base_result_revision": 1, "reviewer_name": "Agente auditor — comparación", "table_program_id": bp["id"], "table_decisions": bd, "notes": "Sin consultar referencia reservada."})
                assert reviewed["state"] == "completed"
                compared.append(call("POST", f"/runs/{bid}/library", json={"result_revision": 2, "label": "Mesa baseline " + filename, "embedding_mode": "openai"}))
            assert compared[0]["descriptor_fingerprint"] != compared[1]["descriptor_fingerprint"]
            report["assertions"]["distinct_dimensions_change_descriptor"] = True
            call("POST", f"/runs/{run_id}/similarity", json={"result_revision": revision, "mode": "semantic", "limit": 10, "descriptor_version": "furniture-v3"})
            call("POST", "/library/groups", json={"mode": "semantic", "threshold": 0.8, "descriptor_version": "furniture-v3"})
            report["assertions"]["real_embedding_and_fingerprint_stability"] = True
    save()
    print(json.dumps({"run_id": run_id, "reviewed_state": result["state"], "assertions": report["assertions"]}), flush=True)


if __name__ == "__main__":
    main()
