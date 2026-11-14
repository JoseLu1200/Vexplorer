from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


RUN_ID = re.compile(r"^run-[0-9a-f]{32}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Known fixtures must never be promoted as real furniture. The first value is
# the public deployment's mesa_demo_001.dxf, observed on 2026-11-14.
KNOWN_NON_REAL_SOURCE_SHA256 = frozenset(
    {"c8aa3006c1098f06df0bc56ac57dfa4e46f597aa5f7c721818e4608d7d367d82"}
)


class BackfillError(ValueError):
    pass


@dataclass(frozen=True)
class Provenance:
    source_kind: str
    document_sha256: str
    authorization_reference: str
    evidence_reference: str
    attested_by: str
    approved_for_public_library: bool


@dataclass(frozen=True)
class Selection:
    run_id: str
    result_revision: int
    label: str
    embedding_mode: str
    provenance: Provenance


@dataclass(frozen=True)
class Manifest:
    schema_version: str
    backup_reference: str | None
    entries: tuple[Selection, ...]


@dataclass(frozen=True)
class Assessment:
    run_id: str
    result_revision: int
    eligible: bool
    reasons: tuple[str, ...]
    document_id: str | None
    source_sha256: str | None
    reviewer_name: str | None
    review_reason: str | None


def _required_text(value: Any, error: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BackfillError(error)
    return value.strip()


def _strict_keys(value: dict[str, Any], allowed: set[str], error: str) -> None:
    if set(value) != allowed:
        raise BackfillError(error)


def load_manifest(path: Path) -> Manifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackfillError("invalid_manifest") from exc
    if not isinstance(raw, dict):
        raise BackfillError("invalid_manifest")
    _strict_keys(raw, {"schema_version", "backup_reference", "entries"}, "invalid_manifest_fields")
    if raw.get("schema_version") != "1.0":
        raise BackfillError("unsupported_manifest_version")
    values = raw.get("entries")
    if not isinstance(values, list) or not values:
        raise BackfillError("empty_manifest")
    entries: list[Selection] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            raise BackfillError("invalid_manifest_entry")
        _strict_keys(
            value,
            {"run_id", "result_revision", "label", "embedding_mode", "provenance"},
            "invalid_manifest_entry_fields",
        )
        run_id = value.get("run_id")
        if not isinstance(run_id, str) or RUN_ID.fullmatch(run_id) is None:
            raise BackfillError("invalid_run_id")
        if run_id in seen:
            raise BackfillError("duplicate_run_selection")
        seen.add(run_id)
        revision = value.get("result_revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise BackfillError("invalid_result_revision")
        label = _required_text(value.get("label"), "invalid_label", maximum=120)
        embedding_mode = value.get("embedding_mode")
        if embedding_mode not in {"offline", "openai"}:
            raise BackfillError("invalid_embedding_mode")
        source = value.get("provenance")
        if not isinstance(source, dict):
            raise BackfillError("invalid_provenance")
        _strict_keys(
            source,
            {
                "source_kind",
                "document_sha256",
                "authorization_reference",
                "evidence_reference",
                "attested_by",
                "approved_for_public_library",
            },
            "invalid_provenance_fields",
        )
        if source.get("source_kind") != "real_furniture":
            raise BackfillError("source_not_real_furniture")
        if source.get("approved_for_public_library") is not True:
            raise BackfillError("public_library_not_approved")
        digest = source.get("document_sha256")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            raise BackfillError("invalid_document_sha256")
        provenance = Provenance(
            source_kind="real_furniture",
            document_sha256=digest,
            authorization_reference=_required_text(
                source.get("authorization_reference"), "missing_authorization_reference"
            ),
            evidence_reference=_required_text(
                source.get("evidence_reference"), "missing_evidence_reference"
            ),
            attested_by=_required_text(source.get("attested_by"), "missing_attested_by", maximum=120),
            approved_for_public_library=True,
        )
        entries.append(Selection(run_id, revision, label, embedding_mode, provenance))
    backup = raw.get("backup_reference")
    if backup is not None:
        backup = _required_text(backup, "invalid_backup_reference")
    return Manifest("1.0", backup, tuple(entries))


def require_apply_preconditions(manifest: Manifest) -> None:
    if manifest.backup_reference is None:
        raise BackfillError("backup_reference_required_for_apply")


def library_save_payload(entry: Selection) -> dict[str, Any]:
    return {
        "result_revision": entry.result_revision,
        "label": entry.label,
        "embedding_mode": entry.embedding_mode,
        "publication": {
            "source_kind": entry.provenance.source_kind,
            "source_reference": entry.provenance.evidence_reference,
            "approved_for_public_library": entry.provenance.approved_for_public_library,
        },
    }


def _data(value: Any) -> Any:
    if isinstance(value, dict) and "data" in value:
        if value.get("error"):
            raise BackfillError(f"api_error:{value['error']}")
        return value["data"]
    return value


def assess_candidate(
    entry: Selection,
    run_response: dict[str, Any],
    revisions_response: list[dict[str, Any]] | dict[str, Any],
    document_response: dict[str, Any],
    drawing_response: dict[str, Any],
) -> Assessment:
    run_data = _data(run_response)
    revisions = _data(revisions_response)
    document = _data(document_response)
    drawing = _data(drawing_response)
    run = run_data.get("run") if isinstance(run_data, dict) else None
    reasons: list[str] = []
    if not isinstance(run, dict) or run.get("id") != entry.run_id:
        reasons.append("run_identity_mismatch")
        run = {} if not isinstance(run, dict) else run
    document_id = run.get("document_id")
    if not isinstance(revisions, list):
        revisions = []
    revision = next(
        (item for item in revisions if isinstance(item, dict) and item.get("result_revision") == entry.result_revision),
        None,
    )
    reviewer_name = review_reason = None
    if revision is None:
        reasons.append("result_revision_not_found")
    else:
        if revision.get("state") != "completed":
            reasons.append("completed_revision_required")
        review = revision.get("review")
        if not isinstance(review, dict):
            reasons.append("review_required")
        else:
            reviewer_name = review.get("reviewer_name")
            review_reason = review.get("reason")
            if not isinstance(reviewer_name, str) or not reviewer_name.strip():
                reasons.append("reviewer_required")
            if not isinstance(review_reason, str) or not review_reason.strip():
                reasons.append("review_reason_required")
    source = document.get("source") if isinstance(document, dict) else None
    source_sha256 = source.get("sha256") if isinstance(source, dict) else None
    if source_sha256 != entry.provenance.document_sha256:
        reasons.append("document_sha256_mismatch")
    if source_sha256 in KNOWN_NON_REAL_SOURCE_SHA256:
        reasons.append("known_non_real_source")
    if not isinstance(drawing, dict) or drawing.get("synthetic") is not False:
        reasons.append("synthetic_drawing_not_allowed")
    return Assessment(
        run_id=entry.run_id,
        result_revision=entry.result_revision,
        eligible=not reasons,
        reasons=tuple(reasons),
        document_id=document_id if isinstance(document_id, str) else None,
        source_sha256=source_sha256 if isinstance(source_sha256, str) else None,
        reviewer_name=reviewer_name if isinstance(reviewer_name, str) else None,
        review_reason=review_reason if isinstance(review_reason, str) else None,
    )


def library_items_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = _data(response)
    if isinstance(data, dict):
        data = data.get("items")
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise BackfillError("invalid_library_response")
    return data


def verify_published_items(
    manifest: Manifest, published: dict[str, dict[str, Any]]
) -> None:
    for entry in manifest.entries:
        item = published.get(entry.run_id)
        publication = item.get("publication") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or item.get("result_revision") != entry.result_revision
            or not isinstance(publication, dict)
            or publication.get("source_kind") != "real_furniture"
            or publication.get("source_reference") != entry.provenance.evidence_reference
            or publication.get("approved_for_public_library") is not True
            or not isinstance(publication.get("attested_by"), str)
            or not publication["attested_by"].strip()
            or not isinstance(publication.get("attested_at"), str)
            or not publication["attested_at"].strip()
        ):
            raise BackfillError("library_publication_verification_failed")


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        base = base_url.rstrip("/")
        if not (base.startswith("https://") or base.startswith("http://127.0.0.1")):
            raise BackfillError("https_or_loopback_required")
        self.base_url = base
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                value = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BackfillError(f"http_request_failed:{path}") from exc
        if not isinstance(value, dict):
            raise BackfillError("invalid_api_response")
        return value

    def get(self, path: str) -> dict[str, Any]:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, payload)


def inventory(client: ApiClient, manifest: Manifest) -> tuple[Assessment, ...]:
    assessments: list[Assessment] = []
    for entry in manifest.entries:
        run_response = client.get(f"/api/v1/runs/{entry.run_id}")
        run_data = _data(run_response)
        run = run_data.get("run", {}) if isinstance(run_data, dict) else {}
        document_id = run.get("document_id")
        if not isinstance(document_id, str):
            assessments.append(
                Assessment(entry.run_id, entry.result_revision, False, ("document_id_missing",), None, None, None, None)
            )
            continue
        assessments.append(
            assess_candidate(
                entry,
                run_response,
                client.get(f"/api/v1/runs/{entry.run_id}/revisions"),
                client.get(f"/api/v1/documents/{document_id}"),
                client.get(f"/api/v1/runs/{entry.run_id}/drawing"),
            )
        )
    return tuple(assessments)


def _report(manifest: Manifest, assessments: tuple[Assessment, ...], *, applied: bool) -> dict[str, Any]:
    by_run = {item.run_id: item for item in manifest.entries}
    return {
        "schema_version": "1.0",
        "mode": "apply" if applied else "dry_run",
        "backup_reference": manifest.backup_reference,
        "eligible_count": sum(item.eligible for item in assessments),
        "rejected_count": sum(not item.eligible for item in assessments),
        "entries": [
            {
                **asdict(item),
                "provenance": asdict(by_run[item.run_id].provenance),
                "label": by_run[item.run_id].label,
                "embedding_mode": by_run[item.run_id].embedding_mode,
            }
            for item in assessments
        ],
    }


def execute(client: ApiClient, manifest: Manifest, *, apply: bool) -> dict[str, Any]:
    if apply:
        require_apply_preconditions(manifest)
    assessments = inventory(client, manifest)
    if any(not item.eligible for item in assessments):
        return _report(manifest, assessments, applied=False)
    if not apply:
        return _report(manifest, assessments, applied=False)
    existing = {item.get("run_id"): item for item in library_items_from_response(client.get("/api/v1/library"))}
    for entry in manifest.entries:
        current = existing.get(entry.run_id)
        if current and current.get("embedding") is not None and entry.embedding_mode == "offline":
            raise BackfillError("embedding_downgrade_not_allowed")
    for entry in manifest.entries:
        client.post(
            f"/api/v1/runs/{entry.run_id}/library",
            library_save_payload(entry),
        )
    published = {item.get("run_id"): item for item in library_items_from_response(client.get("/api/v1/library"))}
    verify_published_items(manifest, published)
    return _report(manifest, assessments, applied=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory and explicitly backfill reviewed real furniture into Vexplorer Library."
    )
    parser.add_argument("--base-url", required=True, help="Application root, for example https://host/vexplorer")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write only after every selected entry passes all gates.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        report = execute(ApiClient(args.base_url), manifest, apply=args.apply)
    except BackfillError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        if args.report.exists():
            print("report_exists", file=sys.stderr)
            return 2
        args.report.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0 if report["rejected_count"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())


