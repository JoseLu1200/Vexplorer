"""Audit the real durable autonomous general-furniture HTTP workflow.

This is an online model acceptance, not a deterministic fixture oracle and not
a replacement for the separate 16-case deterministic evaluation. Basic credentials
come only from VEXPLORER_QA_USERNAME / VEXPLORER_QA_PASSWORD or interactive input;
credentials and provider payloads are never written to the report.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from getpass import getpass
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_JOB_STATES = frozenset({"succeeded", "failed", "interrupted"})


class AcceptanceFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditConfig:
    base_url: str
    fixture: Path
    output: Path
    username: str | None
    password: str | None
    origin: str | None
    public: bool = False
    timeout_s: float = 600.0
    request_timeout_s: float = 60.0
    resume_report: Path | None = None


def _parse_sse_events(body: str) -> tuple[dict[str, Any], ...]:
    events: list[dict[str, Any]] = []
    for block in re.split(r"\r?\n\r?\n", body.strip()):
        if not block.strip():
            continue
        event_type = None
        event_id = None
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("id:"):
                event_id = line[3:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if event_type is None or not data_lines:
            raise AcceptanceFailure("invalid_sse_event")
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as exc:
            raise AcceptanceFailure("invalid_sse_json") from exc
        if not isinstance(data, dict):
            raise AcceptanceFailure("invalid_sse_data")
        if isinstance(data.get("data"), dict) and data.get("event_type") == event_type:
            data = data["data"]
        events.append({"id": event_id, "event_type": event_type, "data": data})
    return tuple(events)


def _walk(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _extract_image_hashes(events: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    values: set[str] = set()
    for event in events:
        for key, value in _walk(event.get("data", {})):
            if not any(token in key.lower() for token in ("visual", "image", "artifact")):
                continue
            candidates = value if isinstance(value, list) else (value,)
            for candidate in candidates:
                if isinstance(candidate, str) and _SHA256.fullmatch(candidate):
                    values.add(candidate)
                elif isinstance(candidate, dict):
                    digest = candidate.get("sha256")
                    if isinstance(digest, str) and _SHA256.fullmatch(digest):
                        values.add(digest)
    return tuple(sorted(values))


def _visual_event_artifacts(
    events: tuple[dict[str, Any], ...]
) -> tuple[dict[str, Any], ...]:
    values = []
    for event in events:
        artifacts = event.get("data", {}).get("visual_artifacts", [])
        if isinstance(artifacts, list):
            values.extend(item for item in artifacts if isinstance(item, dict))
    return tuple(values)


def _assert_no_machine_confirmed(review: dict[str, Any]) -> None:
    if review.get("reviewer_kind") != "machine":
        raise AcceptanceFailure("reviewer_kind_not_machine")
    for key, value in _walk(review):
        if key == "state" and value == "confirmed":
            raise AcceptanceFailure("machine_confirmed_fact")
        if key == "dependency_refs" and isinstance(value, list):
            if any(isinstance(item, str) and item.startswith("human:") for item in value):
                raise AcceptanceFailure("machine_human_provenance")


def _assert_occurrence_authority(review: dict[str, Any]) -> dict[str, int]:
    components = {
        str(item.get("id")): item
        for item in review.get("components", [])
        if isinstance(item, dict) and item.get("id")
    }
    physical_by_component: dict[str, list[dict[str, Any]]] = {}
    for occurrence in review.get("occurrences", []):
        if not isinstance(occurrence, dict):
            raise AcceptanceFailure("invalid_physical_occurrence")
        physical_by_component.setdefault(str(occurrence.get("component_id")), []).append(
            occurrence
        )
    provisional_by_component: dict[str, list[dict[str, Any]]] = {}
    for occurrence in review.get("scenario_occurrences", []):
        if not isinstance(occurrence, dict) or occurrence.get("state") != "provisional":
            raise AcceptanceFailure("invalid_provisional_occurrence")
        provisional_by_component.setdefault(
            str(occurrence.get("component_id")), []
        ).append(occurrence)
    for component_id, occurrences in physical_by_component.items():
        component = components.get(component_id)
        quantity = component.get("quantity", {}) if component else {}
        if quantity.get("state") not in {"observed", "derived"}:
            raise AcceptanceFailure("physical_occurrence_without_authority")
        if quantity.get("value") != len(occurrences):
            raise AcceptanceFailure("physical_occurrence_quantity_mismatch")
        if component_id in provisional_by_component:
            raise AcceptanceFailure("physical_and_provisional_occurrence_overlap")
    for component_id, occurrences in provisional_by_component.items():
        component = components.get(component_id)
        quantity = component.get("quantity", {}) if component else {}
        if quantity.get("state") not in {"hypothesis", "deduced", "estimated"}:
            raise AcceptanceFailure("provisional_occurrence_without_hypothesis")
        if quantity.get("value") != len(occurrences):
            raise AcceptanceFailure("provisional_occurrence_quantity_mismatch")
    return {
        "physical": sum(len(items) for items in physical_by_component.values()),
        "provisional": sum(len(items) for items in provisional_by_component.values()),
    }


def _validate_provisional_exports(
    csv_payload: bytes, svg_payload: bytes
) -> dict[str, Any]:
    try:
        csv_text = csv_payload.decode("utf-8-sig")
        rows = list(csv.DictReader(StringIO(csv_text)))
        svg_text = svg_payload.decode("utf-8")
    except (UnicodeDecodeError, csv.Error) as exc:
        raise AcceptanceFailure("invalid_provisional_export") from exc
    required = {
        "quantity_state",
        "occurrence_status",
        "physical_occurrence_ids",
        "scenario_occurrence_ids",
    }
    headers = set(rows[0]) if rows else set(csv.DictReader(StringIO(csv_text)).fieldnames or ())
    if not required <= headers:
        raise AcceptanceFailure("provisional_csv_headers_missing")
    occurrence_states = [item["occurrence_status"] for item in rows]
    if "confirmed" in occurrence_states or "[confirmed]" in svg_text:
        raise AcceptanceFailure("provisional export contains forged confirmed label")
    if any(item not in {"provisional", "unknown"} for item in occurrence_states):
        raise AcceptanceFailure("invalid_provisional_occurrence_status")
    svg_lower = svg_text.lower()
    if not any(
        marker in svg_lower
        for marker in (
            "schematic; not manufacturing-ready",
            "schematic_unplaced_not_manufacturing_ready",
            "esquema_sin_colocacion_no_fabricacion",
            "no apto para fabricación",
        )
    ):
        raise AcceptanceFailure("schematic_warning_missing")
    if any(item == "provisional" for item in occurrence_states):
        if not any(
            marker in svg_lower
            for marker in ("provisional scenario", "escenario provisional")
        ):
            raise AcceptanceFailure("provisional_svg_label_missing")
        svg_label = "provisional scenario"
    else:
        if rows and not any(
            marker in svg_lower
            for marker in ("no physical occurrence", "sin ocurrencia física")
        ):
            raise AcceptanceFailure("unknown_occurrence_svg_label_missing")
        svg_label = "no physical occurrence" if rows else "empty"
    return {
        "csv_rows": len(rows),
        "csv_occurrence_states": occurrence_states,
        "svg_label": svg_label,
        "csv_sha256": sha256(csv_payload).hexdigest(),
        "svg_sha256": sha256(svg_payload).hexdigest(),
    }


def _validate_history_scenarios(
    value: dict[str, Any],
    run_id: str,
    proposal_revision: int,
    review_revision: int,
) -> dict[str, Any]:
    if (
        value.get("run_id") != run_id
        or value.get("proposal_revision") != proposal_revision
        or value.get("review_revision") != review_revision
    ):
        raise AcceptanceFailure("history_scenario_snapshot_mismatch")
    if value.get("status") not in {"provisional", "not_estimable"}:
        raise AcceptanceFailure("history_scenario_status_invalid")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list):
        raise AcceptanceFailure("history_scenarios_invalid")
    provenance = []
    for scenario in scenarios:
        sources = scenario.get("result_provenance") if isinstance(scenario, dict) else None
        if not isinstance(sources, list) or not sources:
            raise AcceptanceFailure("history_scenario_provenance_missing")
        provenance.extend(item for item in sources if isinstance(item, dict))
    if scenarios and not provenance:
        raise AcceptanceFailure("history_scenario_provenance_missing")
    return {
        "status": value["status"],
        "scenario_count": len(scenarios),
        "numeric_cost_count": sum(
            item.get("cost_subtotal") is not None for item in scenarios
        ),
        "numeric_hours_count": sum(
            item.get("manufacturing_hours") is not None for item in scenarios
        ),
        "provenance_record_ids": sorted(
            {
                str(item["record_id"])
                for item in provenance
                if item.get("record_id") is not None
            }
        ),
        "provenance_origins": sorted(
            {
                str(item["origin"])
                for item in provenance
                if item.get("origin") is not None
            }
        ),
        "missing_data": value.get("missing_data", []),
    }


class AutonomousAudit:
    def __init__(self, config: AuditConfig) -> None:
        self.config = config
        self.qa_id = (
            f"qa-autonomous-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
            f"-{uuid4().hex[:8]}"
        )
        headers = {"User-Agent": "Vexplorer-autonomous-online-acceptance/1"}
        if config.origin:
            headers["Origin"] = config.origin
        client_options: dict[str, Any] = {}
        if not config.public:
            if not config.username or not config.password:
                raise AcceptanceFailure("private_audit_credentials_missing")
            client_options["auth"] = httpx.BasicAuth(config.username, config.password)
        self.client = httpx.Client(
            base_url=config.base_url.rstrip("/") + "/",
            headers=headers,
            timeout=config.request_timeout_s,
            follow_redirects=False,
            **client_options,
        )
        self.report: dict[str, Any] = {
            "schema_version": "1.0.0",
            "audit_kind": "online_autonomous_model_acceptance",
            "scope_note": (
                "Real online proposer/critic execution; separate from and not a "
                "replacement for the 16-case deterministic evaluation."
            ),
            "qa_label": self.qa_id,
            "started_at": datetime.now(UTC).isoformat(),
            "base_url": config.base_url,
            "fixture": config.fixture.name,
            "fixture_sha256": sha256(config.fixture.read_bytes()).hexdigest(),
            "timeout_s": config.timeout_s,
            "access_mode": "public" if config.public else "authenticated",
            "status": "running",
            "checks": [],
            "resources": {},
            "partial_evidence": {},
        }

    def close(self) -> None:
        self.client.close()

    def check(self, check_id: str, condition: bool, detail: str, **evidence: Any) -> None:
        self.report["checks"].append(
            {
                "id": check_id,
                "status": "PASS" if condition else "FAIL",
                "detail": detail,
                "evidence": evidence,
            }
        )
        if not condition:
            raise AcceptanceFailure(f"{check_id}: {detail}")

    def skip(self, check_id: str, detail: str, **evidence: Any) -> None:
        self.report["checks"].append(
            {"id": check_id, "status": "SKIP", "detail": detail, "evidence": evidence}
        )

    @staticmethod
    def _error_code(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if isinstance(error, dict) and error.get("code"):
            return str(error["code"])
        detail = payload.get("detail")
        return str(detail) if isinstance(detail, str) else None

    def data(self, response: httpx.Response, expected: int) -> Any:
        if response.status_code != expected:
            raise AcceptanceFailure(
                f"HTTP {response.request.method} {response.request.url.path} returned "
                f"{response.status_code}, expected {expected}, code={self._error_code(response)}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AcceptanceFailure("invalid_json_response") from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise AcceptanceFailure("invalid_response_envelope")
        return payload["data"]

    def events(self, run_id: str) -> tuple[dict[str, Any], ...]:
        response = self.client.get(f"api/v1/runs/{run_id}/events")
        if response.status_code != 200:
            raise AcceptanceFailure(f"events_unavailable:{response.status_code}")
        return _parse_sse_events(response.text)

    def poll_job(self, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.timeout_s
        while time.monotonic() < deadline:
            job = self.data(self.client.get(f"api/v1/jobs/{job_id}"), 200)
            self.report["partial_evidence"]["last_job"] = job
            if job.get("run_id"):
                self.report["resources"]["run_id"] = job["run_id"]
            if job.get("state") in _TERMINAL_JOB_STATES:
                return job
            time.sleep(1.0)
        raise AcceptanceFailure(f"job_timeout:{job_id}")

    def capture_partial(self, run_id: str | None) -> None:
        if not run_id:
            return
        try:
            events = self.events(run_id)
            self.report["partial_evidence"]["events"] = list(events)
        except Exception as exc:
            self.report["partial_evidence"]["events_error"] = type(exc).__name__
        response = self.client.get(f"api/v1/runs/{run_id}/general")
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                self.report["partial_evidence"]["general"] = payload.get("data")


def _event_types(events: tuple[dict[str, Any], ...]) -> set[str]:
    return {str(item["event_type"]) for item in events}


def _provider_event_evidence(events: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    response_ids = []
    for event in events:
        data = event["data"]
        response_id = data.get("provider_response_id")
        model = str(data.get("provider_model") or "")
        if response_id and model and not model.lower().startswith(("test", "injected:")):
            response_ids.append(str(response_id))
    return tuple(dict.fromkeys(response_ids))


def _proposal_models(events: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(event["data"]["provider_model"])
            for event in events
            if event["event_type"] == "general_proposal_committed"
            and event.get("data", {}).get("provider_model")
        )
    )


def _validate_construction_outputs(
    package: dict[str, Any],
    downloaded: list[tuple[dict[str, Any], bytes]],
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    construction = package.get("construction")
    if not isinstance(construction, dict):
        raise AcceptanceFailure("construction_plan_missing")
    pieces = construction.get("pieces")
    if not isinstance(pieces, list) or not pieces:
        raise AcceptanceFailure("construction_pieces_missing")
    bom_component_ids = {
        str(row.get("component_id"))
        for row in package.get("bom_rows", [])
        if isinstance(row, dict) and row.get("component_id")
    }
    manufactured_count = 0
    hardware_count = 0
    hardware_pending_fields = 0
    reviewed_components = {
        str(component.get("id")): component
        for component in (review or {}).get("components", [])
        if isinstance(component, dict) and component.get("id")
    }
    visual_passes = {
        str(check.get("id")): check
        for check in (review or {}).get("machine_checks", [])
        if isinstance(check, dict)
        and check.get("outcome") == "pass"
        and check.get("method") == "model_visual"
    }
    accepted_reviews = {
        str(field_review.get("target_ref")): field_review
        for field_review in (review or {}).get("machine_field_reviews", [])
        if isinstance(field_review, dict) and field_review.get("status") == "accepted"
    }
    for piece in pieces:
        if not isinstance(piece, dict):
            raise AcceptanceFailure("construction_piece_invalid")
        geometry = piece.get("geometry")
        shape_kind = geometry.get("shape_kind") if isinstance(geometry, dict) else None
        if shape_kind == "hardware":
            hardware_count += 1
            component_id = str(piece.get("component_id"))
            component = reviewed_components.get(component_id)
            classification_accepted = False
            for suffix in ("kind", "geometry"):
                target = f"component:{component_id}.{suffix}"
                field_review = accepted_reviews.get(target)
                if field_review is None:
                    continue
                if any(
                    check_id in visual_passes
                    and target in visual_passes[check_id].get("target_refs", [])
                    for check_id in field_review.get("check_ids", [])
                ):
                    classification_accepted = True
                    break
            if (
                not isinstance(component, dict)
                or component.get("kind") != "hardware"
                or not classification_accepted
            ):
                raise AcceptanceFailure("construction_hardware_classification_unreviewed")
            if component_id not in bom_component_ids:
                raise AcceptanceFailure("construction_hardware_bom_missing")
            for field, value_key in (
                ("quantity", "value"),
                ("length", "value_mm"),
                ("width", "value_mm"),
                ("thickness", "value_mm"),
            ):
                value = piece.get(field)
                if not isinstance(value, dict):
                    raise AcceptanceFailure("construction_hardware_field_invalid")
                number = value.get(value_key)
                if isinstance(number, (int, float)) and not isinstance(number, bool) and number > 0:
                    if (
                        value.get("review_status") != "accepted"
                        or value.get("state") in {None, "unknown", "conflict"}
                        or not str(value.get("explanation") or "").strip()
                    ):
                        raise AcceptanceFailure("construction_hardware_numeric_unreviewed")
                    continue
                if (
                    number is not None
                    or value.get("state") not in {"unknown", "conflict"}
                    or value.get("review_status")
                    not in {"abstained", "rejected", "conflict", "unreviewed"}
                    or not str(value.get("explanation") or "").strip()
                ):
                    raise AcceptanceFailure("construction_hardware_pending_not_explicit")
                hardware_pending_fields += 1
            continue
        if shape_kind not in {"rectangle", "linear", "custom_contour"}:
            raise AcceptanceFailure("construction_piece_geometry_not_manufacturable")
        manufactured_count += 1
        quantity = piece.get("quantity")
        if not isinstance(quantity, dict) or not isinstance(quantity.get("value"), int):
            raise AcceptanceFailure("construction_piece_quantity_not_numeric")
        for field in ("length", "width", "thickness"):
            value = piece.get(field)
            number = value.get("value_mm") if isinstance(value, dict) else None
            if not isinstance(number, (int, float)) or isinstance(number, bool) or number <= 0:
                raise AcceptanceFailure("construction_piece_dimension_not_numeric")
        sheet_ids = piece.get("sheet_ids")
        if not isinstance(sheet_ids, list) or not sheet_ids:
            raise AcceptanceFailure("construction_piece_sheet_missing")
        formats = {
            str(artifact.get("kind"))
            for artifact, payload in downloaded
            if payload
            and artifact.get("status") == "ready"
            and artifact.get("sheet_id") in sheet_ids
        }
        if not {"piece_sheet_svg", "piece_sheet_dxf"} <= formats:
            raise AcceptanceFailure("construction_piece_formats_missing")
    if manufactured_count == 0:
        raise AcceptanceFailure("construction_manufactured_pieces_missing")
    return {
        "piece_count": len(pieces),
        "manufactured_piece_count": manufactured_count,
        "hardware_count": hardware_count,
        "hardware_pending_field_count": hardware_pending_fields,
        "numeric_dimension_count": manufactured_count * 3,
        "piece_sheet_svg_count": sum(
            artifact.get("kind") == "piece_sheet_svg" for artifact, _ in downloaded
        ),
        "piece_sheet_dxf_count": sum(
            artifact.get("kind") == "piece_sheet_dxf" for artifact, _ in downloaded
        ),
    }


def _audit_history_scenarios(
    audit: "AutonomousAudit",
    config: AuditConfig,
    *,
    run_id: str,
    proposal_revision: int,
    review_revision: int,
) -> None:
    if config.public:
        audit.skip(
            "historical_scenarios_exact_snapshot",
            "Public acceptance intentionally omits private history/catalog endpoints.",
            omitted_endpoint="/api/v1/history/scenarios",
        )
        return
    history_scenarios = audit.data(
        audit.client.post(
            "api/v1/history/scenarios",
            json={
                "run_id": run_id,
                "proposal_revision": proposal_revision,
                "review_revision": review_revision,
                "limit": 5,
                "retrieval_method": "attribute",
            },
            headers={"Idempotency-Key": f"{audit.qa_id}-history-scenarios"},
        ),
        200,
    )
    history_evidence = _validate_history_scenarios(
        history_scenarios, run_id, proposal_revision, review_revision
    )
    audit.report["history_scenarios"] = history_scenarios
    audit.check(
        "historical_scenarios_exact_snapshot",
        True,
        "Historical scenarios use the exact autonomous snapshot and preserve provenance; missing numeric cost/hours remain explicit.",
        **history_evidence,
    )


def _resume_resources(path: Path) -> tuple[str, str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        resources = payload["resources"]
        document_id = resources["document_id"]
        job_id = resources["job_id"]
        run_id = resources["run_id"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AcceptanceFailure("invalid_resume_report") from exc
    if not all(isinstance(item, str) and item for item in (document_id, job_id, run_id)):
        raise AcceptanceFailure("invalid_resume_report")
    return document_id, job_id, run_id


def run_autonomous_acceptance(config: AuditConfig) -> dict[str, Any]:
    audit = AutonomousAudit(config)
    run_id: str | None = None
    try:
        session = audit.data(audit.client.get("api/v1/session"), 200)
        audit.check(
            "session",
            bool(session.get("environment"))
            and (config.public or bool(session.get("authenticated"))),
            (
                "The target exposed the public environment without credentials."
                if config.public
                else "The target exposed an authenticated environment-scoped session."
            ),
            environment=session.get("environment"),
            authenticated=session.get("authenticated"),
        )
        if config.resume_report is not None:
            document_id, job_id, expected_run_id = _resume_resources(
                config.resume_report
            )
            audit.report["resumed_from"] = config.resume_report.name
            audit.report["resources"].update(
                {"document_id": document_id, "job_id": job_id, "run_id": expected_run_id}
            )
            manifest = audit.data(
                audit.client.get(f"api/v1/documents/{document_id}"), 200
            )
            job = audit.poll_job(job_id)
            run_id = job.get("run_id")
            audit.check(
                "resumed_existing_job",
                job.get("state") == "succeeded" and run_id == expected_run_id,
                "Verification reused the existing durable job without submitting another model run.",
                document_id=document_id,
                job_id=job_id,
                run_id=run_id,
                state=job.get("state"),
            )
        else:
            fixture_bytes = config.fixture.read_bytes()
            manifest = audit.data(
                audit.client.post(
                    "api/v1/documents",
                    files={
                        "file": (
                            f"{audit.qa_id}-{config.fixture.name}",
                            fixture_bytes,
                            "application/dxf",
                        )
                    },
                ),
                201,
            )
            document_id = manifest["document_id"]
            audit.report["resources"]["document_id"] = document_id
        audit.check(
            "source_manifest",
            manifest.get("sha256") == audit.report["fixture_sha256"]
            and manifest.get("artifacts", {}).get("normalized_dxf", {}).get("sha256")
            == audit.report["fixture_sha256"],
            "The server manifest preserves the exact public DXF source hash.",
            document_id=document_id,
            source_sha256=manifest.get("sha256"),
            normalized_sha256=(manifest.get("artifacts", {}).get("normalized_dxf") or {}).get("sha256"),
        )
        if config.resume_report is None:
            submitted = audit.data(
                audit.client.post(
                    "api/v1/jobs",
                    json={
                        "document_id": document_id,
                        "mode": "live",
                        "input_kind": "general_furniture",
                        "proposal_mode": "model_generated",
                    },
                    headers={"Idempotency-Key": f"{audit.qa_id}-job"},
                ),
                202,
            )
            job_id = submitted["id"]
            audit.report["resources"]["job_id"] = job_id
            job = audit.poll_job(job_id)
            run_id = job.get("run_id")
        if job.get("state") != "succeeded" or not run_id:
            audit.capture_partial(run_id)
            audit.check(
                "durable_autonomous_job",
                False,
                "The online autonomous job did not succeed; partial evidence was preserved.",
                job_id=job_id,
                run_id=run_id,
                state=job.get("state"),
                error=job.get("error"),
            )
        events = audit.events(run_id)
        audit.report["partial_evidence"]["events"] = list(events)
        types = _event_types(events)
        required_events = {
            "general_proposal_committed",
            "general_auto_review_started",
            "general_auto_review_tool_completed",
            "general_auto_review_completed",
        }
        provider_response_ids = _provider_event_evidence(events)
        proposer_models = _proposal_models(events)
        image_hashes = _extract_image_hashes(events)
        visual_artifacts = _visual_event_artifacts(events)
        audit.check(
            "real_provider_events",
            required_events <= types and bool(provider_response_ids),
            "Durable events prove real proposer/reviewer provider calls.",
            event_types=sorted(types),
            provider_response_ids=provider_response_ids,
        )
        audit.check(
            "source_image_hash_events",
            bool(image_hashes)
            and bool(visual_artifacts)
            and all(
                _SHA256.fullmatch(str(item.get("sha256") or ""))
                and str(item.get("reference") or "").startswith(
                    str(manifest["sha256"])
                )
                and item.get("source_view_ids")
                and item.get("crop_bounds_source")
                for item in visual_artifacts
            ),
            "Public events bind actual visual hashes and crop provenance to the source DXF hash.",
            image_sha256s=image_hashes,
            visual_artifacts=visual_artifacts,
        )
        record = audit.data(
            audit.client.get(f"api/v1/runs/{run_id}/general"), 200
        )
        audit.report["partial_evidence"]["general"] = record
        review = record.get("review")
        if not isinstance(review, dict):
            raise AcceptanceFailure("machine_review_missing")
        _assert_no_machine_confirmed(review)
        occurrence_evidence = _assert_occurrence_authority(review)
        provenance = review.get("machine_provenance") or {}
        reviewer_model = str(provenance.get("model") or "")
        provenance_response_ids = tuple(provenance.get("response_ids") or ())
        audit.check(
            "machine_review_provenance",
            review.get("reviewer_kind") == "machine"
            and review.get("auto_review_status")
            in {"accepted", "incomplete", "conflict", "abstained"}
            and bool(reviewer_model)
            and not reviewer_model.lower().startswith(("test", "injected:"))
            and bool(provenance.get("policy_version"))
            and bool(provenance_response_ids)
            and bool(set(provenance_response_ids) & set(provider_response_ids))
            and record.get("proposal", {}).get("proposal_origin") == "native_tool",
            "The final critic is machine-attributed with policy and response provenance.",
            proposal_revision=record.get("proposal_revision"),
            review_revision=record.get("review_revision"),
            auto_review_status=review.get("auto_review_status"),
            machine_provenance=provenance,
        )
        audit.check(
            "separate_live_models",
            any("sol" in model.lower() for model in proposer_models)
            and "astra" in reviewer_model.lower()
            and reviewer_model not in proposer_models,
            "The fresh live run used a Sol proposer and a separate Astra critic.",
            proposer_models=proposer_models,
            reviewer_model=reviewer_model,
        )
        audit.check(
            "no_forged_confirmed_facts",
            True,
            "Machine facts contain no forged confirmations; physical occurrences require observed/derived quantity and hypotheses remain provisional.",
            **occurrence_evidence,
        )
        proposal_revision = int(record["proposal_revision"])
        review_revision = int(record["review_revision"])
        proposal_events = [
            item["data"]
            for item in events
            if item["event_type"]
            in {"general_proposal_committed", "general_auto_semantic_repair_committed"}
        ]
        committed_revisions = sorted(
            {
                int(item["proposal_revision"])
                for item in proposal_events
                if item.get("proposal_revision") is not None
            }
        )
        semantic_repair = "general_auto_semantic_repair_committed" in types
        lineage_ok = bool(committed_revisions) and committed_revisions[-1] == proposal_revision
        if semantic_repair:
            lineage_ok = lineage_ok and len(committed_revisions) >= 2 and committed_revisions[-1] == committed_revisions[0] + 1
        audit.check(
            "proposal_lineage",
            lineage_ok,
            "P1/P2 lineage is explicit when the autonomous critic performs semantic repair.",
            semantic_repair=semantic_repair,
            committed_revisions=committed_revisions,
            final_proposal_revision=proposal_revision,
        )
        derived = audit.data(
            audit.client.get(
                f"api/v1/runs/{run_id}/general/derived",
                params={
                    "proposal_revision": proposal_revision,
                    "review_revision": review_revision,
                },
            ),
            200,
        )
        package = derived["package"]
        audit.check(
            "exact_revision_derived",
            package.get("proposal_revision") == proposal_revision
            and package.get("review_revision") == review_revision,
            "Derived package retrieval is pinned to the exact reviewed proposal snapshot.",
            proposal_revision=proposal_revision,
            review_revision=review_revision,
            package_status=package.get("status"),
        )
        artifact_payloads: dict[str, bytes] = {}
        downloaded_artifacts: list[tuple[dict[str, Any], bytes]] = []
        for artifact in package.get("artifacts", []):
            response = audit.client.get(
                f"api/v1/runs/{run_id}/general/artifacts/{artifact['id']}",
                params={
                    "proposal_revision": proposal_revision,
                    "review_revision": review_revision,
                },
            )
            if response.status_code != 200:
                raise AcceptanceFailure(
                    f"artifact_unavailable:{artifact['id']}:{response.status_code}"
                )
            artifact_payloads[str(artifact["kind"])] = response.content
            downloaded_artifacts.append((artifact, response.content))
        if "bom_csv" not in artifact_payloads or "drawing_svg" not in artifact_payloads:
            raise AcceptanceFailure("provisional_exports_missing")
        export_evidence = _validate_provisional_exports(
            artifact_payloads["bom_csv"], artifact_payloads["drawing_svg"]
        )
        audit.check(
            "provisional_exports",
            True,
            "CSV and SVG retain provisional/unknown occurrence labels and manufacturing warning.",
            **export_evidence,
        )
        audit.check(
            "numeric_construction_outputs",
            True,
            "Every primary CAD piece is numeric and exposes downloadable SVG and DXF sheets.",
            **_validate_construction_outputs(package, downloaded_artifacts, review),
        )
        _audit_history_scenarios(
            audit,
            config,
            run_id=run_id,
            proposal_revision=proposal_revision,
            review_revision=review_revision,
        )
        audit.report["resources"].update(
            {
                "run_id": run_id,
                "proposal_revision": proposal_revision,
                "review_revision": review_revision,
            }
        )
        audit.report["status"] = "passed"
    except Exception as exc:
        audit.capture_partial(run_id)
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
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("base URL must be absolute HTTP(S)")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError(
            "base URL cannot contain credentials, query or fragment"
        )
    return value.rstrip("/")


def _credentials() -> tuple[str, str]:
    username = os.getenv("VEXPLORER_QA_USERNAME") or input("Basic username: ").strip()
    password = os.getenv("VEXPLORER_QA_PASSWORD") or getpass("Basic password: ")
    if not username or not password:
        raise SystemExit(
            "Basic credentials are required via environment or interactive input"
        )
    return username, password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", type=_validated_base_url, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--public",
        action="store_true",
        help="Use the public no-login surface and omit private history/catalog checks.",
    )
    parser.add_argument(
        "--resume-report",
        type=Path,
        help="Reuse document/job/run IDs from an earlier report; never submits a new job.",
    )
    args = parser.parse_args()
    if not args.fixture.is_file() or args.fixture.suffix.lower() != ".dxf":
        parser.error("--fixture must be an existing public DXF")
    if args.timeout < 300:
        parser.error("--timeout must be at least 300 seconds for real model execution")
    if args.resume_report is not None and not args.resume_report.is_file():
        parser.error("--resume-report must be an existing autonomous audit JSON")
    if args.public and args.resume_report is not None:
        parser.error("--public requires a fresh durable live job; resume is not allowed")
    username, password = (None, None) if args.public else _credentials()
    try:
        report = run_autonomous_acceptance(
            AuditConfig(
                base_url=args.base_url,
                fixture=args.fixture.resolve(),
                output=args.output.resolve(),
                username=username,
                password=password,
                origin=os.getenv("VEXPLORER_QA_ORIGIN"),
                public=args.public,
                timeout_s=args.timeout,
                resume_report=args.resume_report.resolve()
                if args.resume_report is not None
                else None,
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "failure_type": type(exc).__name__,
                    "output": str(args.output.resolve()),
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(args.output.resolve()),
                "check_count": len(report["checks"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
