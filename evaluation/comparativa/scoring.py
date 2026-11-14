"""Independent matching and per-family metrics (no global score).

Components are matched to reference components by dimension values alone,
one-to-one, *before* any precision/recall or quantity comparison.  The match
never uses keys, roles or reference-supplied pairings, and nothing in it
depends on key order.

Matching rules (documented because they are a choice):
* Identity match: every known value of the predicted component is assigned to
  a distinct reference dimension slot (independent of field labels: an
  orthographic rectangle shows any two of a part's three dimensions) and every
  value that lands on a slot not annotated unidentifiable must be within
  ``match_tolerance_mm``.  A value that lands on an unidentifiable slot does not
  block the match; it is scored afterwards as an invention.  At least two known
  values must fit.
* ``matched_partial`` is published apart: pairs among the leftovers where two or
  more values fit but an identifiable one does not.  It never enters precision,
  recall, coverage or MAE.
* The whole assignment of predicted to reference components is one exact
  global problem (Hungarian algorithm, any size), ordered by content and never
  by key, so equal answers score equally under any naming.  It takes the reading
  most favourable to the prediction: maximum number of valid matches, then
  fewest inventions, fewest resolvable fields left unknown, least dimension
  error, most exact quantities.  Reference components with identical dimensions
  form a *class*; inside one the favourable reading is optimistic, so the
  least favourable assignment with the same number of matches is solved too and
  published as ``abstention.lower_bound``; ``identity.ambiguous_class_pairs``
  counts the pairs resolved inside classes of more than one member.
* A field annotated ``identifiable=None`` filters the match like an identifiable
  one (only ``identifiable=False`` fields are free).
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
    OUTPUT_STATUSES,
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


def _assign_partial(
    component: Component, reference: RefComponent, tolerance: float
) -> tuple[tuple[int, float], dict[str, str]] | None:
    """Loose fit: best subset of >= 2 values within tolerance (for ``matched_partial`` only)."""

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


def _fit_strict(
    component: Component, reference: RefComponent, tolerance: float
) -> tuple[tuple[int, float], dict[str, str]] | None:
    """Identity fit: all known values placed; identifiable slots must be within tolerance."""

    known = [
        (name, component.dimensions_mm[name])
        for name in DIMENSION_FIELDS
        if component.dimensions_mm[name] is not None
    ]
    slots = _slots(reference)
    if len(known) < MIN_KNOWN_DIMENSIONS or len(known) > len(slots):
        return None
    best: tuple[tuple[int, Any, float, int, tuple[str, ...]], dict[str, str]] | None = None
    for chosen in permutations(slots, len(known)):
        diffs = [
            abs(value - reference.dimensions[slot].value)  # type: ignore[operator]
            for (_, value), slot in zip(known, chosen, strict=True)
        ]
        if any(d > tolerance and reference.dimensions[slot].identifiable is not False for d, slot in zip(diffs, chosen, strict=True)):
            continue
        fits = sum(d <= tolerance for d in diffs)
        if fits < MIN_KNOWN_DIMENSIONS:
            continue
        mapping = {name: slot for (name, _), slot in zip(known, chosen, strict=True)}
        fit_dist = sum(d for d in diffs if d <= tolerance)
        cost = _pair_cost(component, reference, mapping)
        rank = (
            -fits,
            cost,
            fit_dist,
            sum(name != slot for name, slot in mapping.items()),
            chosen,
        )
        if best is None or rank < best[0]:
            best = (rank, mapping)
    return None if best is None else ((best[0][0], best[0][2]), best[1])


# Integer weights keep the lexicographic order exact inside a linear assignment:
# invented > resolvable-left-unknown > dimension error > inexact quantity > total fit distance.
_W_INVENTED = 10**28
_W_LEFT_UNKNOWN = 10**22
_W_ERROR = 10**12
_W_INEXACT = 10**11
_UNMATCHED = 10**40
_FORBIDDEN = 10**43
_REVERSE = 10**36


def _scalar_cost(cost: tuple[Any, ...], fit_distance: float) -> int:
    invented, left_unknown, error, minus_exact = cost
    return (
        invented * _W_INVENTED
        + left_unknown * _W_LEFT_UNKNOWN
        + round(error * 1000) * _W_ERROR
        + (1 + minus_exact) * _W_INEXACT
        + round(fit_distance * 1000)
    )


def _hungarian(cost: list[list[int]]) -> list[int]:
    """Minimum-cost assignment of ``n`` rows to ``m >= n`` columns (exact, integers)."""

    n, m = len(cost), len(cost[0])
    inf = 10**60
    u = [0] * (n + 1)
    v = [0] * (m + 1)
    owner = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        owner[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = owner[j0], inf, 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                current = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if current < minv[j]:
                    minv[j], way[j] = current, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            if j1 == 0:
                raise ComparisonError("Hungarian assignment failed: no augmenting path (j1 == 0)")
            for j in range(m + 1):
                if used[j]:
                    u[owner[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if owner[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            owner[j0] = owner[j1]
            j0 = j1
    answer = [0] * n
    for j in range(1, m + 1):
        if owner[j]:
            answer[owner[j] - 1] = j - 1
    return answer


def match_components(
    predicted: list[Component],
    reference: tuple[RefComponent, ...],
    match_tolerance_mm: float,
    *,
    pessimistic: bool = False,
) -> list[tuple[Component, RefComponent, dict[str, str]]]:
    """One-to-one identity matches from one global exact assignment.

    The objective is lexicographic: most valid matches first, then (favourable
    reading) fewest inventions, fewest resolvable fields left unknown, least
    dimension error, most exact quantities.  ``pessimistic`` keeps the maximum
    number of matches but takes the least favourable reading of the rest.
    Rows and columns are ordered by content, never by key.
    """

    rows = sorted(predicted, key=_signature)
    columns = sorted(reference, key=_ref_signature)
    if not rows or not columns:
        return []
    fits = [[_fit_strict(p, r, match_tolerance_mm) for r in columns] for p in rows]
    matrix = []
    for row, p in zip(fits, rows, strict=True):
        costs = []
        for fit, r in zip(row, columns, strict=True):
            if fit is None:
                costs.append(_FORBIDDEN)
                continue
            scalar = _scalar_cost(_pair_cost(p, r, fit[1]), fit[0][1])
            costs.append(_REVERSE - scalar if pessimistic else scalar)
        matrix.append(costs + [_UNMATCHED] * len(rows))
    pairs: list[tuple[Component, RefComponent, dict[str, str]]] = []
    for row_index, column in enumerate(_hungarian(matrix)):
        fit = fits[row_index][column] if column < len(columns) else None
        if fit is not None:
            pairs.append((rows[row_index], columns[column], fit[1]))
    return pairs


def count_partial_matches(
    predicted: list[Component],
    reference: tuple[RefComponent, ...],
    pairs: list[tuple[Component, RefComponent, dict[str, str]]],
    match_tolerance_mm: float,
) -> int:
    """Greedy one-to-one loose fits among the leftovers (published apart, never scored)."""

    matched_p = {id(p) for p, _, _ in pairs}
    matched_r = {id(r) for _, r, _ in pairs}
    candidates = []
    for pred in predicted:
        if id(pred) in matched_p:
            continue
        for ref in reference:
            if id(ref) in matched_r:
                continue
            fit = _assign_partial(pred, ref, match_tolerance_mm)
            if fit is not None:
                candidates.append((fit[0], _signature(pred), _ref_signature(ref), id(pred), id(ref)))
    candidates.sort(key=lambda item: item[:3])
    used_p: set[int] = set()
    used_r: set[int] = set()
    for *_, pid, rid in candidates:
        if pid in used_p or rid in used_r:
            continue
        used_p.add(pid)
        used_r.add(rid)
    return len(used_p)


class _Group:
    def __init__(self, *, shadow: bool = False) -> None:
        self.shadow: _Group = self if shadow else _Group(shadow=True)
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
        result = self._finalize()
        lower = self.shadow._finalize()
        result["abstention"]["lower_bound"] = {
            "note": "least favourable assignment inside classes of identical dimensions",
            "correct_abstentions": lower["abstention"]["correct_abstentions"],
            "correct_abstention_rate": lower["abstention"]["correct_abstention_rate"],
            "asserted_unidentifiable": lower["abstention"]["asserted_unidentifiable"],
            "resolvable_left_unknown": lower["abstention"]["resolvable_left_unknown"],
            "over_abstention_rate": lower["abstention"]["over_abstention_rate"],
        }
        return result

    def _finalize(self) -> dict[str, Any]:
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
                "matched_partial": c["matched_partial"],
                "ambiguous_class_pairs": c["ambiguous_pairs"],
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
    tolerance_mm: float, match_tolerance_mm: float, *, pessimistic: bool = False,
) -> None:
    c = group.c
    pairs = match_components(components, reference.components, match_tolerance_mm, pessimistic=pessimistic)
    c["matched"] += len(pairs)
    c["matched_partial"] += count_partial_matches(components, reference.components, pairs, match_tolerance_mm)
    class_size = Counter(_ref_dims(r) for r in reference.components)
    c["ambiguous_pairs"] += sum(class_size[_ref_dims(r)] > 1 for _, r, _ in pairs)
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
        if output.get("status") not in OUTPUT_STATUSES:
            raise ComparisonError(f"invalid output status: {output.get('status')!r}")
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
                val = usage.get(field_name)
                if isinstance(val, int) and not isinstance(val, bool):
                    group.c[field_name] += val
            cost_val = usage.get("cost_eur")
            if isinstance(cost_val, (int, float)) and not isinstance(cost_val, bool):
                group.costs.append(float(cost_val))
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
        _score_observation(group.shadow, components, reference, tolerance_mm, match_tolerance_mm, pessimistic=True)
    result: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for (variant, family, split), group in sorted(groups.items()):
        result.setdefault(variant, {}).setdefault(family, {})[split] = group.finalize()
    return result
