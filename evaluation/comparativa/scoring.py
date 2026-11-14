"""Independent matching and per-family metrics (no global score).

Components are matched to reference components by dimension values alone,
one-to-one, *before* any precision/recall or quantity comparison.  The match
never uses keys, roles or reference-supplied pairings, and nothing in it
depends on key order.

Matching rules (documented because they are a choice):
* A predicted component needs at least two known dimensions that fit the
  reference within ``match_tolerance_mm``: the best subset of >= 2 values is
  assigned to distinct reference dimension slots, independent of field labels
  (an orthographic rectangle shows any two of a part's three dimensions).
  The remaining known values go to the remaining slots and are then scored as
  errors (identifiable slot) or inventions (unidentifiable slot).
* Reference components with identical dimensions form one *class*.  Predicted
  components are matched to classes greedily by (fit, content signature,
  class dimensions); keys are never used, so equal answers score equally under
  any naming.
* Inside a class the assignment of predicted to reference components is the one
  most favourable to the prediction (fewest inventions, then fewest resolvable
  fields left unknown, then least dimension error, then most exact quantities).
  The ambiguity is declared, not hidden: indistinguishable references cannot
  penalise a prediction for how they happen to be listed.
* Failed observations contribute their reference types and resolvable fields to
  the coverage/recall denominators (no prediction = nothing found); a labelled
  ``*_conditioned_on_ok`` view excludes them.  ``not_evaluated`` and
  ``not_applicable`` stay out of every denominator.
* Quantity precision/recall cover identifiable reference quantities only;
  quantities the views cannot establish are reported under abstention.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations, permutations
from typing import Any

from .model import (
    DIMENSION_FIELDS,
    CaseMeta,
    ComparisonError,
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


def _slots(reference: RefComponent) -> list[str]:
    return [name for name in DIMENSION_FIELDS if reference.dimensions[name].value is not None]


def _assign(
    component: Component, reference: RefComponent, tolerance: float
) -> tuple[tuple[int, float], dict[str, str]] | None:
    """Best fit of the component's known values to the reference slots.

    Returns ``(rank, mapping)``; rank is ``(-fitted_values, summed_error)`` so
    smaller is better.  ``mapping`` maps predicted field -> reference slot and
    includes values that did not fit (they become errors or inventions).
    """

    known = [
        (name, component.dimensions_mm[name])
        for name in DIMENSION_FIELDS
        if component.dimensions_mm[name] is not None
    ]
    slots = _slots(reference)
    if len(known) < MIN_KNOWN_DIMENSIONS:
        return None
    best: tuple[tuple[int, float, tuple[str, ...]], dict[str, str]] | None = None
    for size in range(min(len(known), len(slots)), MIN_KNOWN_DIMENSIONS - 1, -1):
        for subset in combinations(range(len(known)), size):
            for chosen in permutations(slots, size):
                diffs = [
                    abs(known[i][1] - reference.dimensions[slot].value)  # type: ignore[operator]
                    for i, slot in zip(subset, chosen, strict=True)
                ]
                if any(diff > tolerance for diff in diffs):
                    continue
                mapping = {known[i][0]: slot for i, slot in zip(subset, chosen, strict=True)}
                leftover_names = [known[i][0] for i in range(len(known)) if i not in subset]
                leftover_slots = [slot for slot in slots if slot not in chosen]
                extra = 0.0
                if leftover_names and leftover_slots:
                    options = []
                    for pick in permutations(leftover_slots, min(len(leftover_names), len(leftover_slots))):
                        pairs = list(zip(leftover_names, pick, strict=False))
                        cost = sum(
                            abs(component.dimensions_mm[n] - reference.dimensions[sl].value)  # type: ignore[operator]
                            for n, sl in pairs
                        )
                        options.append((cost, pick, pairs))
                    cost, _, pairs = min(options, key=lambda item: (item[0], item[1]))
                    mapping.update(dict(pairs))
                    extra = cost
                rank = (-size, sum(diffs) + extra, chosen)
                if best is None or rank < best[0]:
                    best = (rank, mapping)
        if best is not None:
            break  # a fit with more values within tolerance always wins
    return None if best is None else ((best[0][0], best[0][1]), best[1])


def _signature(component: Component) -> tuple[Any, ...]:
    """Key-free content signature used for deterministic tie-breaking."""

    return (
        tuple(-1.0 if component.dimensions_mm[n] is None else component.dimensions_mm[n] for n in DIMENSION_FIELDS),
        -1 if component.quantity is None else component.quantity,
    )


def _ref_dims(reference: RefComponent) -> tuple[float, ...]:
    return tuple(
        -1.0 if reference.dimensions[n].value is None else reference.dimensions[n].value  # type: ignore[misc]
        for n in DIMENSION_FIELDS
    )


def _ref_signature(reference: RefComponent) -> tuple[Any, ...]:
    return (
        _ref_dims(reference),
        tuple(str(reference.dimensions[n].identifiable) for n in DIMENSION_FIELDS),
        str(reference.quantity.identifiable),
        -1.0 if reference.quantity.value is None else reference.quantity.value,
    )


def _pair_cost(component: Component, reference: RefComponent, mapping: dict[str, str]) -> tuple[Any, ...]:
    """Lower is better: inventions, resolvable-left-unknown, dimension error, -exact quantity."""

    by_slot = {slot: name for name, slot in mapping.items()}
    invented = left_unknown = 0
    error = 0.0
    for slot in DIMENSION_FIELDS:
        field_ref = reference.dimensions[slot]
        if field_ref.value is None or field_ref.identifiable is None:
            continue
        name = by_slot.get(slot)
        value = component.dimensions_mm[name] if name else None
        if field_ref.identifiable:
            if value is None:
                left_unknown += 1
            else:
                error += abs(value - field_ref.value)
        elif value is not None:
            invented += 1
    quantity_ref = reference.quantity
    exact = 0
    if quantity_ref.identifiable is False and component.quantity is not None:
        invented += 1
    elif quantity_ref.identifiable and quantity_ref.value is not None:
        if component.quantity is None:
            left_unknown += 1
        else:
            exact = int(component.quantity == int(quantity_ref.value))
    return (invented, left_unknown, round(error, 9), -exact)


MAX_PERMUTED_CLASS = 7


def match_components(
    predicted: list[Component], reference: tuple[RefComponent, ...], match_tolerance_mm: float
) -> list[tuple[Component, RefComponent, dict[str, str]]]:
    classes: dict[tuple[float, ...], list[RefComponent]] = {}
    for ref in reference:
        classes.setdefault(_ref_dims(ref), []).append(ref)
    candidates = []
    for pred in predicted:
        for dims, members in classes.items():
            assigned = _assign(pred, members[0], match_tolerance_mm)
            if assigned is not None:
                candidates.append((assigned[0], _signature(pred), dims, pred, assigned[1]))
    candidates.sort(key=lambda item: item[:3])
    capacity = {dims: len(members) for dims, members in classes.items()}
    taken: dict[tuple[float, ...], list[tuple[Component, dict[str, str]]]] = {}
    used: set[int] = set()
    for _, _, dims, pred, mapping in candidates:
        if id(pred) in used or capacity[dims] == 0:
            continue
        used.add(id(pred))
        capacity[dims] -= 1
        taken.setdefault(dims, []).append((pred, mapping))

    pairs: list[tuple[Component, RefComponent, dict[str, str]]] = []
    for dims in sorted(taken):
        members = sorted(classes[dims], key=_ref_signature)
        chosen = sorted(taken[dims], key=lambda item: _signature(item[0]))
        if len(members) > MAX_PERMUTED_CLASS:
            pairs.extend((p, r, m) for (p, m), r in zip(chosen, members, strict=False))
            continue
        best: tuple[tuple[Any, ...], tuple[RefComponent, ...]] | None = None
        for order in permutations(members, len(chosen)):
            totals = [_pair_cost(p, r, m) for (p, m), r in zip(chosen, order, strict=True)]
            score = tuple(sum(item[i] for item in totals) for i in range(4))
            if best is None or score < best[0]:
                best = (score, order)
        assert best is not None
        pairs.extend((p, r, m) for (p, m), r in zip(chosen, best[1], strict=True))
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
        types_ref = c["reference_types"] + c["failed_reference_types"]
        precision = _ratio(c["matched"], c["predicted_types"])
        recall = _ratio(c["matched"], types_ref)
        qty_precision = _ratio(c["quantity_true_positive"], c["quantity_predicted"])
        qty_reference = c["quantity_reference"] + c["failed_quantity_reference"]
        qty_recall = _ratio(c["quantity_true_positive"], qty_reference)
        eligible = c["dim_eligible"] + c["failed_dim_eligible"]
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
                "eligible_fields": eligible,
                "predicted_fields": c["dim_covered"],
                "coverage": _ratio(c["dim_covered"], eligible),
                "coverage_conditioned_on_ok": _ratio(c["dim_covered"], c["dim_eligible"]),
                "mae_mm": _ratio(sum(self.errors), len(self.errors)),
                "within_tolerance": c["dim_within"],
                "within_tolerance_rate": _ratio(c["dim_within"], len(self.errors)),
                "role_label_mismatches": c["role_mismatch"],
            },
            "identity": {
                "reference_types": types_ref,
                "predicted_types": c["predicted_types"],
                "matched": c["matched"],
                "false_positives": c["predicted_types"] - c["matched"],
                "omissions": types_ref - c["matched"],
                "precision": precision,
                "recall": recall,
                "recall_conditioned_on_ok": _ratio(c["matched"], c["reference_types"]),
                "f1": _f1(precision, recall),
                "quantity": {
                    "scope": "identifiable_quantities_only",
                    "compared_components": c["quantity_compared"],
                    "exact_matches": c["quantity_exact"],
                    "exact_rate": _ratio(c["quantity_exact"], c["quantity_compared"]),
                    "reference_total": qty_reference,
                    "predicted_total": c["quantity_predicted"],
                    "true_positive": c["quantity_true_positive"],
                    "precision": qty_precision,
                    "recall": qty_recall,
                    "recall_conditioned_on_ok": _ratio(c["quantity_true_positive"], c["quantity_reference"]),
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


def _score_failed(group: _Group, reference: ReferenceCase) -> None:
    """A failed run found nothing: its reference enters the denominators."""

    c = group.c
    c["failed_reference_types"] += len(reference.components)
    for ref in reference.components:
        c["failed_dim_eligible"] += sum(
            1 for n in DIMENSION_FIELDS
            if ref.dimensions[n].value is not None and ref.dimensions[n].identifiable
        )
        if ref.quantity.identifiable and ref.quantity.value is not None:
            c["failed_quantity_reference"] += int(ref.quantity.value)


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

    by_reference = {id(r): (p, mapping) for p, r, mapping in pairs}
    matched_predictions = {id(p) for p, _, _ in pairs}
    for ref in reference.components:
        quantity_ref = ref.quantity
        if quantity_ref.identifiable and quantity_ref.value is not None:
            c["quantity_reference"] += int(quantity_ref.value)
        paired = by_reference.get(id(ref))
        predicted, mapping = paired if paired else (None, {})
        assigned_slots = {slot: name for name, slot in mapping.items()}

        for slot in DIMENSION_FIELDS:
            field_ref = ref.dimensions[slot]
            if field_ref.value is None:
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
            elif quantity_ref.value is not None:
                expected = int(quantity_ref.value)
                c["quantity_compared"] += 1
                c["quantity_exact"] += predicted.quantity == expected
                c["quantity_true_positive"] += min(predicted.quantity, expected)
                c["quantity_predicted"] += predicted.quantity
    # Quantities of unmatched rows are unsupported claims: they count against precision.
    for component in components:
        if component.quantity is not None and id(component) not in matched_predictions:
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
        meta = metas.get(output["case_id"])
        if meta is None:
            raise ComparisonError(f"frozen output for unknown case {output['case_id']!r}")
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
        if output["status"] not in {"ok", "failed"}:
            continue
        reference = references.get(output["case_id"])
        if reference is None:
            group.cases_without_reference.add(output["case_id"])
            continue
        group.cases_with_reference.add(output["case_id"])
        if output["status"] == "failed":
            _score_failed(group, reference)
            continue
        components = [parse_component(item) for item in output["components"]]
        _score_observation(group, components, reference, tolerance_mm, match_tolerance_mm)
    result: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for (variant, family, split), group in sorted(groups.items()):
        result.setdefault(variant, {}).setdefault(family, {})[split] = group.finalize()
    return result
