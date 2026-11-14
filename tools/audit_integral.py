"""Run reproducible integral HTTP acceptance against a local or remote Vexplorer service.

Basic credentials are read only from VEXPLORER_QA_USERNAME / VEXPLORER_QA_PASSWORD
or interactive input. They are never accepted as command-line arguments or written to
the JSON report.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pymupdf


class AcceptanceFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditConfig:
    base_url: str
    output: Path
    fixture: Path
    username: str
    password: str
    origin: str | None
    dwg: Path | None = None
    request_timeout_s: float = 30.0
    poll_timeout_s: float = 90.0


class IntegralAudit:
    def __init__(self, config: AuditConfig) -> None:
        self.config = config
        self.qa_id = f"qa-integral-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        headers = {"User-Agent": "Vexplorer-integral-acceptance/1"}
        if config.origin:
            headers["Origin"] = config.origin
        self.client = httpx.Client(
            base_url=config.base_url.rstrip("/") + "/",
            auth=httpx.BasicAuth(config.username, config.password),
            headers=headers,
            timeout=config.request_timeout_s,
            follow_redirects=False,
        )
        self.report: dict[str, Any] = {
            "schema_version": "1.0.0",
            "qa_label": self.qa_id,
            "started_at": datetime.now(UTC).isoformat(),
            "base_url": config.base_url,
            "fixture": config.fixture.name,
            "optional_dwg": config.dwg.name if config.dwg else None,
            "checks": [],
            "resources": {},
            "status": "running",
        }

    def close(self) -> None:
        self.client.close()

    def check(self, check_id: str, condition: bool, detail: str, **evidence: Any) -> None:
        item = {
            "id": check_id,
            "status": "PASS" if condition else "FAIL",
            "detail": detail,
            "evidence": evidence,
        }
        self.report["checks"].append(item)
        if not condition:
            raise AcceptanceFailure(f"{check_id}: {detail}")

    @staticmethod
    def _error_code(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return str(error.get("code")) if error.get("code") else None
        detail = payload.get("detail") if isinstance(payload, dict) else None
        return str(detail) if isinstance(detail, str) else None

    def data(self, response: httpx.Response, expected: int) -> Any:
        if response.status_code != expected:
            raise AcceptanceFailure(
                f"HTTP {response.request.method} {response.request.url.path} returned "
                f"{response.status_code}, expected {expected}, code={self._error_code(response)}"
            )
        payload = response.json()
        if not isinstance(payload, dict) or "data" not in payload:
            raise AcceptanceFailure(f"invalid response envelope for {response.request.url.path}")
        return payload["data"]

    def upload(self, filename: str, content: bytes, media_type: str) -> dict[str, Any]:
        return self.data(
            self.client.post(
                "api/v1/documents",
                files={"file": (filename, content, media_type)},
            ),
            201,
        )

    def poll_job(self, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.poll_timeout_s
        while time.monotonic() < deadline:
            job = self.data(self.client.get(f"api/v1/jobs/{job_id}"), 200)
            if job["state"] in {"succeeded", "failed", "interrupted"}:
                return job
            time.sleep(0.15)
        raise AcceptanceFailure(f"job {job_id} did not finish within timeout")

    def submit_general_job(self, document_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        submitted = self.data(
            self.client.post(
                "api/v1/jobs",
                json={
                    "document_id": document_id,
                    "mode": "geometry_only",
                    "input_kind": "general_furniture",
                },
                headers={"Idempotency-Key": f"{self.qa_id}-general-job"},
            ),
            202,
        )
        terminal = self.poll_job(submitted["id"])
        self.check(
            "durable_general_job",
            terminal["state"] == "succeeded" and bool(terminal.get("run_id")),
            "The generic geometry run completed through the durable job API.",
            job_id=submitted["id"],
            state=terminal["state"],
            run_id=terminal.get("run_id"),
        )
        run_id = terminal["run_id"]
        run = self.data(self.client.get(f"api/v1/runs/{run_id}"), 200)
        ledger = self.data(self.client.get(f"api/v1/runs/{run_id}/ledger"), 200)
        return terminal, run, ledger


def _vector_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=300, height=140)
    page.draw_rect((20, 20, 220, 110))
    page.insert_text((24, 45), "DO NOT SCALE DRAWING — QA")
    payload = document.tobytes()
    document.close()
    return payload


def _raster_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=120, height=100)
    ppm = b"P6\n2 2\n255\n" + bytes((20, 90, 160)) * 4
    page.insert_image(page.rect, stream=ppm)
    payload = document.tobytes()
    document.close()
    return payload


def _contour_basis(ledger: dict[str, Any]) -> dict[str, Any]:
    observations = ledger.get("observations", [])
    evidence = ledger.get("evidence", [])
    for contour in ledger.get("contours", []):
        points = contour.get("points_mm")
        if not points:
            continue
        xs = [float(item["x"]) for item in points]
        ys = [float(item["y"]) for item in points]
        span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
        if span_x <= 0 or span_y <= 0:
            continue
        entity_ids = tuple(contour.get("source_entity_ids", []))
        observation_ids = tuple(
            item["id"] for item in observations if contour["id"] in item.get("contour_ids", [])
        )
        evidence_ids = tuple(
            item["id"]
            for item in evidence
            if set(item.get("source_entity_ids", [])) & set(entity_ids)
        )
        return {
            "contour_id": contour["id"],
            "view_id": contour["view_id"],
            "entity_ids": entity_ids,
            "observation_ids": observation_ids,
            "evidence_ids": evidence_ids,
            "length_mm": span_x,
            "width_mm": span_y,
        }
    raise AcceptanceFailure("public fixture did not yield a metric two-axis contour")


def _manual_proposal(
    *, drawing_id: str, ledger_revision: str, basis: dict[str, Any], qa_id: str,
) -> dict[str, Any]:
    contour_id = basis["contour_id"]
    return {
        "schema_version": "0.6.0",
        "id": f"{qa_id}-proposal",
        "drawing_id": drawing_id,
        "ledger_revision": ledger_revision,
        "proposal_origin": "human",
        "bindings": [
            {"id": "qa-length", "operation": "copy", "operand_refs": [f"measurement:contour:{contour_id}:span-x"]},
            {"id": "qa-width", "operation": "copy", "operand_refs": [f"measurement:contour:{contour_id}:span-y"]},
        ],
        "components": [{
            "id": "qa-panel-proposed",
            "label": "QA panel proposal",
            "kind": "panel",
            "role": "unknown",
            "length_binding_id": "qa-length",
            "width_binding_id": "qa-width",
            "thickness_binding_id": None,
            "quantity": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
            "premise_ids": ["qa-premise"],
            "source_view_ids": [basis["view_id"]],
            "source_observation_ids": list(basis["observation_ids"]),
            "source_contour_ids": [contour_id],
            "source_evidence_ids": list(basis["evidence_ids"]),
            "source_dimension_ids": [],
            "source_document_refs": [],
            "assumptions": ["QA semantic assignment; not manufacturing authority."],
            "unknown_fields": ["thickness", "quantity", "material", "finish", "placement"],
        }],
        "premises": [{
            "id": "qa-premise",
            "description": "The selected contour may represent one reviewable panel.",
            "required": True,
            "blocking": True,
        }],
        "assumptions": ["QA acceptance proposal; explicitly synthetic and revisable."],
    }


def _confirmed_value(value: float, field: str) -> dict[str, Any]:
    return {
        "value_mm": value,
        "unit": "mm",
        "state": "confirmed",
        "dependency_refs": [f"human:qa:{field}"],
        "evidence_ids": [],
        "dimension_ids": [],
    }


def _confirmed_text(value: str, field: str) -> dict[str, Any]:
    return {
        "value": value,
        "state": "confirmed",
        "dependency_refs": [f"human:qa:{field}"],
        "evidence_ids": [],
    }


def _review_body(
    *,
    proposal_revision: int,
    base_review_revision: int,
    source_component_id: str,
    result_component_id: str,
    basis: dict[str, Any],
    thickness_mm: float,
    component_quantity: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "base_proposal_revision": proposal_revision,
        "base_review_revision": base_review_revision,
        "reviewer_name": "qa-client-claim",
        "reason": reason,
        "operations": [{
            "kind": "replace",
            "source_component_ids": [source_component_id],
            "result_component_ids": [result_component_id],
            "reason": reason,
        }],
        "components": [{
            "id": result_component_id,
            "label": "QA confirmed panel",
            "kind": "panel",
            "role": "qa_panel",
            "length": _confirmed_value(basis["length_mm"], "length"),
            "width": _confirmed_value(basis["width_mm"], "width"),
            "thickness": _confirmed_value(thickness_mm, "thickness"),
            "quantity": {
                "value": component_quantity,
                "state": "confirmed",
                "dependency_refs": ["human:qa:quantity"],
                "evidence_ids": [],
            },
            "material": _confirmed_text("QA_SYNTHETIC_BOARD", "material"),
            "finish": _confirmed_text("QA_SYNTHETIC_FINISH", "finish"),
            "replaces_component_ids": [source_component_id],
            "source_view_ids": [basis["view_id"]],
            "source_observation_ids": list(basis["observation_ids"]),
            "source_contour_ids": [basis["contour_id"]],
            "source_evidence_ids": list(basis["evidence_ids"]),
            "source_dimension_ids": [],
            "source_document_refs": [],
            "assumptions": ["QA human confirmation for acceptance only."],
            "unknown_fields": [],
        }],
        "furniture_quantity": {
            "value": 1,
            "state": "confirmed",
            "dependency_refs": ["human:qa:furniture-quantity"],
            "evidence_ids": [],
        },
    }


def _canonical_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _artifact_hashes(audit: IntegralAudit, run_id: str, derived: dict[str, Any]) -> dict[str, str]:
    package = derived["package"]
    proposal_revision = package["proposal_revision"]
    review_revision = package["review_revision"]
    values: dict[str, str] = {}
    for item in package["artifacts"]:
        response = audit.client.get(
            f"api/v1/runs/{run_id}/general/artifacts/{item['id']}",
            params={"proposal_revision": proposal_revision, "review_revision": review_revision},
        )
        if response.status_code != 200:
            raise AcceptanceFailure(f"artifact {item['id']} returned HTTP {response.status_code}")
        values[item["id"]] = sha256(response.content).hexdigest()
    return values


def _synthetic_history_record(
    *, qa_id: str, username: str, target: dict[str, Any],
) -> dict[str, Any]:
    return {
        "record_id": f"{qa_id}-history",
        "project_id": f"{qa_id}-project",
        "revision": "qa-r1",
        "family": target.get("family") or "qa_general_furniture",
        "area_mm2": target.get("area_mm2"),
        "length_mm": target.get("length_mm"),
        "volume_mm3": target.get("volume_mm3"),
        "quantity": target.get("quantity"),
        "material": target.get("material"),
        "finish": target.get("finish"),
        "currency": "EUR",
        "actual_cost": 350.0,
        "cost_basis": "budget",
        "manufacturing_hours": 10.0,
        "origin": "synthetic",
        "provenance": {
            "source": f"QA_SYNTHETIC integral acceptance {qa_id}",
            "source_date": datetime.now(UTC).date().isoformat(),
            "imported_by": username,
            "notes": "Synthetic QA data; never use as commercial history.",
        },
        "concepts": [
            {
                "concept_id": "qa-material",
                "kind": "material",
                "driver": "area",
                "cost": 200.0,
                "hours": 2.0,
                "material": target.get("material") or "QA_SYNTHETIC_BOARD",
            },
            {
                "concept_id": "qa-labor",
                "kind": "labor",
                "driver": "item",
                "cost": 150.0,
                "hours": 8.0,
            },
        ],
        "components": [],
        "included_scope": ["labor", "material"],
        "cost_scope": ["material", "labor"],
        "hours_scope": ["material", "labor"],
    }


def run_integral_acceptance(config: AuditConfig) -> dict[str, Any]:
    audit = IntegralAudit(config)
    try:
        session = audit.data(audit.client.get("api/v1/session"), 200)
        environment = session.get("environment")
        with httpx.Client(
            base_url=config.base_url.rstrip("/") + "/",
            headers={"Origin": config.origin} if config.origin else None,
            timeout=config.request_timeout_s,
        ) as unauthenticated:
            denied = unauthenticated.get("api/v1/config")
        auth_enforced = denied.status_code == 401
        audit.report["checks"].append({
            "id": "negative_auth_scope",
            "status": "PASS" if auth_enforced else "SKIP",
            "detail": (
                "Unauthenticated business request returned 401."
                if auth_enforced else "Local environment does not enforce Basic auth; production must return 401."
            ),
            "evidence": {"environment": environment, "http_status": denied.status_code},
        })
        if environment == "production" and not auth_enforced:
            raise AcceptanceFailure("negative_auth_scope: production did not reject unauthenticated request")
        audit.check(
            "authenticated_session",
            bool(session.get("authenticated")) == (environment == "production")
            and (environment != "production" or session.get("username") == config.username),
            "Authenticated session state matches the server environment.",
            environment=environment,
            username=session.get("username"),
        )

        vector = audit.upload(f"{audit.qa_id}-vector.pdf", _vector_pdf(), "application/pdf")
        vector_child = audit.data(
            audit.client.post(
                f"api/v1/documents/{vector['document_id']}/pages/1/select",
                json={
                    "mm_per_pdf_point": 0.5,
                    "confirmed_by": config.username,
                    "reason": "QA explicit scale confirmation; source says DO NOT SCALE",
                },
            ),
            200,
        )
        audit.check(
            "vector_pdf_scale_provenance",
            vector_child["source"]["unit"] == "mm"
            and vector_child["artifacts"]["normalized_dxf"]["source_page"] == 1
            and "scale_conflicts_with_document_note:page=1:do_not_scale"
            in vector_child["ingestion"]["warnings"],
            "Scaled vector PDF child preserves page, actor provenance and DO NOT SCALE conflict.",
            parent_document_id=vector["document_id"],
            child_document_id=vector_child["document_id"],
            warnings=vector_child["ingestion"]["warnings"],
        )

        raster = audit.upload(f"{audit.qa_id}-raster.pdf", _raster_pdf(), "application/pdf")
        raster_child = audit.data(
            audit.client.post(
                f"api/v1/documents/{raster['document_id']}/pages/1/select",
                json={
                    "confirmed_by": config.username,
                    "reason": "QA raster manual visual review",
                },
            ),
            200,
        )
        raster_preview = audit.client.get(raster_child["artifacts"]["preview"]["url"])
        audit.check(
            "raster_pdf_manual_path",
            raster_child["ingestion"]["state"] == "needs_review"
            and raster_child["artifacts"]["normalized_dxf"] is None
            and raster_child["ingestion"]["capabilities"]["geometry_analysis"] is False
            and raster_preview.status_code == 200
            and raster_preview.headers.get("content-type", "").startswith("image/png"),
            "Raster PDF remains visual/manual and exposes no CAD geometry.",
            parent_document_id=raster["document_id"],
            child_document_id=raster_child["document_id"],
        )

        fixture_bytes = config.fixture.read_bytes()
        document = audit.upload(config.fixture.name, fixture_bytes, "application/dxf")
        terminal, run_payload, ledger = audit.submit_general_job(document["document_id"])
        run_id = terminal["run_id"]
        run = run_payload["run"]
        basis = _contour_basis(ledger)
        proposal = _manual_proposal(
            drawing_id=ledger["drawing_id"],
            ledger_revision=run["candidate_revision"],
            basis=basis,
            qa_id=audit.qa_id,
        )
        proposal_body = {"mode": "manual", "base_proposal_revision": 0, "proposal": proposal}
        proposed = audit.data(
            audit.client.post(f"api/v1/runs/{run_id}/general/proposals", json=proposal_body),
            201,
        )
        audit.check(
            "manual_general_proposal",
            proposed["proposal_revision"] == 1
            and proposed["draft"]["components"][0]["length"]["value_mm"] == basis["length_mm"]
            and proposed["draft"]["components"][0]["width"]["value_mm"] == basis["width_mm"],
            "Manual proposal binds deterministic contour measurements as hypotheses.",
            run_id=run_id,
            proposal_revision=proposed["proposal_revision"],
        )
        stale_proposal = audit.client.post(
            f"api/v1/runs/{run_id}/general/proposals", json=proposal_body
        )
        audit.check(
            "negative_stale_proposal_revision",
            stale_proposal.status_code == 409,
            "A stale base proposal revision is rejected.",
            http_status=stale_proposal.status_code,
            error_code=audit._error_code(stale_proposal),
        )

        reason1 = "QA review 1 confirms dimensions, quantity, material and finish"
        review1_body = _review_body(
            proposal_revision=1,
            base_review_revision=0,
            source_component_id="qa-panel-proposed",
            result_component_id="qa-panel-reviewed-r1",
            basis=basis,
            thickness_mm=18.0,
            component_quantity=2,
            reason=reason1,
        )
        review1 = audit.data(
            audit.client.post(f"api/v1/runs/{run_id}/general/reviews", json=review1_body),
            200,
        )
        reviewed1 = review1["review"]
        expected_reviewer = config.username if environment == "production" else "qa-client-claim"
        audit.check(
            "confirmed_review_reason_fields",
            reviewed1["review_revision"] == 1
            and reviewed1["reason"] == reason1
            and reviewed1["reviewer_name"] == expected_reviewer
            and reviewed1["components"][0]["material"]["value"] == "QA_SYNTHETIC_BOARD",
            "First review records reason, reviewer and confirmed fields.",
            proposal_revision=review1["proposal_revision"],
            review_revision=reviewed1["review_revision"],
            reviewer_name=reviewed1["reviewer_name"],
        )
        audit.report["checks"].append({
            "id": "authoritative_actor_override",
            "status": "PASS" if environment == "production" else "SKIP",
            "detail": (
                "Authenticated server actor replaced the client reviewer claim."
                if environment == "production"
                else "Local mode has no authenticated actor; production must replace the client claim."
            ),
            "evidence": {"reviewer_name": reviewed1["reviewer_name"]},
        })
        stale_review = audit.client.post(
            f"api/v1/runs/{run_id}/general/reviews", json=review1_body
        )
        audit.check(
            "negative_stale_review_revision",
            stale_review.status_code == 409,
            "A stale base review revision is rejected.",
            http_status=stale_review.status_code,
            error_code=audit._error_code(stale_review),
        )

        derived1 = audit.data(
            audit.client.get(
                f"api/v1/runs/{run_id}/general/derived",
                params={"proposal_revision": 1, "review_revision": 1},
            ),
            200,
        )
        derived1_hash = _canonical_hash(derived1)
        artifact_hashes1 = _artifact_hashes(audit, run_id, derived1)
        first_artifact_id = derived1["package"]["artifacts"][0]["id"]
        first_artifact_path = (
            f"api/v1/runs/{run_id}/general/artifacts/{first_artifact_id}"
            "?proposal_revision=1&review_revision=1"
        )
        with httpx.Client(
            base_url=config.base_url.rstrip("/") + "/",
            headers={"Origin": config.origin} if config.origin else None,
            timeout=config.request_timeout_s,
        ) as unauthenticated:
            unauthenticated_artifact = unauthenticated.get(first_artifact_path)
        artifact_auth_enforced = unauthenticated_artifact.status_code == 401
        audit.report["checks"].append({
            "id": "negative_artifact_auth_scope",
            "status": "PASS" if artifact_auth_enforced else "SKIP",
            "detail": (
                "Unauthenticated exact-revision artifact request returned 401."
                if artifact_auth_enforced
                else "Local environment does not enforce artifact auth; production must return 401."
            ),
            "evidence": {"environment": environment, "http_status": unauthenticated_artifact.status_code},
        })
        if environment == "production" and not artifact_auth_enforced:
            raise AcceptanceFailure(
                "negative_artifact_auth_scope: production exposed an artifact without authentication"
            )
        reason2 = "QA review 2 changes thickness and quantity while preserving revision 1"
        review2_body = _review_body(
            proposal_revision=1,
            base_review_revision=1,
            source_component_id="qa-panel-reviewed-r1",
            result_component_id="qa-panel-reviewed-r2",
            basis=basis,
            thickness_mm=19.0,
            component_quantity=3,
            reason=reason2,
        )
        review2 = audit.data(
            audit.client.post(f"api/v1/runs/{run_id}/general/reviews", json=review2_body),
            200,
        )
        derived1_after = audit.data(
            audit.client.get(
                f"api/v1/runs/{run_id}/general/derived",
                params={"proposal_revision": 1, "review_revision": 1},
            ),
            200,
        )
        artifact_hashes1_after = _artifact_hashes(audit, run_id, derived1_after)
        audit.check(
            "immutable_exact_revision_artifacts",
            review2["review_revision"] == 2
            and _canonical_hash(derived1_after) == derived1_hash
            and artifact_hashes1_after == artifact_hashes1,
            "Revision 1 derived payload and artifact bytes remain exact after review 2.",
            review2_revision=review2["review_revision"],
            revision1_hash=derived1_hash,
            artifact_hashes=artifact_hashes1,
        )

        target = dict(derived1["historical_target"])
        target["currency"] = "EUR"
        target["required_cost_scope"] = ["material", "labor"]
        target["required_hours_scope"] = ["material", "labor"]
        record = _synthetic_history_record(
            qa_id=audit.qa_id, username=config.username, target=target
        )
        imported = audit.data(
            audit.client.post("api/v1/history/import/json", json={"records": [record]}),
            200,
        )
        audit.check(
            "synthetic_history_import",
            imported["accepted"] == 1 and imported["rejected"] == 0,
            "Synthetic QA history is explicitly labeled and imported.",
            import_id=imported["import_id"],
            record_id=record["record_id"],
        )
        compared = audit.data(
            audit.client.post(
                "api/v1/history/comparables",
                json={
                    "target": target,
                    "limit": 5,
                    "retrieval_method": "attribute",
                    "include_synthetic": True,
                },
            ),
            200,
        )
        comparable_ids = [item["record"]["record_id"] for item in compared["items"]]
        audit.check(
            "synthetic_comparable_provenance",
            record["record_id"] in comparable_ids
            and all(item["record"]["origin"] == "synthetic" for item in compared["items"] if item["record"]["record_id"] == record["record_id"]),
            "Comparable retrieval includes the synthetic QA record only when explicitly requested.",
            comparable_ids=comparable_ids,
        )
        estimate = audit.data(
            audit.client.post(
                "api/v1/history/estimate",
                json={
                    "target": target,
                    "comparable_ids": [record["record_id"]],
                    "include_synthetic": True,
                },
            ),
            200,
        )
        audit.check(
            "historical_estimate_math_provenance",
            abs(float(estimate["cost_subtotal"]) - 350.0) < 1e-9
            and abs(float(estimate["manufacturing_hours"]) - 10.0) < 1e-9
            and estimate["result_provenance"][0]["record_id"] == record["record_id"]
            and estimate["result_provenance"][0]["origin"] == "synthetic",
            "Estimate math is independently known and provenance remains synthetic.",
            cost_subtotal=estimate["cost_subtotal"],
            manufacturing_hours=estimate["manufacturing_hours"],
            result_provenance=estimate["result_provenance"],
        )

        if config.dwg is not None:
            dwg = audit.upload(config.dwg.name, config.dwg.read_bytes(), "application/acad")
            audit.check(
                "optional_real_dwg",
                dwg["source"]["format"] == "dwg"
                and dwg["artifacts"]["normalized_dxf"] is not None,
                "Optional DWG was converted through the configured server provider.",
                document_id=dwg["document_id"],
                warnings=dwg["ingestion"]["warnings"],
            )
        else:
            audit.report["checks"].append({
                "id": "optional_real_dwg",
                "status": "SKIP",
                "detail": "No --dwg sample supplied.",
                "evidence": {},
            })

        audit.report["resources"] = {
            "vector_pdf_parent": vector["document_id"],
            "vector_pdf_child": vector_child["document_id"],
            "raster_pdf_parent": raster["document_id"],
            "raster_pdf_child": raster_child["document_id"],
            "general_document": document["document_id"],
            "general_job": terminal["id"],
            "general_run": run_id,
            "history_record": record["record_id"],
        }
        audit.report["status"] = "passed"
    except Exception as exc:
        audit.report["status"] = "failed"
        audit.report["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        raise
    finally:
        audit.report["finished_at"] = datetime.now(UTC).isoformat()
        audit.close()
        _write_json(config.output, audit.report)
    return audit.report


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("base URL must be absolute HTTP(S)")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("base URL cannot contain credentials, query or fragment")
    return value.rstrip("/")


def _credentials() -> tuple[str, str]:
    username = os.getenv("VEXPLORER_QA_USERNAME") or input("Basic username: ").strip()
    password = os.getenv("VEXPLORER_QA_PASSWORD") or getpass("Basic password: ")
    if not username or not password:
        raise SystemExit("Basic credentials are required via environment or interactive input")
    return username, password


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", type=_validated_base_url, default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=root / ".runtime" / "integral-acceptance" / "report.json")
    parser.add_argument("--fixture", type=Path, default=root / "data" / "planos_demo" / "piezas_completo.dxf")
    parser.add_argument("--dwg", type=Path, default=None)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--poll-timeout", type=float, default=90.0)
    args = parser.parse_args()
    if not args.fixture.is_file():
        parser.error("--fixture must be an existing public DXF")
    if args.dwg is not None and (not args.dwg.is_file() or args.dwg.suffix.lower() != ".dwg"):
        parser.error("--dwg must be an existing DWG")
    if args.request_timeout <= 0 or args.poll_timeout <= 0:
        parser.error("timeouts must be positive")
    username, password = _credentials()
    try:
        result = run_integral_acceptance(AuditConfig(
            base_url=args.base_url,
            output=args.output,
            fixture=args.fixture.resolve(),
            username=username,
            password=password,
            origin=os.getenv("VEXPLORER_QA_ORIGIN"),
            dwg=args.dwg.resolve() if args.dwg else None,
            request_timeout_s=args.request_timeout,
            poll_timeout_s=args.poll_timeout,
        ))
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "failure_type": type(exc).__name__,
            "output": str(args.output.resolve()),
        }, ensure_ascii=False))
        raise SystemExit(1) from None
    print(json.dumps({
        "status": result["status"],
        "output": str(args.output.resolve()),
        "check_count": len(result["checks"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
