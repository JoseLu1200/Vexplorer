from __future__ import annotations

from backend.app.contratos.modelos import ExplanationBundle, FormulaExplanation, PieceExplanation, Result


def explain_table_result(result: Result) -> ExplanationBundle:
    analysis = result.table_analysis
    evaluated = result.evaluated_table_program
    if analysis is None or evaluated is None:
        raise ValueError("table_evaluation_unavailable")
    measures = {item.id: item for item in analysis.measures}
    bindings = {item.id: item for item in evaluated.bindings}
    specs = {item.id: item for item in evaluated.raw_program.components}
    premises = {item.id: item for item in evaluated.raw_program.premises}

    def measurement_ids_for(binding_id: str) -> set[str]:
        found: set[str] = set()
        pending = [binding_id]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current in visited or current not in bindings:
                continue
            visited.add(current)
            for operand in bindings[current].operand_refs:
                if operand.ref_type == "measure":
                    found.add(operand.ref_id)
                else:
                    pending.append(operand.ref_id)
        return found

    pieces = []
    for component in evaluated.components:
        spec = specs[component.id]
        field_bindings = {"length_mm": spec.length_binding_id, "width_mm": spec.width_binding_id, "thickness_mm": spec.thickness_binding_id}
        referenced_measure_ids = set().union(*(measurement_ids_for(binding_id) for binding_id in field_bindings.values()))
        referenced_measures = [measures[item] for item in sorted(referenced_measure_ids) if item in measures]
        formulas = []
        for field, binding_id in field_bindings.items():
            value = getattr(component, field.removesuffix("_mm"))
            if value.value_mm is None:
                continue
            operand_ids = measurement_ids_for(binding_id)
            operands = {item: measures[item].value_mm for item in sorted(operand_ids) if item in measures and measures[item].value_mm is not None}
            formulas.append(FormulaExplanation(field=field, expression=f"{field}=binding:{binding_id}", operands_mm=operands, result_mm=value.value_mm))
        states = {
            "quantity": "calculated" if component.quantity is not None else "unknown",
            "length_mm": "hypothesis" if component.length.state == "proposed" else "unknown" if component.length.state in ("unknown", "conflict") else component.length.state,
            "width_mm": "hypothesis" if component.width.state == "proposed" else "unknown" if component.width.state in ("unknown", "conflict") else component.width.state,
            "thickness_mm": "hypothesis" if component.thickness.state == "proposed" else "unknown" if component.thickness.state in ("unknown", "conflict") else component.thickness.state,
        }
        unknowns = tuple(field for field, state in states.items() if state in ("unknown", "hypothesis"))
        pieces.append(PieceExplanation(
            piece_id=component.id,
            proposal_id=component.id,
            role=component.role,
            source_entity_ids=tuple(sorted({entity_id for item in referenced_measures for entity_id in item.source_entity_ids})),
            source_contour_ids=(),
            evidence_ids=tuple(sorted(set(component.evidence_ids) | {evidence_id for item in referenced_measures for evidence_id in item.evidence_ids})),
            dimension_ids=tuple(sorted({dimension_id for item in referenced_measures for dimension_id in item.measurement_ids})),
            measurements={"quantity": component.quantity, "length_mm": component.length.value_mm, "width_mm": component.width.value_mm, "thickness_mm": component.thickness.value_mm},
            formulas=tuple(formulas),
            premises=tuple(premises[item].description for item in spec.premise_ids if item in premises),
            unknown_fields=unknowns,
            field_states=states,
        ))
    return ExplanationBundle(run_id=result.run_id, result_revision=result.result_revision, pieces=tuple(pieces), warnings=tuple(item.message for item in evaluated.issues))
