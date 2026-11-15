from __future__ import annotations

from backend.app.contratos.modelos import (
    DrawingExtraction,
    GeneralDraftComponent,
    GeneralFurnitureDraft,
    GeneralFurnitureProposal,
    GeneralValue,
    ReferentialValidationError,
)
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.inference import resolve_construction_graph
from backend.app.general_furniture.assembly_semantics import (
    validate_assembly_source_references,
)


def _unknown() -> GeneralValue:
    return GeneralValue(value_mm=None, state="unknown")


def materialize_general_proposal(
    extraction: DrawingExtraction,
    proposal: GeneralFurnitureProposal,
    *,
    allowed_document_refs: tuple[str, ...] = (),
) -> GeneralFurnitureDraft:
    if proposal.drawing_id != extraction.drawing_id:
        raise ValueError("proposal_drawing_mismatch")
    ledger = {
        "view": {item.id for item in extraction.views},
        "observation": {item.id for item in extraction.observations},
        "contour": {item.id for item in extraction.contours},
        "evidence": {item.id for item in extraction.evidence},
        "dimension": {item.id for item in extraction.dimensions},
    }
    dimensions = {item.id: item for item in extraction.dimensions}
    measures = {item.id: item for item in derive_geometry_measurements(extraction)}
    internal_ref_prefixes = (
        "parameter:", "binding:", "premise:", "component:",
        "constraint:", "detail:", "decision:",
    )

    def external_ref_is_allowed(reference: str) -> bool:
        if reference.startswith(internal_ref_prefixes):
            return True
        kind, separator, ref_id = reference.partition(":")
        if not separator:
            return False
        allowed_by_kind = {
            "dimension": ledger["dimension"],
            "measurement": set(measures),
            "view": ledger["view"],
            "observation": ledger["observation"],
            "contour": ledger["contour"],
            "evidence": ledger["evidence"],
        }
        if kind in allowed_by_kind:
            return ref_id in allowed_by_kind[kind]
        if kind in {"document", "visual"}:
            return reference in allowed_document_refs or ref_id in allowed_document_refs
        return False

    nested_reference_fields = [
        *((f"construction_parameters[{index}].source_refs", item.source_refs) for index, item in enumerate(proposal.construction_parameters)),
        *((f"components[{index}].geometry.basis_refs", item.geometry.basis_refs) for index, item in enumerate(proposal.components)),
        *((f"components[{index}].quantity_basis_refs", item.quantity_basis_refs) for index, item in enumerate(proposal.components)),
        *((f"construction_constraints[{index}].source_refs", item.source_refs) for index, item in enumerate(proposal.construction_constraints)),
        *((f"construction_details[{index}].source_refs", item.source_refs) for index, item in enumerate(proposal.construction_details)),
        *(
            (f"construction_details[{index}].geometry.dimension_refs", item.geometry.dimension_refs)
            for index, item in enumerate(proposal.construction_details)
            if item.geometry is not None
        ),
        *((f"construction_decisions[{index}].basis_refs", item.basis_refs) for index, item in enumerate(proposal.construction_decisions)),
        *((f"construction_placements[{index}].source_refs", item.source_refs) for index, item in enumerate(proposal.construction_placements)),
    ]
    invalid_authority_fields = [
        (path, sorted({ref for ref in refs if not external_ref_is_allowed(ref)}))
        for path, refs in nested_reference_fields
        if any(not external_ref_is_allowed(ref) for ref in refs)
    ]
    allowed_documents = set(allowed_document_refs)
    invalid_document_fields = [
        (f"components[{index}].source_document_refs", sorted(invalid))
        for index, component in enumerate(proposal.components)
        if (invalid := set(component.source_document_refs) - allowed_documents)
    ]
    authority_details = [
        {
            "path": path,
            "msg": "construction_reference_outside_authority",
            "invalid_refs": tuple(refs[:10]),
            "invalid_ref_count": len(refs),
            "expected": "dimension|measurement|view|observation|contour|evidence|document|visual|internal",
        }
        for path, refs in invalid_authority_fields
    ]
    document_details = [
        {
            "path": path,
            "msg": "proposal_reference_outside_document_context",
            "invalid_refs": tuple(refs[:10]),
            "invalid_ref_count": len(refs),
            "expected": "document or visual reference announced by the current context",
        }
        for path, refs in invalid_document_fields
    ]
    reference_details = authority_details + document_details
    if reference_details:
        raise ReferentialValidationError(
            "construction_reference_outside_authority" if authority_details else "proposal_reference_outside_document_context",
            reference_details,
            total_count=len(reference_details),
        )
    validate_assembly_source_references(
        extraction,
        proposal,
        allowed_document_refs=allowed_document_refs,
    )
    for component in proposal.components:
        checks = (
            (component.source_view_ids, ledger["view"]),
            (component.source_observation_ids, ledger["observation"]),
            (component.source_contour_ids, ledger["contour"]),
            (component.source_evidence_ids, ledger["evidence"]),
            (component.source_dimension_ids, ledger["dimension"]),
        )
        if any(not set(values) <= allowed for values, allowed in checks):
            raise ValueError("proposal_reference_outside_ledger")
        if proposal.proposal_origin == "native_tool" and not (
            component.source_view_ids
            or component.source_observation_ids
            or component.source_contour_ids
            or component.source_evidence_ids
            or component.source_dimension_ids
            or component.source_document_refs
        ):
            raise ValueError("native_component_requires_ledger_reference")

    source_values: dict[str, GeneralValue] = {}
    for source in dimensions.values():
        source_values[f"dimension:{source.id}"] = GeneralValue(
            value_mm=source.value_mm,
            state="observed" if source.value_mm is not None else "unknown",
            evidence_ids=source.evidence_ids if source.value_mm is not None else (),
            dimension_ids=(source.id,) if source.value_mm is not None else (),
            method="observed_copy" if source.value_mm is not None else None,
        )
    for source in measures.values():
        source_values[f"measurement:{source.id}"] = GeneralValue(
            value_mm=source.value_mm,
            state="observed" if source.value_mm is not None else "unknown",
            dependency_refs=(f"measurement:{source.id}",) if source.value_mm is not None else (),
            method="observed_copy" if source.value_mm is not None else None,
        )
    if proposal.construction_parameters:
        resolved, resolved_parameters = resolve_construction_graph(
            proposal.bindings, proposal.construction_parameters, source_values
        )
    else:
        resolved = {}
        resolved_parameters = ()
    for binding in proposal.bindings:
        if binding.id in resolved:
            continue
        operands: list[GeneralValue] = []
        for ref in binding.operand_refs:
            kind, separator, ref_id = ref.partition(":")
            if not separator or kind not in {"dimension", "measurement", "binding"}:
                raise ValueError("invalid_general_operand_reference")
            if kind == "binding":
                if ref_id not in resolved:
                    raise ValueError("binding_reference_must_target_previous_binding")
                operands.append(resolved[ref_id])
            elif kind == "dimension":
                source = dimensions.get(ref_id)
                if source is None:
                    raise ValueError("proposal_reference_outside_ledger")
                operands.append(
                    GeneralValue(
                        value_mm=source.value_mm,
                        state="observed" if source.value_mm is not None else "unknown",
                        evidence_ids=source.evidence_ids
                        if source.value_mm is not None
                        else (),
                        dimension_ids=(source.id,)
                        if source.value_mm is not None
                        else (),
                    )
                )
            else:
                source = measures.get(ref_id)
                if source is None:
                    raise ValueError("proposal_reference_outside_ledger")
                operands.append(
                    GeneralValue(
                        value_mm=source.value_mm,
                        state="observed" if source.value_mm is not None else "unknown",
                        dependency_refs=(f"measurement:{source.id}",)
                        if source.value_mm is not None
                        else (),
                    )
                )
        if any(item.value_mm is None for item in operands):
            resolved[binding.id] = _unknown()
            continue
        values = [
            float(item.value_mm) for item in operands if item.value_mm is not None
        ]
        if binding.operation == "copy":
            value = values[0]
            state = operands[0].state
            dependencies = operands[0].dependency_refs
        elif binding.operation == "add":
            value = sum(values)
            state = "derived"
            dependencies = binding.operand_refs
        elif binding.operation == "scale_rational":
            value = values[0] * binding.rational_numerator / binding.rational_denominator
            state = "derived"
            dependencies = binding.operand_refs
        else:
            value = values[0] - sum(values[1:])
            state = "derived"
            dependencies = binding.operand_refs
        if value <= 0:
            resolved[binding.id] = _unknown()
            continue
        resolved[binding.id] = GeneralValue(
            value_mm=value,
            state=state,
            dependency_refs=dependencies,
            evidence_ids=tuple(
                dict.fromkeys(
                    evidence_id
                    for item in operands
                    for evidence_id in item.evidence_ids
                )
            ),
            dimension_ids=tuple(
                dict.fromkeys(
                    dimension_id
                    for item in operands
                    for dimension_id in item.dimension_ids
                )
            ),
        )

    def field(binding_id: str | None) -> GeneralValue:
        if binding_id is None or binding_id not in resolved:
            return _unknown()
        value = resolved[binding_id]
        if value.value_mm is None:
            return value
        if value.state in {"derived", "deduced", "estimated"}:
            return GeneralValue(
                value_mm=value.value_mm,
                range_mm=value.range_mm,
                state="deduced" if value.state == "derived" else value.state,
                dependency_refs=(f"binding:{binding_id}",),
                evidence_ids=value.evidence_ids,
                dimension_ids=value.dimension_ids,
                method=value.method,
                formula=value.formula,
                assumption_refs=value.assumption_refs,
            )
        if value.state == "observed":
            return GeneralValue(
                value_mm=value.value_mm,
                state="deduced",
                dependency_refs=(f"binding:{binding_id}",),
                evidence_ids=value.evidence_ids,
                dimension_ids=value.dimension_ids,
                method="observed_copy",
                formula=f"copy(binding:{binding_id})",
            )
        return GeneralValue(
            value_mm=value.value_mm,
            state="hypothesis",
            dependency_refs=(f"binding:{binding_id}",),
            evidence_ids=value.evidence_ids,
            dimension_ids=value.dimension_ids,
        )

    return GeneralFurnitureDraft(
        proposal_id=proposal.id,
        drawing_id=proposal.drawing_id,
        ledger_revision=proposal.ledger_revision,
        components=tuple(
            GeneralDraftComponent(
                id=item.id,
                label=item.label,
                kind=item.kind,
                role=item.role,
                length=field(item.length_binding_id),
                width=field(item.width_binding_id),
                thickness=field(item.thickness_binding_id),
                quantity=item.quantity,
                premise_ids=item.premise_ids,
                source_view_ids=item.source_view_ids,
                source_observation_ids=item.source_observation_ids,
                source_contour_ids=item.source_contour_ids,
                source_evidence_ids=item.source_evidence_ids,
                source_dimension_ids=item.source_dimension_ids,
                source_document_refs=item.source_document_refs,
                assumptions=item.assumptions,
                unknown_fields=item.unknown_fields,
                scenario_id=item.scenario_id,
                necessity=item.necessity,
                geometry=item.geometry,
                construction_parameter_ids=item.construction_parameter_ids,
                detail_ids=item.detail_ids,
                quantity_basis_refs=item.quantity_basis_refs,
            )
            for item in proposal.components
        ),
        premises=proposal.premises,
        assumptions=proposal.assumptions,
        construction_scenario_id=proposal.construction_scenario_id,
        construction_parameters=resolved_parameters,
        construction_constraints=proposal.construction_constraints,
        construction_details=proposal.construction_details,
        construction_decisions=proposal.construction_decisions,
        construction_placements=proposal.construction_placements,
        evidence_dispositions=proposal.evidence_dispositions,
        assembly_relations=proposal.assembly_relations,
        assembly_alternatives=proposal.assembly_alternatives,
    )
