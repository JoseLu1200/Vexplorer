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
        return call("POST", "/runs", json={"document_id": document["document_id"], "mode": mode})

    config = call("GET", "/config")
    live = call("GET", f"/runs/{args.reuse_live_run}") if args.reuse_live_run else create_run("estanteria_montada.dxf", "live")
    run_id = live["run"]["id"]
    events = client.get(f"/runs/{run_id}/events")
    evidence["live_events_sse"] = events.text
    evidence["live_run_id"] = run_id
    for filename in ("estanteria_montada.dxf", "mueble_demo_002.dxf", "mueble_demo_004.dxf"):
        run = create_run(filename, "geometry_only")
        run_id = run["run"]["id"]
        reviewed = call("POST", f"/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Agente auditor — prueba técnica", "scenario_id": "scenario-between-sides", "confirmed_thickness_mm": 18, "material": "tablero sintético", "finish": "melamina sintética", "notes": "Ensayo automatizado, no revisión industrial."})
        call("POST", f"/runs/{run_id}/library", json={"result_revision": reviewed["result_revision"], "label": "Auditoría proveedor " + filename, "embedding_mode": "openai"})
    call("POST", f"/runs/{run_id}/similarity", json={"result_revision": 2, "mode": "semantic", "limit": 10})
    call("POST", f"/runs/{run_id}/library", json={"result_revision": 2, "label": "Auditoría proveedor traslado", "embedding_mode": "openai"})
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
