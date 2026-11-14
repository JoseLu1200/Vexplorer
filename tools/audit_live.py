"""Opt-in HTTP audit: invokes configured live model and embedding provider.

Run against a disposable audit instance; this creates documents/runs/library entries.
Never reads credentials or evaluator references. Requests are made to the local API.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--invoke-paid-provider", action="store_true", required=True)
    parser.add_argument("--reuse-live-run", help="Resume an existing real live run after an interrupted audit.")
    parser.add_argument("--input-kind", choices=("mounted_views_legacy", "separated_part_views"), default="mounted_views_legacy")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = {"date_utc": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url, "checks": []}
    if args.reuse_live_run and args.output.exists():
        evidence = json.loads(args.output.read_text(encoding="utf-8"))
    client = httpx.Client(base_url=args.base_url + "/api/v1", timeout=160)

    def call(method, path, **kwargs):
        started = time.monotonic()
        response = client.request(method, path, **kwargs)
        payload = response.json()
        evidence["checks"].append({"method": method, "path": path, "status": response.status_code, "elapsed_s": round(time.monotonic() - started, 3), "response": payload})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{method} {path}: {response.status_code}", flush=True)
        response.raise_for_status()
        return payload["data"]

    def create_run(filename, mode):
        data = (root / "data" / "planos_demo" / filename).read_bytes()
        document = call("POST", "/documents", files={"file": ("audit-" + filename, data, "application/dxf")})
        return call("POST", "/runs", json={"document_id": document["document_id"], "mode": mode, "input_kind": args.input_kind})

    config = call("GET", "/config")
    separated = args.input_kind == "separated_part_views"
    filenames = ("piezas_completo.dxf", "piezas_dimensiones_variante.dxf", "piezas_ids_trasladados.dxf", "piezas_espesor_36.dxf") if separated else ("estanteria_montada.dxf", "mueble_demo_002.dxf", "mueble_demo_004.dxf")
    evidence["input_kind"] = args.input_kind
    live = call("GET", f"/runs/{args.reuse_live_run}") if args.reuse_live_run else create_run(filenames[0], "live")
    run_id = live["run"]["id"]
    events = client.get(f"/runs/{run_id}/events")
    events.raise_for_status()
    evidence["live_events_sse"] = events.text
    evidence["live_run_id"] = run_id
    items = []
    for filename in filenames:
        run = create_run(filename, "geometry_only")
        run_id = run["run"]["id"]
        review = {"base_result_revision": 1, "reviewer_name": "Agente auditor — prueba técnica", "material": "tablero sintético", "finish": "melamina sintética", "notes": "Ensayo automatizado, no revisión industrial. Colocación esquemática aceptada como premisa."}
        if separated:
            candidate = next(item for item in run["result"]["assembly_candidates"] if item["layout"] == "between_sides" and not item["unassigned_part_observation_ids"])
            review["assembly_candidate_id"] = candidate["id"]
        else:
            review.update(scenario_id="scenario-between-sides", confirmed_thickness_mm=18)
        reviewed = call("POST", f"/runs/{run_id}/reviews", json=review)
        items.append(call("POST", f"/runs/{run_id}/library", json={"result_revision": reviewed["result_revision"], "label": "Auditoría proveedor " + filename, "embedding_mode": "openai"}))
    call("POST", f"/runs/{run_id}/similarity", json={"result_revision": 2, "mode": "semantic", "limit": 10})
    call("POST", f"/runs/{run_id}/library", json={"result_revision": 2, "label": "Auditoría proveedor repetición", "embedding_mode": "openai"})
    if separated:
        assert items[0]["descriptor_fingerprint"] == items[2]["descriptor_fingerprint"], "IDs/translation changed semantic fingerprint"
        assert items[0]["descriptor_fingerprint"] != items[3]["descriptor_fingerprint"], "Thickness missing from semantic fingerprint"
        assert items[0]["descriptor"]["dimensions"] == items[3]["descriptor"]["dimensions"], "Thickness control must preserve assembly envelope"
        assert "inspeccionar_pieza" in events.text and "entregar_candidato_montaje" in events.text, "Real parts tool sequence missing"
        call("POST", "/library/groups", json={"mode": "semantic", "threshold": 0.8})
        evidence["assertions"] = {"identifier_translation_invariance": True, "thickness_sensitivity_same_envelope": True, "real_parts_tool_sequence": True}
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
