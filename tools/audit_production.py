"""Run the private-production acceptance path without external providers."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any

from fastapi.testclient import TestClient


@dataclass(frozen=True)
class AcceptanceConfig:
    data_dir: Path
    report_path: Path
    catalog_path: Path
    fixture_path: Path
    conflict_fixture_path: Path
    username: str = "acceptance-auditor"
    password: str | None = None
    poll_timeout_s: float = 30.0


class _RejectingProvider:
    """Records an error if geometry-only acceptance crosses the paid boundary."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def respond(self, *args: object, **kwargs: object) -> object:
        self.calls.append("respond")
        raise AssertionError("offline acceptance attempted a provider call")


def _accept_all(program: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "target_kind": "program",
            "target_id": program["id"],
            "action": "accept",
            "reason": "Hipótesis seleccionada por la aceptación operativa",
        },
        *(
            {
                "target_kind": "component",
                "target_id": item["id"],
                "action": "accept",
                "reason": "Componente revisado por el usuario autenticado",
            }
            for item in program["components"]
        ),
        *(
            {
                "target_kind": "premise",
                "target_id": item["id"],
                "action": "accept",
                "reason": "Premisa revisada por el usuario autenticado",
            }
            for item in program["premises"]
        ),
    ]


def _response_data(response, expected_status: int) -> Any:
    if response.status_code != expected_status:
        raise AssertionError(
            f"HTTP {response.status_code}, expected {expected_status}: {response.text}"
        )
    return response.json()["data"]


def _poll_job(client: TestClient, auth: tuple[str, str], job_id: str, timeout_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = _response_data(client.get(f"/api/v1/jobs/{job_id}", auth=auth), 200)
        if job["state"] in {"succeeded", "failed", "interrupted"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not become terminal within {timeout_s}s")


def _submit_table(
    client: TestClient,
    auth: tuple[str, str],
    fixture: Path,
    *,
    key: str,
    timeout_s: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with fixture.open("rb") as stream:
        document = _response_data(
            client.post(
                "/api/v1/documents",
                files={"file": ("source.dxf", stream, "application/dxf")},
                auth=auth,
            ),
            201,
        )
    submitted = _response_data(
        client.post(
            "/api/v1/jobs",
            json={
                "document_id": document["document_id"],
                "mode": "geometry_only",
                "input_kind": "mounted_orthographic_views",
                "table_profile": "rectangular_table_v1",
                "proposal_mode": "catalog_baseline",
                "table_template_id": "side_supports_v1",
            },
            auth=auth,
            headers={"Idempotency-Key": f"{key}-{document['document_id']}"},
        ),
        202,
    )
    terminal = _poll_job(client, auth, submitted["id"], timeout_s)
    if terminal["state"] != "succeeded":
        raise AssertionError(f"job failed: {terminal}")
    run = _response_data(client.get(f"/api/v1/runs/{terminal['run_id']}", auth=auth), 200)
    return terminal, run


def _write_report(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Informe de aceptación local de producción",
        "",
        "Modo: `geometry_only`, sin llamadas a proveedores externos.",
        "",
        "## Comprobaciones",
        "",
        "| Comprobación | Estado | Evidencia |",
        "|---|---|---|",
    ]
    for item in result.get("checks", []):
        detail = str(item.get("detail", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{item['id']}` | {item['status']} | {detail} |")
    lines.extend((
        "",
        "## Identificadores",
        "",
        f"- Job: `{result.get('job', {}).get('id', 'no disponible')}`",
        f"- Run: `{result.get('job', {}).get('run_id', 'no disponible')}`",
        f"- Revisión: `{result.get('review', {}).get('result_revision', 'no disponible')}`",
        f"- Catálogo: `{result.get('estimate', {}).get('catalog_version', 'no disponible')}`",
        f"- Coste completo: `{result.get('estimate', {}).get('grand_total_eur', 'no disponible')} EUR`",
        f"- Horas: `{result.get('estimate', {}).get('total_hours', 'no disponible')}`",
        f"- Precio provisional: `{result.get('estimate', {}).get('provisional_sale_price_eur', 'no disponible')} EUR`",
        "",
        "## Límites",
        "",
        "El catálogo de esta aceptación simula una exportación ERP para probar la configuración; no contiene tarifas comerciales de la empresa. El fixture no acredita precisión industrial, TLS remoto ni aceptación de un técnico.",
    ))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_production_acceptance(config: AcceptanceConfig) -> dict[str, Any]:
    """Exercise auth, durable work, review, artifacts, cost, export and restart."""
    from backend.app.main import create_app
    from backend.app.operacion.auth import hash_password

    config.data_dir.mkdir(parents=True, exist_ok=True)
    password = config.password or secrets.token_urlsafe(24)
    users_path = config.data_dir / "acceptance-users.json"
    users_path.write_text(
        json.dumps({config.username: hash_password(password, salt=b"acceptance-salt!")}),
        encoding="utf-8",
    )
    previous = {key: os.environ.get(key) for key in (
        "VEXPLORER_ENV",
        "VEXPLORER_USERS_FILE",
        "VEXPLORER_ALLOWED_ORIGINS",
        "VEXPLORER_COST_CATALOG",
        "OPENAI_API_KEY",
    )}
    os.environ.update({
        "VEXPLORER_ENV": "production",
        "VEXPLORER_USERS_FILE": str(users_path),
        "VEXPLORER_ALLOWED_ORIGINS": "https://acceptance.invalid",
        "VEXPLORER_COST_CATALOG": str(config.catalog_path.resolve()),
    })
    os.environ.pop("OPENAI_API_KEY", None)
    provider = _RejectingProvider()
    result: dict[str, Any] = {"checks": [], "provider_calls": provider.calls}

    def check(check_id: str, condition: bool, detail: str) -> None:
        result["checks"].append({
            "id": check_id,
            "status": "PASS" if condition else "FAIL",
            "detail": detail,
        })
        if not condition:
            raise AssertionError(f"{check_id}: {detail}")

    auth = (config.username, password)
    try:
        app = create_app(data_dir=config.data_dir, frontend_dir=config.data_dir / "no-frontend", agent_provider=provider)
        with TestClient(app) as client:
            check(
                "authentication_required",
                client.get("/api/v1/config").status_code == 401,
                "Una ruta de negocio sin Basic devuelve 401.",
            )
            session = _response_data(client.get("/api/v1/session", auth=auth), 200)
            check(
                "offline_geometry_only",
                session["username"] == config.username and not provider.calls,
                "La sesión autenticada usa geometry_only y el proveedor no recibe llamadas.",
            )
            job, run = _submit_table(
                client, auth, config.fixture_path, key="acceptance-complete-v1", timeout_s=config.poll_timeout_s
            )
            result["job"] = job
            initial = run["result"]
            program = initial["table_programs"][0]
            review = _response_data(
                client.post(
                    f"/api/v1/runs/{job['run_id']}/reviews",
                    json={
                        "base_result_revision": initial["result_revision"],
                        "reviewer_name": "spoofed-client-name",
                        "table_program_id": program["id"],
                        "table_decisions": _accept_all(program),
                        "notes": "Aceptación local; no certifica fabricación",
                    },
                    auth=auth,
                    headers={"Idempotency-Key": "acceptance-review-v1"},
                ),
                201,
            )
            result["review"] = review
            check(
                "named_reviewer_authority",
                review["review"]["reviewer_name"] == config.username,
                "El servidor sustituyó el nombre enviado por el usuario autenticado.",
            )
            drawings = _response_data(
                client.post(
                    f"/api/v1/runs/{job['run_id']}/table-drawings",
                    json={"result_revision": review["result_revision"]},
                    auth=auth,
                ),
                201,
            )
            first_artifact = drawings["sheets"][0]["formats"][0]["url"]
            unauthorised_artifact = client.get(first_artifact)
            check(
                "artifact_authority_required",
                unauthorised_artifact.status_code == 401,
                "Los artefactos derivados también requieren autoridad.",
            )
            material_overrides = {
                component["id"]: "solid-real"
                for component in review["evaluated_table_program"]["components"]
                if component["role"] != "tabletop"
            }
            estimate = _response_data(
                client.post(
                    f"/api/v1/runs/{job['run_id']}/table-costs",
                    json={
                        "result_revision": review["result_revision"],
                        "scope": {
                            "material_tariff_id": "board-real",
                            "component_material_tariff_ids": material_overrides,
                            "edge_scope": "all_exposed",
                            "edge_tariff_id": "edge-real",
                            "operation_tariff_ids": ["cut-real"],
                            "operation_hours_by_tariff": {"cut-real": 2.5},
                            "labor_tariff_id": "labor-real",
                            "labor_hours": 3,
                            "finish_tariff_id": "finish-real",
                            "finish_quantity_m2": 1.5,
                            "provisional_margin_percent": 20,
                        },
                    },
                    auth=auth,
                ),
                201,
            )
            result["estimate"] = estimate
            exported = client.get(
                f"/api/v1/runs/{job['run_id']}/exports",
                params={"format": "json"},
                auth=auth,
            )
            if exported.status_code != 200:
                raise AssertionError(f"export failed: {exported.status_code} {exported.text}")
            bundle = exported.json()
            result["export"] = bundle
            check(
                "review_drawings_cost_export",
                review["state"] == "completed"
                and all(sheet["status"] == "ready" for sheet in drawings["sheets"])
                and estimate["total_state"] == "complete"
                and estimate["synthetic"] is False
                and bundle.get("estimate") == estimate,
                "La revisión completa produce planos, coste no-demo completo y exportación coherente.",
            )
            conflict_job, conflict_run = _submit_table(
                client,
                auth,
                config.conflict_fixture_path,
                key="acceptance-conflict-v1",
                timeout_s=config.poll_timeout_s,
            )
            conflict_initial = conflict_run["result"]
            conflict_program = conflict_initial["table_programs"][0]
            conflict = _response_data(
                client.post(
                    f"/api/v1/runs/{conflict_job['run_id']}/reviews",
                    json={
                        "base_result_revision": conflict_initial["result_revision"],
                        "reviewer_name": "spoofed-client-name",
                        "table_program_id": conflict_program["id"],
                        "table_decisions": _accept_all(conflict_program),
                        "notes": "El conflicto observado no se corrige sin autoridad métrica",
                    },
                    auth=auth,
                    headers={"Idempotency-Key": "acceptance-conflict-review-v1"},
                ),
                201,
            )
            result["conflict"] = conflict
            conflict_measures = conflict["table_analysis"]["measures"]
            check(
                "dimension_conflict_blocks_completion",
                conflict["state"] == "needs_review"
                and any(item["state"] == "conflict" for item in conflict_measures),
                "Aceptar la hipótesis no borra el conflicto dimensional ni completa el resultado.",
            )
        restarted_app = create_app(
            data_dir=config.data_dir,
            frontend_dir=config.data_dir / "no-frontend",
            agent_provider=provider,
        )
        with TestClient(restarted_app) as restarted:
            durable_job = _response_data(
                restarted.get(f"/api/v1/jobs/{result['job']['id']}", auth=auth), 200
            )
            durable_run = _response_data(
                restarted.get(f"/api/v1/runs/{result['job']['run_id']}", auth=auth), 200
            )
            durable_estimate = _response_data(
                restarted.get(
                    f"/api/v1/runs/{result['job']['run_id']}/table-costs",
                    params={
                        "result_revision": review["result_revision"],
                        "estimate_id": estimate["estimate_id"],
                    },
                    auth=auth,
                ),
                200,
            )
            durable_drawings = _response_data(
                restarted.get(
                    f"/api/v1/runs/{result['job']['run_id']}/table-drawings",
                    params={"result_revision": review["result_revision"]},
                    auth=auth,
                ),
                200,
            )
            result["restart"] = durable_job
            check(
                "durable_job_restart",
                durable_job["state"] == "succeeded"
                and durable_run["result"]["result_revision"] == review["result_revision"]
                and durable_estimate == estimate
                and durable_drawings == drawings,
                "Trabajo, revisión, planos y estimación permanecen en SQLite tras crear otra aplicación.",
            )
        check(
            "provider_boundary_unused",
            not provider.calls,
            "El proveedor inyectado no recibió llamadas.",
        )
        return result
    finally:
        _write_report(config.report_path, result)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=root / ".runtime" / "production" / "data")
    parser.add_argument("--report", type=Path, default=root / ".runtime" / "production" / "acceptance-report.md")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=root / "data" / "planos_demo" / "mesa_demo_001.dxf")
    parser.add_argument("--conflict-fixture", type=Path, default=root / "data" / "planos_demo" / "mesa_demo_004.dxf")
    parser.add_argument("--username", default="acceptance-auditor")
    args = parser.parse_args()
    result = run_production_acceptance(AcceptanceConfig(
        data_dir=args.data_dir,
        report_path=args.report,
        catalog_path=args.catalog,
        fixture_path=args.fixture,
        conflict_fixture_path=args.conflict_fixture,
        username=args.username,
    ))
    print(json.dumps({
        "checks": result["checks"],
        "report": str(args.report.resolve()),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
