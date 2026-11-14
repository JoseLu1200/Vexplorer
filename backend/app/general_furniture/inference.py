from __future__ import annotations

from backend.app.contratos.modelos import (
    GeneralBinding,
    GeneralConstructionParameter,
    GeneralDimensionRange,
    GeneralResolvedConstructionParameter,
    GeneralValue,
)


def _bounds(value: GeneralValue) -> tuple[float, float]:
    assert value.value_mm is not None
    if value.range_mm is None:
        return value.value_mm, value.value_mm
    return value.range_mm.min_mm, value.range_mm.max_mm


def _evaluate(binding: GeneralBinding, operands: tuple[GeneralValue, ...]) -> GeneralValue | None:
    if any(item.value_mm is None for item in operands):
        return None
    values = [float(item.value_mm) for item in operands if item.value_mm is not None]
    ranges = [_bounds(item) for item in operands]
    if binding.operation == "copy":
        nominal = values[0]
        low, high = ranges[0]
    elif binding.operation == "scale_rational":
        factor = binding.rational_numerator / binding.rational_denominator
        nominal = values[0] * factor
        low, high = ranges[0][0] * factor, ranges[0][1] * factor
    elif binding.operation == "add":
        nominal = sum(values)
        low = sum(item[0] for item in ranges)
        high = sum(item[1] for item in ranges)
    else:
        nominal = values[0] - sum(values[1:])
        low = ranges[0][0] - sum(item[1] for item in ranges[1:])
        high = ranges[0][1] - sum(item[0] for item in ranges[1:])
    if nominal <= 0 or low <= 0 or high <= 0:
        return None
    states = {item.state for item in operands}
    if "estimated" in states:
        state = "estimated"
    elif "deduced" in states or binding.operation != "copy":
        state = "deduced"
    else:
        state = operands[0].state
    assumption_refs = tuple(dict.fromkeys(ref for item in operands for ref in item.assumption_refs))
    dependencies = binding.operand_refs if binding.operation != "copy" else operands[0].dependency_refs
    return GeneralValue(
        value_mm=nominal,
        range_mm=GeneralDimensionRange(min_mm=low, max_mm=high) if state == "estimated" else None,
        state=state,
        dependency_refs=dependencies,
        evidence_ids=tuple(dict.fromkeys(ref for item in operands for ref in item.evidence_ids)),
        dimension_ids=tuple(dict.fromkeys(ref for item in operands for ref in item.dimension_ids)),
        method="arithmetic" if binding.operation != "copy" else operands[0].method,
        formula=f" {binding.operation} ".join(binding.operand_refs),
        assumption_refs=assumption_refs,
    )


def resolve_construction_graph(
    bindings: tuple[GeneralBinding, ...],
    parameters: tuple[GeneralConstructionParameter, ...],
    source_values: dict[str, GeneralValue],
    *,
    max_depth: int = 8,
) -> tuple[dict[str, GeneralValue], tuple[GeneralResolvedConstructionParameter, ...]]:
    """Resolve a bounded construction DAG without promoting estimates to facts."""
    refs = dict(source_values)
    ref_depth = {reference: 0 for reference in source_values}
    resolved_bindings: dict[str, GeneralValue] = {}
    resolved_parameters: dict[str, GeneralResolvedConstructionParameter] = {}
    parameter_by_binding = {
        item.binding_id: item for item in parameters if item.binding_id is not None
    }
    for parameter in parameters:
        if parameter.basis != "estimated":
            continue
        assert parameter.nominal_mm is not None and parameter.range_mm is not None
        value = GeneralValue(
            value_mm=parameter.nominal_mm,
            range_mm=parameter.range_mm,
            state="estimated",
            dependency_refs=parameter.source_refs + parameter.assumption_refs,
            method=parameter.method,
            assumption_refs=parameter.assumption_refs,
        )
        refs[f"parameter:{parameter.id}"] = value
        ref_depth[f"parameter:{parameter.id}"] = 0
        resolved_parameters[parameter.id] = GeneralResolvedConstructionParameter(
            id=parameter.id,
            label=parameter.label,
            nominal_mm=parameter.nominal_mm,
            range_mm=parameter.range_mm,
            state="estimated",
            method=parameter.method,
            binding_id=None,
            dependency_refs=parameter.source_refs + parameter.assumption_refs,
            source_refs=parameter.source_refs,
            assumption_refs=parameter.assumption_refs,
            rationale=parameter.rationale,
        )

    pending = {item.id: item for item in bindings}
    for _depth in range(max_depth):
        progress = False
        for binding_id, binding in tuple(pending.items()):
            operands = tuple(refs[ref] for ref in binding.operand_refs if ref in refs)
            if len(operands) != len(binding.operand_refs):
                continue
            depth = 1 + max(ref_depth[reference] for reference in binding.operand_refs)
            if depth > max_depth:
                raise ValueError("construction_graph_depth_exceeded")
            value = _evaluate(binding, operands)
            if value is None:
                continue
            resolved_bindings[binding_id] = value
            refs[f"binding:{binding_id}"] = value
            ref_depth[f"binding:{binding_id}"] = depth
            del pending[binding_id]
            progress = True
            parameter = parameter_by_binding.get(binding_id)
            if parameter is None:
                continue
            effective_state = (
                "estimated"
                if value.state == "estimated"
                else "observed"
                if value.state == "observed" and parameter.basis == "observed"
                else "deduced"
            )
            low, high = _bounds(value)
            assumptions = tuple(dict.fromkeys(value.assumption_refs + parameter.assumption_refs))
            resolved = GeneralResolvedConstructionParameter(
                id=parameter.id,
                label=parameter.label,
                nominal_mm=float(value.value_mm),
                range_mm=GeneralDimensionRange(min_mm=low, max_mm=high),
                state=effective_state,
                method=parameter.method,
                binding_id=binding_id,
                formula=value.formula,
                dependency_refs=binding.operand_refs,
                source_refs=parameter.source_refs,
                assumption_refs=assumptions,
                rationale=parameter.rationale,
            )
            resolved_parameters[parameter.id] = resolved
            refs[f"parameter:{parameter.id}"] = GeneralValue(
                value_mm=resolved.nominal_mm,
                range_mm=resolved.range_mm if resolved.state == "estimated" else None,
                state=resolved.state,
                dependency_refs=(f"binding:{binding_id}",),
                method=resolved.method,
                formula=resolved.formula,
                assumption_refs=resolved.assumption_refs,
            )
            ref_depth[f"parameter:{parameter.id}"] = depth
        if not progress:
            break
    if pending or len(resolved_parameters) != len(parameters):
        raise ValueError("construction_graph_unresolved_or_too_deep")
    return resolved_bindings, tuple(resolved_parameters[item.id] for item in parameters)
