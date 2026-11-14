from __future__ import annotations

import csv
from contextlib import closing
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
from typing import Protocol

from pydantic import ValidationError

from backend.app.semantic.embeddings import EmbeddingProviderError, validate_embedding
from backend.app.historico.models import (
    ComparableResponse,
    EmbeddingSpace,
    EstimateContributor,
    EstimateProvenance,
    HistoricalComparable,
    HistoricalConcept,
    HistoricalEstimate,
    HistoricalEstimateScenario,
    HistoricalImport,
    HistoricalProvenance,
    HistoricalRecord,
    HistoricalRecordPage,
    HistoricalTarget,
    ImportErrorItem,
    ImportResult,
    ProvisionalAssumption,
    ProvisionalHistoricalScenario,
    ProvisionalScalingBasis,
    ProvisionalScenarioCondition,
    ProvisionalScenarioResponse,
    ProvisionalScenarioSnapshot,
)


class _EmbeddingResult(Protocol):
    vector: tuple[float, ...]
    model: str
    dimensions: int


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    def embed(self, text: str) -> _EmbeddingResult: ...


@dataclass(frozen=True)
class _StoredEmbedding:
    vector: tuple[float, ...]
    model: str
    dimensions: int


def _canonical(record: HistoricalRecord) -> str:
    return record.model_dump_json(exclude_none=False)


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding_space_incompatible")
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(
        sum(x * x for x in right)
    )
    if denominator == 0:
        raise ValueError("invalid_embedding")
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator


def _semantic_text(value: HistoricalRecord | HistoricalTarget) -> str:
    fields = (
        f"family={value.family or 'unknown'}",
        f"dimensions_mm={value.width_mm},{value.depth_mm},{value.height_mm}",
        f"area_mm2={value.area_mm2}",
        f"length_mm={value.length_mm}",
        f"volume_mm3={value.volume_mm3}",
        f"quantity={value.quantity}",
        f"material={value.material or 'unknown'}",
        f"finish={value.finish or 'unknown'}",
    )
    if isinstance(value, HistoricalRecord):
        component_text = "|".join(
            f"{item.kind or 'unknown'}:{item.quantity}:{item.length_mm}:{item.width_mm}:{item.thickness_mm}:{item.material or 'unknown'}:{item.finish or 'unknown'}"
            for item in value.components
        )
        return "; ".join(fields) + f"; scope={','.join(value.included_scope)}; components={component_text or 'none'}"
    return "; ".join(fields)


def _attribute_score(
    target: HistoricalTarget, record: HistoricalRecord
) -> tuple[float, dict[str, float], tuple[str, ...], tuple[str, ...]]:
    components: dict[str, float] = {}
    differences: list[str] = []
    missing: list[str] = []
    for name in (
        "width_mm",
        "depth_mm",
        "height_mm",
        "length_mm",
        "area_mm2",
        "volume_mm3",
        "quantity",
    ):
        target_value = getattr(target, name)
        record_value = getattr(record, name)
        if target_value is None or record_value is None:
            missing.append(name)
            continue
        score = max(0.0, 1.0 - abs(target_value - record_value) / max(target_value, record_value))
        components[name] = score
        if target_value != record_value:
            differences.append(f"{name}: target={target_value:g}, historical={record_value:g}")
    for name in ("family", "material", "finish"):
        target_value = getattr(target, name)
        record_value = getattr(record, name)
        if target_value is None or record_value is None:
            missing.append(name)
            continue
        score = 1.0 if target_value.casefold() == record_value.casefold() else 0.0
        components[name] = score
        if score == 0:
            differences.append(f"{name}: target={target_value}, historical={record_value}")
    weights = {
        "width_mm": 0.1,
        "depth_mm": 0.1,
        "height_mm": 0.1,
        "area_mm2": 0.15,
        "length_mm": 0.1,
        "volume_mm3": 0.1,
        "quantity": 0.05,
        "family": 0.2,
        "material": 0.2,
        "finish": 0.1,
    }
    available_weight = sum(weights[name] for name in components)
    score = (
        sum(components[name] * weights[name] for name in components) / available_weight
        if available_weight
        else 0.0
    )
    return round(score, 6), components, tuple(differences), tuple(sorted(set(missing)))


@dataclass(frozen=True)
class _ScaledLine:
    concept_id: str
    kind: str
    record_id: str
    score: float
    base_cost: float | None
    base_hours: float | None
    quantity_factor: float | None
    consumption_factor: float | None
    cost: float | None
    hours: float | None
    evidence: str
    formula: str
    missing_data: tuple[str, ...] = ()


class HistoricalStore:
    def __init__(
        self,
        db_path: Path,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        max_records: int = 100_000,
        semantic_candidate_limit: int = 1_000,
    ) -> None:
        if max_records < 1 or semantic_candidate_limit < 1:
            raise ValueError("history limits must be positive")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_provider = embedding_provider
        self.max_records = max_records
        self.semantic_candidate_limit = semantic_candidate_limit
        with closing(self._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS historical_records ("
                "record_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision TEXT NOT NULL, "
                "origin TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS historical_embeddings ("
                "record_id TEXT NOT NULL, payload_hash TEXT NOT NULL, model TEXT NOT NULL, "
                "dimensions INTEGER NOT NULL, vector TEXT NOT NULL, "
                "PRIMARY KEY (record_id, payload_hash, model, dimensions), "
                "FOREIGN KEY (record_id) REFERENCES historical_records(record_id))"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def import_records(
        self, value: HistoricalImport, *, dry_run: bool = False
    ) -> ImportResult:
        canonical = [_canonical(record) for record in value.records]
        import_id = hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()
        accepted = unchanged = rejected = 0
        errors: list[ImportErrorItem] = []
        seen: set[str] = set()
        with closing(self._connect()) as db, db:
            stored_count = db.execute(
                "SELECT COUNT(*) FROM historical_records"
            ).fetchone()[0]
            for row, (record, payload) in enumerate(
                zip(value.records, canonical, strict=True), start=1
            ):
                if record.record_id in seen:
                    rejected += 1
                    errors.append(ImportErrorItem(row=row, error="duplicate record_id in import"))
                    continue
                seen.add(record.record_id)
                digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                existing = db.execute(
                    "SELECT payload_hash FROM historical_records WHERE record_id=?",
                    (record.record_id,),
                ).fetchone()
                if existing is not None and existing["payload_hash"] == digest:
                    unchanged += 1
                elif existing is not None:
                    rejected += 1
                    errors.append(
                        ImportErrorItem(
                            row=row,
                            error="record_id already exists with different immutable payload",
                        )
                    )
                else:
                    if stored_count + accepted >= self.max_records:
                        rejected += 1
                        errors.append(
                            ImportErrorItem(
                                row=row, error="history_capacity_exceeded"
                            )
                        )
                        continue
                    accepted += 1
                    if not dry_run:
                        db.execute(
                            "INSERT INTO historical_records VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                record.record_id,
                                record.project_id,
                                record.revision,
                                record.origin,
                                payload,
                                digest,
                            ),
                        )
            if dry_run:
                db.rollback()
        return ImportResult(
            import_id=import_id,
            dry_run=dry_run,
            accepted=accepted,
            unchanged=unchanged,
            rejected=rejected,
            errors=tuple(errors),
        )

    def import_csv(
        self,
        text: str,
        *,
        dry_run: bool = False,
        imported_by: str | None = None,
    ) -> ImportResult:
        records: list[HistoricalRecord] = []
        errors: list[ImportErrorItem] = []
        reader = csv.DictReader(io.StringIO(text))
        for row_number, row in enumerate(reader, start=2):
            if row_number > 10_001:
                errors.append(
                    ImportErrorItem(
                        row=row_number, error="history_import_row_limit_exceeded"
                    )
                )
                break
            try:
                numeric_float = (
                    "width_mm",
                    "depth_mm",
                    "height_mm",
                    "length_mm",
                    "area_mm2",
                    "volume_mm3",
                    "actual_cost",
                    "manufacturing_hours",
                )
                payload: dict[str, object] = {
                    key: value for key, value in row.items() if value not in (None, "")
                }
                for name in numeric_float:
                    if name in payload:
                        payload[name] = float(str(payload[name]))
                if "quantity" in payload:
                    payload["quantity"] = int(str(payload["quantity"]))
                for scope_field in (
                    "included_scope",
                    "cost_scope",
                    "hours_scope",
                ):
                    if scope_field in payload:
                        payload[scope_field] = tuple(
                            item.strip()
                            for item in str(payload[scope_field]).split("|")
                            if item.strip()
                        )
                source = payload.pop("source", None)
                source_date = payload.pop("source_date", None)
                claimed_imported_by = payload.pop("imported_by", None)
                notes = payload.pop("notes", None)
                payload["provenance"] = HistoricalProvenance(
                    source=source,
                    source_date=source_date,
                    imported_by=(
                        str(imported_by)
                        if imported_by is not None
                        else claimed_imported_by
                    ),
                    notes=notes,
                )
                records.append(HistoricalRecord.model_validate(payload))
            except (ValidationError, TypeError, ValueError) as exc:
                errors.append(ImportErrorItem(row=row_number, error=str(exc)))
        if records:
            result = self.import_records(HistoricalImport(records=tuple(records)), dry_run=dry_run)
            return result.model_copy(
                update={
                    "rejected": result.rejected + len(errors),
                    "errors": tuple(errors) + result.errors,
                }
            )
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ImportResult(
            import_id=digest,
            dry_run=dry_run,
            accepted=0,
            unchanged=0,
            rejected=len(errors),
            errors=tuple(errors),
        )

    def list_records(
        self,
        *,
        limit: int,
        offset: int,
        origin: str | None = None,
    ) -> HistoricalRecordPage:
        where = " WHERE origin=?" if origin is not None else ""
        parameters = (origin,) if origin is not None else ()
        with closing(self._connect()) as db, db:
            total = db.execute(
                f"SELECT COUNT(*) FROM historical_records{where}", parameters
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT payload FROM historical_records{where} ORDER BY record_id LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            ).fetchall()
        return HistoricalRecordPage(
            items=tuple(HistoricalRecord.model_validate_json(row["payload"]) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    def _eligible(
        self,
        target: HistoricalTarget,
        *,
        include_synthetic: bool,
        candidate_records: tuple[HistoricalRecord, ...] | None = None,
    ) -> tuple[HistoricalRecord, ...]:
        records = (
            candidate_records
            if candidate_records is not None
            else self.list_records(limit=100_000, offset=0).items
        )
        excluded = set(target.exclude_record_ids)
        required_cost_scope = set(target.required_cost_scope)
        required_hours_scope = set(target.required_hours_scope)

        def scope_compatible(record: HistoricalRecord) -> bool:
            if not required_cost_scope and not required_hours_scope:
                return True
            cost_compatible = (
                bool(required_cost_scope)
                and record.actual_cost is not None
                and set(record.cost_scope) == required_cost_scope
            )
            hours_compatible = (
                bool(required_hours_scope)
                and record.manufacturing_hours is not None
                and set(record.hours_scope) == required_hours_scope
            )
            return cost_compatible or hours_compatible

        eligible = tuple(
            record
            for record in records
            if (include_synthetic or record.origin != "synthetic")
            and record.record_id not in excluded
            and record.project_id != target.exclude_project_id
            and scope_compatible(record)
        )
        return self._deduplicate_projects(eligible)

    @staticmethod
    def _deduplicate_projects(
        records: tuple[HistoricalRecord, ...]
    ) -> tuple[HistoricalRecord, ...]:
        latest: dict[str, HistoricalRecord] = {}
        for record in records:
            previous = latest.get(record.project_id)
            key = (
                record.provenance.source_date,
                record.revision,
                record.record_id,
            )
            previous_key = (
                previous.provenance.source_date,
                previous.revision,
                previous.record_id,
            ) if previous is not None else None
            if previous_key is None or key > previous_key:
                latest[record.project_id] = record
        return tuple(sorted(latest.values(), key=lambda item: item.record_id))

    def find_comparables(
        self,
        target: HistoricalTarget,
        *,
        limit: int,
        retrieval_method: str = "attribute",
        include_synthetic: bool = False,
        _candidate_records: tuple[HistoricalRecord, ...] | None = None,
    ) -> ComparableResponse:
        records = self._eligible(
            target,
            include_synthetic=include_synthetic,
            candidate_records=_candidate_records,
        )
        embedding_space = None
        values: list[HistoricalComparable] = []
        if retrieval_method == "semantic":
            if self.embedding_provider is None:
                raise ValueError("semantic_provider_unavailable")
            target_embedding = self.embedding_provider.embed(_semantic_text(target))
            embedding_space = EmbeddingSpace(
                model=target_embedding.model, dimensions=target_embedding.dimensions
            )
            ranked_pool = sorted(
                records,
                key=lambda record: (
                    -_attribute_score(target, record)[0],
                    record.record_id,
                ),
            )[: self.semantic_candidate_limit]
            for record in ranked_pool:
                record_embedding = self._record_embedding(record)
                if (
                    record_embedding.model != target_embedding.model
                    or record_embedding.dimensions != target_embedding.dimensions
                ):
                    raise ValueError("embedding_space_incompatible")
                _, _, differences, missing = _attribute_score(target, record)
                score = round(_cosine(target_embedding.vector, record_embedding.vector), 6)
                values.append(
                    HistoricalComparable(
                        record=record,
                        score=score,
                        score_components={"cosine": score},
                        differences=differences,
                        missing_fields=missing,
                    )
                )
        elif retrieval_method == "attribute":
            for record in records:
                score, components, differences, missing = _attribute_score(target, record)
                values.append(
                    HistoricalComparable(
                        record=record,
                        score=score,
                        score_components=components,
                        differences=differences,
                        missing_fields=missing,
                    )
                )
        else:
            raise ValueError("unsupported_retrieval_method")
        values.sort(key=lambda item: (-item.score, item.record.record_id))
        return ComparableResponse(
            retrieval_method=retrieval_method,
            items=tuple(values[:limit]),
            embedding_space=embedding_space,
        )

    def _record_embedding(self, record: HistoricalRecord) -> _EmbeddingResult:
        if self.embedding_provider is None:
            raise ValueError("semantic_provider_unavailable")
        payload_hash = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()
        with closing(self._connect()) as db, db:
            row = db.execute(
                "SELECT vector FROM historical_embeddings "
                "WHERE record_id=? AND payload_hash=? AND model=? AND dimensions=?",
                (
                    record.record_id,
                    payload_hash,
                    self.embedding_provider.model,
                    self.embedding_provider.dimensions,
                ),
            ).fetchone()
            if row is not None:
                try:
                    vector = validate_embedding(
                        json.loads(row["vector"]), self.embedding_provider.dimensions
                    )
                except (json.JSONDecodeError, EmbeddingProviderError, TypeError):
                    db.execute(
                        "DELETE FROM historical_embeddings "
                        "WHERE record_id=? AND payload_hash=? AND model=? AND dimensions=?",
                        (
                            record.record_id,
                            payload_hash,
                            self.embedding_provider.model,
                            self.embedding_provider.dimensions,
                        ),
                    )
                else:
                    return _StoredEmbedding(
                        vector=vector,
                        model=self.embedding_provider.model,
                        dimensions=self.embedding_provider.dimensions,
                    )
            result = self.embedding_provider.embed(_semantic_text(record))
            if (
                result.model != self.embedding_provider.model
                or result.dimensions != self.embedding_provider.dimensions
            ):
                raise ValueError("embedding_space_incompatible")
            vector = validate_embedding(list(result.vector), result.dimensions)
            db.execute(
                "INSERT INTO historical_embeddings VALUES (?, ?, ?, ?, ?)",
                (
                    record.record_id,
                    payload_hash,
                    result.model,
                    result.dimensions,
                    json.dumps(vector, separators=(",", ":")),
                ),
            )
            return _StoredEmbedding(
                vector=vector, model=result.model, dimensions=result.dimensions
            )

    def _get_records(self, ids: tuple[str, ...]) -> tuple[HistoricalRecord, ...]:
        with closing(self._connect()) as db, db:
            records = []
            for record_id in ids:
                row = db.execute(
                    "SELECT payload FROM historical_records WHERE record_id=?", (record_id,)
                ).fetchone()
                if row is None:
                    raise ValueError(f"historical_record_not_found:{record_id}")
                records.append(HistoricalRecord.model_validate_json(row["payload"]))
        return tuple(records)

    @staticmethod
    def _scale_line(
        target: HistoricalTarget,
        record: HistoricalRecord,
        concept: HistoricalConcept,
        score: float,
        *,
        evidence: str,
    ) -> _ScaledLine:
        missing: list[str] = []
        quantity_factor: float | None = 1.0
        consumption_factor: float | None = 1.0
        formula = "base"
        if concept.driver == "item":
            if target.quantity is None or record.quantity is None:
                quantity_factor = None
                missing.append("quantity_for_scaling")
            else:
                quantity_factor = target.quantity / record.quantity
            formula = "base * target_finished_item_quantity / historical_finished_item_quantity"
        driver_fields = {
            "length": "length_mm",
            "area": "area_mm2",
            "volume": "volume_mm3",
        }
        if concept.driver in driver_fields:
            field = driver_fields[concept.driver]
            target_value = getattr(target, field)
            record_value = getattr(record, field)
            if target_value is None or record_value is None:
                consumption_factor = None
                missing.append(f"{concept.driver}_for_scaling")
            elif target.quantity is not None and record.quantity is not None:
                quantity_factor = target.quantity / record.quantity
                target_per_item = target_value / target.quantity
                record_per_item = record_value / record.quantity
                consumption_factor = target_per_item / record_per_item
                formula = (
                    "base * target_finished_item_quantity / historical_finished_item_quantity "
                    f"* target_{concept.driver}_per_item / historical_{concept.driver}_per_item"
                )
            else:
                quantity_factor = 1.0
                consumption_factor = target_value / record_value
                formula = (
                    f"base * target_total_{concept.driver} / historical_total_{concept.driver}"
                )
        reference_material = concept.material or record.material
        material_must_match = concept.kind == "material" or evidence == "global_analogy"
        if material_must_match and (
            target.material is None
            or reference_material is None
            or target.material.casefold() != reference_material.casefold()
        ):
            missing.append("material_rate_or_compatible_history")
        reference_finish = concept.finish or record.finish
        finish_must_match = concept.kind == "finish" or evidence == "global_analogy"
        if finish_must_match and (
            target.finish is None
            or reference_finish is None
            or target.finish.casefold() != reference_finish.casefold()
        ):
            missing.append("finish_rate_or_compatible_history")
        factor = (
            quantity_factor * consumption_factor
            if quantity_factor is not None
            and consumption_factor is not None
            and not missing
            else None
        )
        cost_allowed = target.currency is not None and record.currency == target.currency
        if concept.cost is not None and not cost_allowed:
            missing.append("currency_compatible_comparable")
        return _ScaledLine(
            concept_id=concept.concept_id,
            kind=concept.kind,
            record_id=record.record_id,
            score=score,
            base_cost=concept.cost,
            base_hours=concept.hours,
            quantity_factor=quantity_factor,
            consumption_factor=consumption_factor,
            cost=(
                concept.cost * factor
                if concept.cost is not None and factor is not None and cost_allowed
                else None
            ),
            hours=(
                concept.hours * factor
                if concept.hours is not None and factor is not None
                else None
            ),
            evidence=evidence,
            formula=formula,
            missing_data=tuple(sorted(set(missing))),
        )

    def estimate(
        self,
        target: HistoricalTarget,
        *,
        comparable_ids: tuple[str, ...] = (),
        include_synthetic: bool = False,
    ) -> HistoricalEstimate:
        if not comparable_ids:
            comparable_ids = tuple(
                item.record.record_id
                for item in self.find_comparables(
                    target, limit=3, include_synthetic=include_synthetic
                ).items
            )
        records = self._get_records(comparable_ids) if comparable_ids else ()
        excluded_ids = set(target.exclude_record_ids)
        for record in records:
            if record.record_id in excluded_ids or (
                target.exclude_project_id is not None
                and record.project_id == target.exclude_project_id
            ):
                raise ValueError(f"excluded_historical_record:{record.record_id}")
        records = self._deduplicate_projects(records)
        if not include_synthetic and any(record.origin == "synthetic" for record in records):
            raise ValueError("synthetic_history_requires_explicit_opt_in")
        missing: set[str] = set()
        assumptions: set[str] = set()
        if not records:
            missing.add("compatible_comparable")
        if not target.required_cost_scope:
            missing.add("required_cost_scope")
        if not target.required_hours_scope:
            missing.add("required_hours_scope")
        required_cost_scope = set(target.required_cost_scope)
        required_hours_scope = set(target.required_hours_scope)
        for record in records:
            if (
                required_cost_scope
                and record.cost_scope
                and set(record.cost_scope) != required_cost_scope
            ):
                raise ValueError(
                    f"incompatible_historical_scope:{record.record_id}:cost"
                )
            if (
                required_hours_scope
                and record.hours_scope
                and set(record.hours_scope) != required_hours_scope
            ):
                raise ValueError(
                    f"incompatible_historical_scope:{record.record_id}:hours"
                )
        lines: list[_ScaledLine] = []
        for record in records:
            score = max(_attribute_score(target, record)[0], 0.01)
            concepts = record.concepts
            evidence = "concept_breakdown"
            if not concepts:
                driver = "area" if target.area_mm2 and record.area_mm2 else "item"
                concepts = (
                    HistoricalConcept(
                        concept_id="overall",
                        kind="other",
                        driver=driver,
                        cost=record.actual_cost,
                        hours=record.manufacturing_hours,
                    ),
                )
                evidence = "global_analogy"
                assumptions.add(
                    "Global analogy used because the historical record has no concept breakdown."
                )
            for concept in concepts:
                line = self._scale_line(
                    target, record, concept, score, evidence=evidence
                )
                missing.update(line.missing_data)
                lines.append(line)
        contributors: list[EstimateContributor] = []
        scenarios: list[HistoricalEstimateScenario] = []
        for record in records:
            record_lines = [line for line in lines if line.record_id == record.record_id]
            record_cost_compatible = (
                bool(target.required_cost_scope)
                and record.actual_cost is not None
                and set(record.cost_scope) == set(target.required_cost_scope)
            )
            record_hours_compatible = (
                bool(target.required_hours_scope)
                and record.manufacturing_hours is not None
                and set(record.hours_scope) == set(target.required_hours_scope)
            )
            record_contributors = tuple(
                EstimateContributor(
                    concept_id=line.concept_id,
                    kind=line.kind,
                    comparable_ids=(record.record_id,),
                    formula=line.formula,
                    base_cost=_round(line.base_cost, 2),
                    base_hours=_round(line.base_hours, 3),
                    quantity_factor=_round(line.quantity_factor),
                    consumption_factor=_round(line.consumption_factor),
                    unit_rate_factor=1.0,
                    estimated_cost=(
                        _round(line.cost, 2)
                        if record_cost_compatible
                        else None
                    ),
                    estimated_hours=(
                        _round(line.hours, 3)
                        if record_hours_compatible
                        else None
                    ),
                    evidence=line.evidence,
                    missing_data=line.missing_data,
                )
                for line in record_lines
            )
            contributors.extend(record_contributors)
            cost_values = [
                item.estimated_cost
                for item in record_contributors
                if item.base_cost is not None
            ]
            hour_values = [
                item.estimated_hours
                for item in record_contributors
                if item.base_hours is not None
            ]
            cost_total = (
                round(sum(value for value in cost_values if value is not None), 2)
                if cost_values and all(value is not None for value in cost_values)
                else None
            )
            hours_total = (
                round(sum(value for value in hour_values if value is not None), 3)
                if hour_values and all(value is not None for value in hour_values)
                else None
            )
            scenarios.append(
                HistoricalEstimateScenario(
                    record_id=record.record_id,
                    weight=max(_attribute_score(target, record)[0], 0.01),
                    contributors=record_contributors,
                    cost_total=cost_total,
                    hours_total=hours_total,
                )
            )

        def weighted_scenario_total(field: str, digits: int) -> float | None:
            present = [
                (getattr(scenario, field), scenario.weight)
                for scenario in scenarios
                if getattr(scenario, field) is not None
            ]
            if not present:
                return None
            return round(
                sum(value * weight for value, weight in present)
                / sum(weight for _, weight in present),
                digits,
            )

        cost_subtotal = weighted_scenario_total("cost_total", 2)
        manufacturing_hours = weighted_scenario_total("hours_total", 3)
        if not target.required_cost_scope:
            cost_subtotal = None
        if not target.required_hours_scope:
            manufacturing_hours = None
        complete_costs = [s.cost_total for s in scenarios if s.cost_total is not None]
        complete_hours = [s.hours_total for s in scenarios if s.hours_total is not None]
        cost_range = (
            (round(min(complete_costs), 2), round(max(complete_costs), 2))
            if len(complete_costs) >= 2
            else None
        )
        hours_range = (
            (round(min(complete_hours), 3), round(max(complete_hours), 3))
            if len(complete_hours) >= 2
            else None
        )
        scenarios_by_record = {item.record_id: item for item in scenarios}
        cost_records = [
            record
            for record in records
            if scenarios_by_record[record.record_id].cost_total is not None
        ]
        hours_records = [
            record
            for record in records
            if scenarios_by_record[record.record_id].hours_total is not None
        ]
        non_actual_cost_basis = any(
            record.cost_basis not in (None, "actual") for record in cost_records
        )
        if non_actual_cost_basis:
            assumptions.add(
                "At least one comparable is a quote or budget, not an executed actual cost."
            )
        cost_global_analogy = any(
            item.evidence == "global_analogy" and item.estimated_cost is not None
            for item in contributors
        )
        hours_global_analogy = any(
            item.evidence == "global_analogy" and item.estimated_hours is not None
            for item in contributors
        )
        if not target.required_cost_scope or not cost_records:
            cost_uncertainty = "not_estimable"
        elif non_actual_cost_basis or cost_global_analogy or any(
            record.origin == "synthetic" for record in cost_records
        ):
            cost_uncertainty = "high"
        elif len(cost_records) == 1:
            cost_uncertainty = "medium"
        else:
            cost_uncertainty = "low"
        if not target.required_hours_scope or not hours_records:
            hours_uncertainty = "not_estimable"
        elif hours_global_analogy or any(
            record.origin == "synthetic" for record in hours_records
        ):
            hours_uncertainty = "high"
        elif len(hours_records) == 1:
            hours_uncertainty = "medium"
        else:
            hours_uncertainty = "low"
        uncertainty_rank = {
            "not_estimable": 3,
            "high": 2,
            "medium": 1,
            "low": 0,
        }
        uncertainty = max(
            (cost_uncertainty, hours_uncertainty),
            key=lambda value: uncertainty_rank[value],
        )
        return HistoricalEstimate(
            basis_revision=target.basis_revision,
            currency=target.currency,
            effective_cost_scope=target.required_cost_scope,
            effective_hours_scope=target.required_hours_scope,
            comparable_ids=tuple(record.record_id for record in records),
            result_provenance=tuple(
                EstimateProvenance(
                    record_id=record.record_id,
                    origin=record.origin,
                    source=record.provenance.source,
                    source_date=record.provenance.source_date,
                    cost_basis=record.cost_basis,
                    contributes_cost=(
                        scenarios_by_record[record.record_id].cost_total is not None
                    ),
                    contributes_hours=(
                        scenarios_by_record[record.record_id].hours_total is not None
                    ),
                    cost_scope=record.cost_scope,
                    hours_scope=record.hours_scope,
                )
                for record in records
            ),
            contributors=tuple(contributors),
            scenarios=tuple(scenarios),
            cost_subtotal=cost_subtotal,
            manufacturing_hours=manufacturing_hours,
            cost_range=cost_range,
            hours_range=hours_range,
            uncertainty=uncertainty,
            cost_uncertainty=cost_uncertainty,
            hours_uncertainty=hours_uncertainty,
            missing_data=tuple(sorted(missing)),
            assumptions=tuple(sorted(assumptions)),
        )

    def provisional_scenarios(
        self,
        snapshot: ProvisionalScenarioSnapshot,
        *,
        limit: int = 3,
        retrieval_method: str = "attribute",
    ) -> ProvisionalScenarioResponse:
        if not 1 <= limit <= 10:
            raise ValueError("provisional_scenario_limit_out_of_range")
        if retrieval_method not in {"attribute", "semantic"}:
            raise ValueError("unsupported_retrieval_method")

        common_assumptions = (
            ProvisionalAssumption(
                code="provisional_bom",
                label="Provisional auto-reviewed BOM",
                detail=(
                    "Geometry and component counts remain machine-reviewed hypotheses; "
                    "they are not promoted to confirmed drawing facts."
                ),
                state="provisional",
            ),
            ProvisionalAssumption(
                code="one_finished_item",
                label="One conditional finished item",
                detail=(
                    "Every scenario prices one finished item. This is a scenario condition, "
                    "not a physical occurrence inferred from the drawing."
                ),
                state="conditional",
            ),
        )

        def abstain(*reasons: str) -> ProvisionalScenarioResponse:
            return ProvisionalScenarioResponse(
                run_id=snapshot.run_id,
                proposal_revision=snapshot.proposal_revision,
                review_revision=snapshot.review_revision,
                status="not_estimable",
                assumptions=common_assumptions,
                scenarios=(),
                missing_data=tuple(sorted(set(reasons))),
            )

        if snapshot.auto_review_status in {"conflict", "abstained"}:
            return abstain("auto_review_status")

        rows = tuple(
            row for row in snapshot.rows if row.occurrence_status == "provisional"
        )
        if not rows:
            return abstain("provisional_bom_rows")

        quantity_failure = any(
            row.quantity.state != "hypothesis"
            or row.quantity.review_status != "accepted"
            or row.quantity.value is None
            or not {"quantity_basis", "duplicate_scan"}.issubset(
                row.quantity.check_kinds
            )
            or len(row.scenario_occurrence_ids) != row.quantity.value
            or len(set(row.scenario_occurrence_ids))
            != len(row.scenario_occurrence_ids)
            for row in rows
        )
        if quantity_failure:
            return abstain("provisional_quantity_evidence")

        def accepted_dimension(value) -> bool:
            return (
                value.state == "hypothesis"
                and value.review_status == "accepted"
                and value.value_mm is not None
                and bool(value.check_ids)
            )

        def accepted_known_text(value) -> bool:
            return value.value is None or (
                value.state == "hypothesis"
                and value.review_status == "accepted"
                and bool(value.check_ids)
            )

        if any(
            not accepted_known_text(row.material)
            or not accepted_known_text(row.finish)
            for row in rows
        ):
            return abstain("provisional_material_finish_evidence")

        materials = {row.material.value for row in rows if row.material.value}
        finishes = {row.finish.value for row in rows if row.finish.value}
        material_is_heterogeneous = len(materials) > 1
        finish_is_heterogeneous = len(finishes) > 1
        known_material = next(iter(materials), None) if len(materials) == 1 else None
        known_finish = next(iter(finishes), None) if len(finishes) == 1 else None
        material_is_conditional = any(row.material.value is None for row in rows)
        finish_is_conditional = any(row.finish.value is None for row in rows)

        complete_length = all(accepted_dimension(row.length) for row in rows)
        complete_area = complete_length and all(
            accepted_dimension(row.width) for row in rows
        )
        complete_volume = complete_area and all(
            accepted_dimension(row.thickness) for row in rows
        )
        length_mm = (
            sum(
                float(row.length.value_mm) * int(row.quantity.value)
                for row in rows
            )
            if complete_length
            else None
        )
        area_mm2 = (
            sum(
                float(row.length.value_mm)
                * float(row.width.value_mm)
                * int(row.quantity.value)
                for row in rows
            )
            if complete_area
            else None
        )
        volume_mm3 = (
            sum(
                float(row.length.value_mm)
                * float(row.width.value_mm)
                * float(row.thickness.value_mm)
                * int(row.quantity.value)
                for row in rows
            )
            if complete_volume
            else None
        )
        component_ids = tuple(row.component_id for row in rows)
        occurrence_ids = tuple(
            occurrence
            for row in rows
            for occurrence in row.scenario_occurrence_ids
        )
        source_refs = tuple(
            dict.fromkeys(
                reference
                for row in rows
                for reference in (
                    *row.source_refs,
                    *row.quantity.source_refs,
                    *row.quantity.premise_refs,
                    *row.length.dependency_refs,
                    *row.width.dependency_refs,
                    *row.thickness.dependency_refs,
                )
            )
        )
        scaling_basis = ProvisionalScalingBasis(
            component_ids=component_ids,
            scenario_occurrence_ids=occurrence_ids,
            length_mm=length_mm,
            area_mm2=area_mm2,
            volume_mm3=volume_mm3,
            source_refs=source_refs,
        )

        retrieval_target = HistoricalTarget(
            area_mm2=area_mm2,
            length_mm=length_mm,
            volume_mm3=volume_mm3,
            quantity=1,
            material=known_material,
            finish=known_finish,
            basis_revision=(
                f"provisional:{snapshot.run_id}:proposal:{snapshot.proposal_revision}:"
                f"review:{snapshot.review_revision}"
            ),
        )

        def driver_is_available(driver: str, record: HistoricalRecord) -> bool:
            if driver == "fixed":
                return True
            if driver == "item":
                return record.quantity is not None
            field = {
                "length": "length_mm",
                "area": "area_mm2",
                "volume": "volume_mm3",
            }[driver]
            return getattr(retrieval_target, field) is not None and getattr(
                record, field
            ) is not None

        def constraint_is_compatible(
            kind: str,
            explicit_value: str | None,
            record_value: str | None,
        ) -> bool:
            if kind == "material":
                if material_is_heterogeneous:
                    return False
                target_value = known_material
            elif kind == "finish":
                if finish_is_heterogeneous:
                    return False
                target_value = known_finish
            else:
                return True
            reference_value = explicit_value or record_value
            if reference_value is None:
                return False
            return target_value is None or reference_value.casefold() == target_value.casefold()

        def declared_attributes_are_compatible(record: HistoricalRecord) -> bool:
            if (
                known_material is not None
                and record.material is not None
                and record.material.casefold() != known_material.casefold()
            ):
                return False
            if (
                known_finish is not None
                and record.finish is not None
                and record.finish.casefold() != known_finish.casefold()
            ):
                return False
            if material_is_heterogeneous and record.material is not None:
                return False
            if finish_is_heterogeneous and record.finish is not None:
                return False
            return True

        def metric_is_eligible(record: HistoricalRecord, metric: str) -> bool:
            if record.origin == "synthetic" or record.family is None:
                return False
            if not declared_attributes_are_compatible(record):
                return False
            total = (
                record.actual_cost
                if metric == "cost"
                else record.manufacturing_hours
            )
            scope = record.cost_scope if metric == "cost" else record.hours_scope
            if total is None or not scope:
                return False
            if metric == "cost" and (
                record.currency is None
                or record.material is None
                or record.finish is None
            ):
                return False
            if not record.concepts:
                driver = (
                    "area"
                    if retrieval_target.area_mm2 is not None
                    and record.area_mm2 is not None
                    else "item"
                )
                return (
                    driver_is_available(driver, record)
                    and constraint_is_compatible(
                        "material", None, record.material
                    )
                    and constraint_is_compatible("finish", None, record.finish)
                )
            bearing = tuple(
                concept
                for concept in record.concepts
                if getattr(concept, metric) is not None
            )
            return bool(bearing) and all(
                driver_is_available(concept.driver, record)
                and constraint_is_compatible(
                    concept.kind,
                    concept.material if concept.kind == "material" else concept.finish,
                    record.material if concept.kind == "material" else record.finish,
                )
                for concept in bearing
            )

        listed_records = self.list_records(limit=100_000, offset=0).items
        eligibility = {
            record.record_id: (
                metric_is_eligible(record, "cost"),
                metric_is_eligible(record, "hours"),
            )
            for record in listed_records
        }
        cost_candidates = tuple(
            record for record in listed_records if eligibility[record.record_id][0]
        )
        hours_candidates = tuple(
            record for record in listed_records if eligibility[record.record_id][1]
        )

        def ranked(candidates: tuple[HistoricalRecord, ...]):
            if not candidates:
                return ()
            return self.find_comparables(
                retrieval_target,
                limit=limit,
                retrieval_method=retrieval_method,
                include_synthetic=False,
                _candidate_records=candidates,
            ).items

        rankings = (ranked(cost_candidates), ranked(hours_candidates))
        compatible: list[HistoricalRecord] = []
        positions = [0, 0]
        while len(compatible) < limit and any(
            positions[index] < len(values) for index, values in enumerate(rankings)
        ):
            for index, values in enumerate(rankings):
                if positions[index] >= len(values):
                    continue
                record = values[positions[index]].record
                positions[index] += 1
                if all(item.record_id != record.record_id for item in compatible):
                    compatible.append(record)
                    if len(compatible) == limit:
                        break
        if not compatible:
            reasons = ["compatible_non_synthetic_reference"]
            if material_is_heterogeneous or finish_is_heterogeneous:
                reasons.append("heterogeneous_material_finish")
            return abstain(*reasons)

        scenarios: list[ProvisionalHistoricalScenario] = []
        for record in compatible:
            cost_is_eligible, hours_is_eligible = eligibility[record.record_id]
            target_material = known_material or record.material
            target_finish = known_finish or record.finish
            target = HistoricalTarget(
                family=record.family,
                area_mm2=area_mm2,
                length_mm=length_mm,
                volume_mm3=volume_mm3,
                quantity=1,
                material=target_material,
                finish=target_finish,
                currency=record.currency if cost_is_eligible else None,
                required_cost_scope=record.cost_scope if cost_is_eligible else (),
                required_hours_scope=record.hours_scope if hours_is_eligible else (),
                basis_revision=(
                    f"provisional:{snapshot.run_id}:proposal:{snapshot.proposal_revision}:"
                    f"review:{snapshot.review_revision}:reference:{record.record_id}"
                ),
            )
            estimate = self.estimate(
                target,
                comparable_ids=(record.record_id,),
                include_synthetic=False,
            )
            assumptions = list(common_assumptions)
            assumptions.append(
                ProvisionalAssumption(
                    code="reference_family",
                    label="Reference family condition",
                    detail=(
                        f"This scenario applies only if the furniture belongs to the "
                        f"historical reference family '{record.family}'."
                    ),
                    state="conditional",
                )
            )
            if record.material is None:
                assumptions.append(
                    ProvisionalAssumption(
                        code="reference_material_unreported",
                        label="Reference material not reported",
                        detail=(
                            f"Reference '{record.record_id}' does not publish a material; "
                            "this hours scenario does not invent one."
                        ),
                        state="conditional",
                    )
                )
            elif material_is_conditional:
                assumptions.append(
                    ProvisionalAssumption(
                        code="reference_material",
                        label="Reference material condition",
                        detail=(
                            f"This scenario assumes the historical reference material "
                            f"'{record.material}'."
                        ),
                        state="conditional",
                    )
                )
            if record.finish is None:
                assumptions.append(
                    ProvisionalAssumption(
                        code="reference_finish_unreported",
                        label="Reference finish not reported",
                        detail=(
                            f"Reference '{record.record_id}' does not publish a finish; "
                            "this hours scenario does not invent one."
                        ),
                        state="conditional",
                    )
                )
            elif finish_is_conditional:
                assumptions.append(
                    ProvisionalAssumption(
                        code="reference_finish",
                        label="Reference finish condition",
                        detail=(
                            f"This scenario assumes the historical reference finish "
                            f"'{record.finish}'."
                        ),
                        state="conditional",
                    )
                )
            assumptions.append(
                ProvisionalAssumption(
                    code="reference_economic_context",
                    label="Reference economic context",
                    detail=(
                        f"Currency and metric scopes come only from reference "
                        f"'{record.record_id}' ({record.origin}/{record.cost_basis or 'hours-only'}); "
                        "this result is not a quote."
                    ),
                    state="conditional",
                )
            )
            scenario_missing_data = tuple(
                value
                for value in estimate.missing_data
                if not (
                    (value == "required_cost_scope" and not cost_is_eligible)
                    or (value == "required_hours_scope" and not hours_is_eligible)
                )
            )
            scenarios.append(
                ProvisionalHistoricalScenario(
                    scenario_id=(
                        f"provisional:{snapshot.run_id}:{snapshot.proposal_revision}:"
                        f"{snapshot.review_revision}:{record.record_id}"
                    ),
                    comparable_id=record.record_id,
                    source_effective_date=record.provenance.source_date,
                    condition=ProvisionalScenarioCondition(
                        family=record.family,
                        material=record.material,
                        finish=record.finish,
                        currency=record.currency if cost_is_eligible else None,
                        cost_scope=record.cost_scope if cost_is_eligible else (),
                        hours_scope=record.hours_scope if hours_is_eligible else (),
                    ),
                    currency=record.currency if cost_is_eligible else None,
                    scaling_basis=scaling_basis,
                    assumptions=tuple(assumptions),
                    contributors=estimate.contributors,
                    result_provenance=estimate.result_provenance,
                    cost_subtotal=estimate.cost_subtotal,
                    manufacturing_hours=estimate.manufacturing_hours,
                    cost_range=estimate.cost_range,
                    hours_range=estimate.hours_range,
                    cost_uncertainty=estimate.cost_uncertainty,
                    hours_uncertainty=estimate.hours_uncertainty,
                    missing_data=scenario_missing_data,
                )
            )
        return ProvisionalScenarioResponse(
            run_id=snapshot.run_id,
            proposal_revision=snapshot.proposal_revision,
            review_revision=snapshot.review_revision,
            status="provisional",
            assumptions=common_assumptions,
            scenarios=tuple(scenarios),
            missing_data=(),
        )
