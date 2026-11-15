"""Aggregate a frozen technician-study collection without exposing row data."""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


class StudyInputError(ValueError):
    """Raised when a study collection is unsafe or internally inconsistent."""


_EVIDENCE_KINDS = {
    "developer_fixture",
    "independent_review",
    "observed_technician_study",
}
_SOURCE_KINDS = {"developer_fixture", "published", "company_authorized"}
_CONDITIONS = {"manual", "assisted"}
_CORRECTION_KINDS = {
    "missing_piece_added",
    "extra_piece_removed",
    "quantity_changed",
    "dimension_changed",
    "material_changed",
    "finish_changed",
    "assembly_changed",
    "operation_changed",
    "other",
}
_SEVERITIES = {"minor", "major", "critical"}
_EXCLUSION_REASONS = {
    "procedure_interrupted",
    "technical_failure",
    "invalid_assignment",
    "participant_withdrew",
    "unusable_source",
}
_REFERENCE_KINDS = {"actual", "budget", "quote"}


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StudyInputError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise StudyInputError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StudyInputError(f"{label} must be a non-empty string")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise StudyInputError(f"{label} must be boolean")
    return value


def _number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StudyInputError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise StudyInputError(f"{label} must be finite and >= {minimum}")
    return result


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StudyInputError(f"{label} correction count must be a positive integer")
    return value


def _unique_id(value: Any, label: str, seen: set[str]) -> str:
    identifier = _text(value, label)
    if identifier in seen:
        raise StudyInputError(f"duplicate {label}: {identifier!r}")
    seen.add(identifier)
    return identifier


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _read_collection(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StudyInputError(f"cannot read study collection: {exc}") from exc
    return _object(payload, "collection")


def _validate_study(raw: Any) -> dict[str, Any]:
    study = _object(raw, "study")
    evidence_kind = _text(study.get("evidence_kind"), "study.evidence_kind")
    if evidence_kind not in _EVIDENCE_KINDS:
        raise StudyInputError("unsupported study.evidence_kind")
    source_kind = _text(study.get("source_kind"), "study.source_kind")
    if source_kind not in _SOURCE_KINDS:
        raise StudyInputError("unsupported study.source_kind")
    observed = _boolean(
        study.get("actual_technicians_observed"),
        "study.actual_technicians_observed",
    )
    if evidence_kind == "observed_technician_study" and not observed:
        raise StudyInputError(
            "observed_technician_study requires actual_technicians_observed=true"
        )
    if evidence_kind == "developer_fixture" and (
        observed or source_kind != "developer_fixture"
    ):
        raise StudyInputError(
            "developer_fixture requires source_kind=developer_fixture and no observed technicians"
        )
    if source_kind == "developer_fixture" and evidence_kind != "developer_fixture":
        raise StudyInputError("developer_fixture source cannot claim independent evidence")
    frozen = _boolean(study.get("frozen_before_scoring"), "study.frozen_before_scoring")
    if not frozen:
        raise StudyInputError("study.frozen_before_scoring must be true")
    return {
        "id": _text(study.get("id"), "study.id"),
        "protocol_id": _text(study.get("protocol_id"), "study.protocol_id"),
        "evidence_kind": evidence_kind,
        "source_kind": source_kind,
        "actual_technicians_observed": observed,
        "frozen_before_scoring": frozen,
    }


def _validate_cases(raw: Any) -> dict[str, dict[str, str]]:
    cases: dict[str, dict[str, str]] = {}
    projects: dict[str, set[str]] = {}
    families: dict[str, set[str]] = {}
    duplicate_groups: dict[str, set[str]] = {}
    seen: set[str] = set()
    for index, value in enumerate(_array(raw, "cases")):
        case = _object(value, f"cases[{index}]")
        case_id = _unique_id(case.get("id"), "case id", seen)
        split = _text(case.get("split"), f"cases[{index}].split")
        metadata = {
            "split": split,
            "project_id": _text(case.get("project_id"), f"cases[{index}].project_id"),
            "family_id": _text(case.get("family_id"), f"cases[{index}].family_id"),
            "duplicate_group_id": _text(
                case.get("duplicate_group_id"),
                f"cases[{index}].duplicate_group_id",
            ),
            "plan_sha256": _text(case.get("plan_sha256"), f"cases[{index}].plan_sha256"),
        }
        if re.fullmatch(r"[0-9a-f]{64}", metadata["plan_sha256"]) is None:
            raise StudyInputError(f"cases[{index}].plan_sha256 must be lowercase 64-hex")
        cases[case_id] = metadata
        projects.setdefault(metadata["project_id"], set()).add(split)
        families.setdefault(metadata["family_id"], set()).add(split)
        duplicate_groups.setdefault(metadata["duplicate_group_id"], set()).add(split)
    if not cases:
        raise StudyInputError("cases must not be empty")
    for label, groups in (
        ("project_id", projects),
        ("family_id", families),
        ("duplicate_group_id", duplicate_groups),
    ):
        for identifier, splits in groups.items():
            if len(splits) > 1:
                raise StudyInputError(f"{label} {identifier!r} crosses splits")
    return cases


def _validate_sessions(
    raw: Any,
    cases: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    session_ids: set[str] = set()
    participant_cases: set[tuple[str, str]] = set()
    for index, value in enumerate(_array(raw, "sessions")):
        label = f"sessions[{index}]"
        session = _object(value, label)
        session_id = _unique_id(session.get("id"), "session id", session_ids)
        case_id = _text(session.get("case_id"), f"{label}.case_id")
        if case_id not in cases:
            raise StudyInputError(f"{label}.case_id is not declared")
        participant_id = _text(session.get("participant_id"), f"{label}.participant_id")
        pair = (participant_id, case_id)
        if pair in participant_cases:
            raise StudyInputError("a participant may appear only once per case")
        participant_cases.add(pair)
        reviewer_id = _text(session.get("reviewer_id"), f"{label}.reviewer_id")
        if reviewer_id == participant_id:
            raise StudyInputError(f"{label}.reviewer_id must differ from participant_id")
        condition = _text(session.get("condition"), f"{label}.condition")
        if condition not in _CONDITIONS:
            raise StudyInputError(f"{label}.condition must be manual or assisted")
        duration = _number(session.get("duration_seconds"), f"{label}.duration_seconds")
        interruption = _number(
            session.get("interruption_seconds"),
            f"{label}.interruption_seconds",
        )
        if interruption > duration:
            raise StudyInputError(
                f"{label}.interruption_seconds cannot exceed duration_seconds"
            )
        exclusion = session.get("exclusion_reason")
        if exclusion is not None:
            exclusion = _text(exclusion, f"{label}.exclusion_reason")
            if exclusion not in _EXCLUSION_REASONS:
                raise StudyInputError(f"unsupported {label}.exclusion_reason")
        corrections: list[dict[str, Any]] = []
        for correction_index, raw_correction in enumerate(
            _array(session.get("corrections"), f"{label}.corrections")
        ):
            correction_label = f"{label}.corrections[{correction_index}]"
            correction = _object(raw_correction, correction_label)
            kind = _text(correction.get("kind"), f"{correction_label}.kind")
            if kind not in _CORRECTION_KINDS:
                raise StudyInputError(f"unsupported {correction_label}.kind")
            severity = _text(
                correction.get("severity"), f"{correction_label}.severity"
            )
            if severity not in _SEVERITIES:
                raise StudyInputError(f"unsupported {correction_label}.severity")
            corrections.append(
                {
                    "kind": kind,
                    "severity": severity,
                    "count": _positive_integer(
                        correction.get("count"), correction_label
                    ),
                }
            )
        sessions.append(
            {
                "id": session_id,
                "condition": condition,
                "acceptable": _boolean(
                    session.get("acceptable"), f"{label}.acceptable"
                ),
                "reviewer_blinded_to_condition": _boolean(
                    session.get("reviewer_blinded_to_condition"),
                    f"{label}.reviewer_blinded_to_condition",
                ),
                "active_seconds": duration - interruption,
                "exclusion_reason": exclusion,
                "corrections": corrections,
            }
        )
    if not sessions:
        raise StudyInputError("sessions must not be empty")
    return sessions


def _economic_value(value: Any, label: str, *, cost: bool) -> dict[str, Any]:
    item = _object(value, label)
    result = {
        "value": _number(item.get("value"), f"{label}.value"),
        "scope_id": _text(item.get("scope_id"), f"{label}.scope_id"),
    }
    if cost:
        currency = _text(item.get("currency"), f"{label}.currency")
        if re.fullmatch(r"[A-Z]{3}", currency) is None:
            raise StudyInputError(f"{label}.currency must be three uppercase letters")
        effective_date = _text(
            item.get("effective_date"), f"{label}.effective_date"
        )
        try:
            date.fromisoformat(effective_date)
        except ValueError as exc:
            raise StudyInputError(f"{label}.effective_date must be an ISO date") from exc
        result.update(currency=currency, effective_date=effective_date)
    return result


def _economic_pair(value: Any, label: str, *, cost: bool) -> dict[str, Any] | None:
    if value is None:
        return None
    pair = _object(value, label)
    reference = _economic_value(pair.get("reference"), f"{label}.reference", cost=cost)
    prediction_raw = pair.get("prediction")
    prediction = (
        None
        if prediction_raw is None
        else _economic_value(prediction_raw, f"{label}.prediction", cost=cost)
    )
    return {"reference": reference, "prediction": prediction}


def _validate_economics(
    raw: Any,
    cases: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    economics: list[dict[str, Any]] = []
    seen_cases: set[str] = set()
    for index, value in enumerate(_array(raw, "economics")):
        label = f"economics[{index}]"
        item = _object(value, label)
        case_id = _text(item.get("case_id"), f"{label}.case_id")
        if case_id not in cases:
            raise StudyInputError(f"{label}.case_id is not declared")
        if case_id in seen_cases:
            raise StudyInputError("economics may contain each case only once")
        seen_cases.add(case_id)
        reference_kind = _text(
            item.get("reference_kind"), f"{label}.reference_kind"
        )
        if reference_kind not in _REFERENCE_KINDS:
            raise StudyInputError(f"unsupported {label}.reference_kind")
        cost = _economic_pair(item.get("cost"), f"{label}.cost", cost=True)
        hours = _economic_pair(item.get("hours"), f"{label}.hours", cost=False)
        if cost is None and hours is None:
            raise StudyInputError(f"{label} must contain cost or hours")
        economics.append(
            {"reference_kind": reference_kind, "cost": cost, "hours": hours}
        )
    return economics


def _condition_report(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    acceptable = [session for session in sessions if session["acceptable"]]
    times = [session["active_seconds"] for session in acceptable]
    by_kind: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    for session in sessions:
        for correction in session["corrections"]:
            by_kind[correction["kind"]] += correction["count"]
            by_severity[correction["severity"]] += correction["count"]
    correction_count = sum(by_kind.values())
    return {
        "sessions": len(sessions),
        "acceptable_sessions": len(acceptable),
        "acceptance_rate": _ratio(len(acceptable), len(sessions)),
        "acceptable_time_sessions": len(times),
        "mean_active_seconds_to_acceptable": _mean(times),
        "median_active_seconds_to_acceptable": _median(times),
        "correction_count": correction_count,
        "mean_corrections_per_session": (
            correction_count / len(sessions) if sessions else None
        ),
        "missing_piece_occurrences": by_kind["missing_piece_added"],
        "extra_piece_occurrences": by_kind["extra_piece_removed"],
        "corrections_by_kind": dict(sorted(by_kind.items())),
        "corrections_by_severity": dict(sorted(by_severity.items())),
    }


def _numeric_report(economics: list[dict[str, Any]], field: str) -> dict[str, Any]:
    eligible = 0
    evaluated = 0
    absolute_errors: list[float] = []
    signed_errors: list[float] = []
    relative_errors: list[float] = []
    reference_magnitudes: list[float] = []
    reference_kinds: Counter[str] = Counter()
    evaluated_kinds: Counter[str] = Counter()
    incompatibilities: Counter[str] = Counter()
    incompatible_cases = 0
    metadata_fields = ("currency", "scope_id", "effective_date") if field == "cost" else ("scope_id",)
    for item in economics:
        pair = item[field]
        if pair is None:
            continue
        eligible += 1
        reference_kinds[item["reference_kind"]] += 1
        prediction = pair["prediction"]
        if prediction is None:
            continue
        mismatches = [
            metadata
            for metadata in metadata_fields
            if prediction[metadata] != pair["reference"][metadata]
        ]
        if mismatches:
            incompatible_cases += 1
            for mismatch in mismatches:
                incompatibilities[mismatch] += 1
            continue
        reference_value = pair["reference"]["value"]
        signed_error = prediction["value"] - reference_value
        evaluated += 1
        evaluated_kinds[item["reference_kind"]] += 1
        signed_errors.append(signed_error)
        absolute_errors.append(abs(signed_error))
        reference_magnitudes.append(abs(reference_value))
        if reference_value != 0:
            relative_errors.append(abs(signed_error / reference_value))
    reference_total = sum(reference_magnitudes)
    return {
        "eligible_references": eligible,
        "evaluated": evaluated,
        "coverage": _ratio(evaluated, eligible),
        "mae": _mean(absolute_errors),
        "median_absolute_error": _median(absolute_errors),
        "mean_signed_error": _mean(signed_errors),
        "relative_error_cases": len(relative_errors),
        "mape": _mean(relative_errors),
        "wape": sum(absolute_errors) / reference_total if reference_total else None,
        "reference_kind_counts": dict(sorted(reference_kinds.items())),
        "evaluated_reference_kind_counts": dict(sorted(evaluated_kinds.items())),
        "metadata_incompatible_cases": incompatible_cases,
        "metadata_incompatibility_reasons": dict(sorted(incompatibilities.items())),
    }


def evaluate_study_file(path: str | Path) -> dict[str, Any]:
    """Validate and aggregate a study collection, omitting all row identifiers."""

    collection = _read_collection(Path(path))
    if collection.get("schema_version") != "1.0":
        raise StudyInputError("schema_version must be '1.0'")
    study = _validate_study(collection.get("study"))
    cases = _validate_cases(collection.get("cases"))
    sessions = _validate_sessions(collection.get("sessions"), cases)
    economics = _validate_economics(collection.get("economics"), cases)

    eligible_sessions = [
        session for session in sessions if session["exclusion_reason"] is None
    ]
    excluded = [session for session in sessions if session["exclusion_reason"]]
    exclusion_reasons = Counter(
        session["exclusion_reason"] for session in excluded
    )
    by_condition = {
        condition: _condition_report(
            [session for session in eligible_sessions if session["condition"] == condition]
        )
        for condition in sorted(_CONDITIONS)
    }
    manual = by_condition["manual"]
    assisted = by_condition["assisted"]
    if study["evidence_kind"] == "developer_fixture":
        claim_status = "developer_fixture_not_empirical"
    elif study["evidence_kind"] == "observed_technician_study":
        claim_status = "descriptive_observation_not_causal"
    else:
        claim_status = "no_observed_technician_evidence"

    def difference(left: Any, right: Any) -> float | None:
        return left - right if left is not None and right is not None else None

    return {
        "schema_version": "1.0",
        "dataset": {
            **study,
            "case_count": len(cases),
            "session_count": len(sessions),
            "technician_evidence_available": (
                study["evidence_kind"] == "observed_technician_study"
                and study["actual_technicians_observed"]
            ),
        },
        "sessions": {
            "eligible_sessions": len(eligible_sessions),
            "excluded_sessions": len(excluded),
            "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
            "blinded_review_sessions": sum(
                session["reviewer_blinded_to_condition"]
                for session in eligible_sessions
            ),
            "by_condition": by_condition,
            "descriptive_difference": {
                "assisted_minus_manual_mean_active_seconds": difference(
                    assisted["mean_active_seconds_to_acceptable"],
                    manual["mean_active_seconds_to_acceptable"],
                ),
                "assisted_minus_manual_mean_corrections": difference(
                    assisted["mean_corrections_per_session"],
                    manual["mean_corrections_per_session"],
                ),
                "savings_claim_supported": False,
                "claim_status": claim_status,
            },
        },
        "economics": {
            "cost": _numeric_report(economics, "cost"),
            "hours": _numeric_report(economics, "hours"),
        },
        "limitations": [
            "Aggregates do not establish that a developer fixture or label is independent evidence.",
            "Manual/assisted differences are descriptive and do not establish causal time savings.",
            "Budget, quote and actual references remain separately counted and must not be conflated.",
            "Excluded sessions and incompatible economic metadata reduce coverage instead of being imputed.",
        ],
    }
