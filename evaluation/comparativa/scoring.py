"""Independent matching and per-family metrics (no global score).

Components are matched to reference components by dimension values alone,
one-to-one, *before* any precision/recall or quantity comparison.  The match
never uses keys, roles or reference-supplied pairings.

Matching rules (documented because they are a choice):
* A predicted component needs at least two known dimensions.
* Its known values are assigned to distinct reference dimension slots by best
  fit, independent of field labels (an orthographic rectangle shows any two of
  a part's three dimensions).  Every assigned difference must be within
  ``match_tolerance_mm``.
* Pairs are taken greedily by (cost, predicted key, reference key); ties are
  therefore deterministic.  This is not a global optimum; it is an auditable
  rule.
"""

from __future__ import annotations

from collections import Counter
from itertools import permutations
from typing import Any

from .model import (
    DIMENSION_FIELDS,
    CaseMeta,
    Component,
    RefComponent,
    ReferenceCase,
    parse_component,
)

MIN_KNOWN_DIMENSIONS = 2


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def _assign(
    component: Component, reference: RefComponent, tolerance: float
) -> tuple[float, dict[str, str]] | None:
    known = [(name, component.dimensions_mm[name]) for name in DIMENSION_FIELDS if component.dimensions_mm[name] is not None]
    slots = [name for name in DIMENSION_FIELDS if reference.dimensions[name].value is not None]
    if len(known) < MIN_KNOWN_DIMENSIONS or len(known) > len(slots):
        return None
    best: tuple[tuple[float, tuple[str, ...]], dict[str, str]] | None = None
    for chosen in permutations(slots, len(known)):
        diffs = [abs(value - reference.dimensions[slot].value) for (_, value), slot in zip(known, chosen)]  # type: ignore[operator]
        if any(diff > tolerance for diff in diffs):
            continue
        rank = (sum(diffs), chosen)
        if best is None or rank < best[0]:
            best = (rank, {name: slot for (name, _), slot in zip(known, chosen)})
    return None if best is None else (best[0][0], best[1])


def match_components(
    predicted: list[Component], reference: tuple[RefComponent, ...], match_tolerance_mm: float
) -> list[tuple[Component, RefComponent, dict[str, str]]]:
    candidates = []
    for p in predicted:
        for r in reference:
            assigned = _assign(p, r, match_tolerance_mm)
            if assigned is not None:
                candidates.append((assigned[0], p.key, r.key, p, r, assigned[1]))
    candidates.sort(key=lambda item: item[:3])
    used_p: set[str] = set()
    used_r: set[str] = set()
    pairs = []
    for _, pk, rk, p, r, mapping in candidates:
        if pk in used_p or rk in used_r:
            continue
        used_p.add(pk)
        used_r.add(rk)
        pairs.append((p, r, mapping))
    return pairs


class _Group:
    def __init__(self) -> None:
        self.cases: set[str] = set()
        self.cases_with_reference: set[str] = set()
        self.cases_without_reference: set[str] = set()
        self.status: Counter[str] = Counter()
        self.reasons: Counter[str] = Counter()
        self.observations_scored = 0
        self.c: Counter[str] = Counter()
        self.errors: list[float] = []
        self.durations: list[float] = []
        self.costs: list[float] = []

    def finalize(self) -> dict[str, Any]:
        c = self.c
        precision = _ratio(c["matched"], c["predicted_types"])
        recall = _ratio(c["matched"], c["reference_types"])
        qty_precision = _ratio(c["quantity_true_positive"], c["quantity_predicted"])
        qty_recall = _ratio(c["quantity_true_positive"], c["quantity_reference"])
        unidentifiable = c["unidentifiable_fields"]
        resolvable = c["resolvable_fields_matched"]
        return {
            "sample": {
                "cases": len(self.cases),
                "observations": sum(self.status.values()),
                "observations_scored": self.observations_scored,
                "cases_with_reference": len(self.cases_with_reference),
                "cases_without_reference": len(self.cases_without_reference),
                "status_counts": dict(sorted(self.status.items())),
                "reason_counts": dict(sorted(self.reasons.items())),
            },
            "dimensions": {
                "eligible_fields": c["dim_eligible"],
                "predicted_fields": c["dim_covered"],
                "coverage": _ratio(c["dim_covered"], c["dim_eligible"]),
                "mae_mm": _ratio(sum(self.errors), len(self.errors)),
                "within_tolerance": c["dim_within"],
                "within_tolerance_rate": _ratio(c["dim_within"], len(self.errors)),
                "role_label_mismatches": c["role_mismatch"],
            },
            "identity": {
                "reference_types": c["reference_types"],
                "predicted_types": c["predicted_types"],
                "matched": c["matched"],
                "false_positives": c["predicted_types"] - c["matched"],
                "omissions": c["reference_types"] - c["matched"],
                "precision": precision,
                "recall": recall,
                "f1": _f1(precision, recall),
                "quantity": {
                    "compared_components": c["quantity_compared"],
                    "exact_matches": c["quantity_exact"],
                    "exact_rate": _ratio(c["quantity_exact"], c["quantity_compared"]),
                    "reference_total": c["quantity_reference"],
                    "predicted_total": c["quantity_predicted"],
                    "true_positive": c["quantity_true_positive"],
                    "precision": qty_precision,
                    "recall": qty_recall,
                    "f1": _f1(qty_precision, qty_recall),
                },
            },
            "abstention": {
                "unidentifiable_fields": unidentifiable,
                "correct_abstentions": c["correct_abstentions"],
                "correct_abstention_rate": _ratio(c["correct_abstentions"], unidentifiable),
                "asserted_unidentifiable": c["asserted_unidentifiable"],
                "asserted_matching_reference_value": c["asserted_matching"],
                "resolvable_fields_in_matched_components": resolvable,
                "resolvable_left_unknown": c["resolvable_left_unknown"],
                "over_abstention_rate": _ratio(c["resolvable_left_unknown"], resolvable),
            },
            "fields_without_reference": {
                "fields": c["fields_unannotated"],
                "cases_without_reference": len(self.cases_without_reference),
            },
            "resources": {
                "observations": len(self.durations),
                "duration_s_total": sum(self.durations),
                "duration_s_mean": _ratio(sum(self.durations), len(self.durations)),
                "model_calls": c["model_calls"],
                "tool_calls": c["tool_calls"],
                "input_tokens": c["input_tokens"],
                "output_tokens": c["output_tokens"],
                "cost_reported_observations": len(self.costs),
                "cost_eur_reported_total": sum(self.costs) if self.costs else None,
            },
        }


def _score_observation(
    group: _Group, components: list[Component], reference: ReferenceCase,
    tolerance_mm: float, match_tolerance_mm: float,
) -> None:
    c = group.c
    pairs = match_components(components, reference.components, match_tolerance_mm)
    c["matched"] += len(pairs)
    c["predicted_types"] += len(components)
    c["reference_types"] += len(reference.components)
    group.observations_scored += 1

    by_reference = {r.key: (p, mapping) for p, r, mapping in pairs}
    for ref in reference.components:
        quantity_ref = ref.quantity
        if quantity_ref.value is not None:
            c["quantity_reference"] += int(quantity_ref.value)
        paired = by_reference.get(ref.key)
        predicted, mapping = paired if paired else (None, {})
        assigned_slots = {slot: name for name, slot in mapping.items()}

        for slot in DIMENSION_FIELDS:
            field_ref = ref.dimensions[slot]
            if field_ref.value is None:
                c["fields_unannotated"] += 1 if field_ref.identifiable is None else 0
                continue
            name = assigned_slots.get(slot)
            predicted_value = predicted.dimensions_mm[name] if predicted and name else None
            if field_ref.identifiable is None:
                c["fields_unannotated"] += 1
            elif field_ref.identifiable:
                c["dim_eligible"] += 1
                if predicted is not None:
                    c["resolvable_fields_matched"] += 1
                if predicted_value is None:
                    if predicted is not None:
                        c["resolvable_left_unknown"] += 1
                    continue
                c["dim_covered"] += 1
                error = abs(predicted_value - field_ref.value)
                group.errors.append(error)
                c["dim_within"] += error <= tolerance_mm
                c["role_mismatch"] += name != slot
            else:
                if predicted is None:
                    continue
                c["unidentifiable_fields"] += 1
                if predicted_value is None:
                    c["correct_abstentions"] += 1
                else:
                    c["asserted_unidentifiable"] += 1
                    c["asserted_matching"] += abs(predicted_value - field_ref.value) <= tolerance_mm

        if quantity_ref.identifiable is None:
            c["fields_unannotated"] += 1
        # Quantity: compared only after matching, from the matched pair.
        if predicted is None:
            continue
        if quantity_ref.identifiable is False:
            c["unidentifiable_fields"] += 1
            if predicted.quantity is None:
                c["correct_abstentions"] += 1
            else:
                c["asserted_unidentifiable"] += 1
                c["asserted_matching"] += quantity_ref.value is not None and predicted.quantity == int(quantity_ref.value)
        elif quantity_ref.identifiable:
            c["resolvable_fields_matched"] += 1
            if predicted.quantity is None:
                c["resolvable_left_unknown"] += 1
        if quantity_ref.value is not None and predicted.quantity is not None:
            expected = int(quantity_ref.value)
            c["quantity_compared"] += 1
            c["quantity_exact"] += predicted.quantity == expected
            c["quantity_true_positive"] += min(predicted.quantity, expected)
    for component in components:
        if component.quantity is not None:
            c["quantity_predicted"] += component.quantity


def score_outputs(
    outputs: list[dict[str, Any]],
    metas: dict[str, CaseMeta],
    references: dict[str, ReferenceCase | None],
    *,
    tolerance_mm: float,
    match_tolerance_mm: float,
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Return ``{variant: {family: {split: metrics}}}`` (no cross-family pooling)."""

    groups: dict[tuple[str, str, str], _Group] = {}
    for output in sorted(outputs, key=lambda o: (o["variant"], o["case_id"], o["repetition"])):
        meta = metas[output["case_id"]]
        group = groups.setdefault((output["variant"], meta.family, meta.split), _Group())
        group.cases.add(output["case_id"])
        group.status[output["status"]] += 1
        if output.get("reason"):
            group.reasons[f"{output['status']}:{output['reason']}"] += 1
        if output["status"] in {"ok", "failed"}:
            group.durations.append(float(output["timing"]["duration_s"]))
        usage = output.get("usage") or {}
        for field_name in ("model_calls", "tool_calls", "input_tokens", "output_tokens"):
            if isinstance(usage.get(field_name), int):
                group.c[field_name] += usage[field_name]
        if isinstance(usage.get("cost_eur"), (int, float)) and not isinstance(usage["cost_eur"], bool):
            group.costs.append(float(usage["cost_eur"]))
        if output["status"] != "ok":
            continue
        reference = references.get(output["case_id"])
        if reference is None:
            group.cases_without_reference.add(output["case_id"])
            continue
        group.cases_with_reference.add(output["case_id"])
        components = [parse_component(item) for item in output["components"]]
        _score_observation(group, components, reference, tolerance_mm, match_tolerance_mm)
    result: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for (variant, family, split), group in sorted(groups.items()):
        result.setdefault(variant, {}).setdefault(family, {})[split] = group.finalize()
    return result
