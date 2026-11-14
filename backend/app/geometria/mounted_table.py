from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json

from backend.app.contratos.modelos import (
    DrawingContour,
    DrawingExtraction,
    EvaluatedTableBinding,
    EvaluatedTableComponent,
    EvaluatedTableProgram,
    MountedTableAnalysis,
    Point3D,
    Size3D,
    TableBinding,
    TableComponentSpec,
    TableConfirmedValue,
    TableFieldValue,
    TableMeasure,
    TableMeasurementDisposition,
    TableOperandRef,
    TableOccurrence,
    TableOverallDimensions,
    TablePlacement,
    TablePremise,
    TableProgramIssue,
    TableProgramProposal,
    TableReviewDecision,
)


TOLERANCE_MM = 0.1
REQUIRED_VIEWS = ("FRONT", "TOP", "SIDE")
PROFILE_SLOTS = (
    ("tabletop_thickness", "section"),
    ("support_width", "section"),
    ("support_depth", "section"),
    ("support_thickness", "section"),
)


def _rectangle_bounds(contour: DrawingContour) -> tuple[float, float, float, float] | None:
    points = contour.points_mm
    if not contour.closed or points is None or len(points) != 4:
        return None
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)
    expected = {(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)}
    actual = {(point.x, point.y) for point in points}
    if expected != actual or max_x - min_x <= TOLERANCE_MM or max_y - min_y <= TOLERANCE_MM:
        return None
    return min_x, min_y, max_x, max_y


def _outer_contours(extraction: DrawingExtraction) -> dict[str, tuple[DrawingContour, tuple[float, float, float, float]]]:
    labels = {view.id: view.label for view in extraction.views}
    candidates: dict[str, list[tuple[DrawingContour, tuple[float, float, float, float]]]] = defaultdict(list)
    for contour in extraction.contours:
        bounds = _rectangle_bounds(contour)
        if bounds is not None and labels.get(contour.view_id) in REQUIRED_VIEWS:
            candidates[labels[contour.view_id]].append((contour, bounds))
    return {
        label: max(values, key=lambda item: (item[1][2] - item[1][0]) * (item[1][3] - item[1][1]))
        for label, values in candidates.items()
    }


def _geometry_evidence(extraction: DrawingExtraction, entity_ids: set[str]) -> tuple[str, ...]:
    return tuple(sorted(
        item.id for item in extraction.evidence
        if item.kind == "geometry" and set(item.source_entity_ids) & entity_ids
    ))


def _dimension_semantic(extraction: DrawingExtraction, dimension_id: str) -> str | None:
    dimension = next(item for item in extraction.dimensions if item.id == dimension_id)
    graphic = next((item for item in extraction.dimension_graphics if item.dimension_id == dimension_id), None)
    view = next((item for item in extraction.views if item.id == dimension.view_id), None)
    if graphic is None or view is None or graphic.extension_start_a_mm is None or graphic.extension_start_b_mm is None:
        return None
    delta_x = abs(graphic.extension_start_b_mm.x - graphic.extension_start_a_mm.x)
    delta_y = abs(graphic.extension_start_b_mm.y - graphic.extension_start_a_mm.y)
    orientation = "x" if delta_x >= delta_y else "y"
    return {
        ("FRONT", "x"): "overall_width",
        ("FRONT", "y"): "overall_height",
        ("TOP", "x"): "overall_width",
        ("TOP", "y"): "overall_depth",
        ("SIDE", "x"): "overall_depth",
        ("SIDE", "y"): "overall_height",
    }.get((view.label, orientation))


def _overall_measure(
    extraction: DrawingExtraction,
    semantic: str,
    axis: str,
    geometry: list[tuple[float, DrawingContour]],
) -> TableMeasure:
    dimension_items = [
        item for item in extraction.dimensions
        if _dimension_semantic(extraction, item.id) == semantic
    ]
    entity_ids = {entity_id for _, contour in geometry for entity_id in contour.source_entity_ids}
    evidence_ids = set(_geometry_evidence(extraction, entity_ids))
    measurement_ids = tuple(sorted(item.id for item in dimension_items))
    view_ids = {contour.view_id for _, contour in geometry}
    for item in dimension_items:
        evidence_ids.update(item.evidence_ids)
        if item.view_id is not None:
            view_ids.add(item.view_id)
    geometry_values = [value for value, _ in geometry]
    annotation_values = [item.value_mm for item in dimension_items]
    conflict = any(value is None for value in annotation_values)
    resolved_values = geometry_values + [value for value in annotation_values if value is not None]
    if resolved_values and max(resolved_values) - min(resolved_values) > TOLERANCE_MM:
        conflict = True
    if conflict:
        return TableMeasure(
            id=f"table-measure-{semantic}", semantic=semantic, axis=axis,
            value_mm=None, state="conflict", measurement_ids=measurement_ids,
            view_ids=tuple(sorted(view_ids)), evidence_ids=tuple(sorted(evidence_ids)),
            source_entity_ids=tuple(sorted(entity_ids)), geometry_relation="dimension_annotation",
        )
    if resolved_values:
        return TableMeasure(
            id=f"table-measure-{semantic}", semantic=semantic, axis=axis,
            value_mm=resolved_values[0], state="observed", measurement_ids=measurement_ids,
            view_ids=tuple(sorted(view_ids)), evidence_ids=tuple(sorted(evidence_ids)),
            source_entity_ids=tuple(sorted(entity_ids)), geometry_relation="dimension_annotation",
        )
    return TableMeasure(
        id=f"table-measure-{semantic}", semantic=semantic, axis=axis,
        value_mm=None, state="unknown", geometry_relation="dimension_annotation",
    )


def _section_measures(
    extraction: DrawingExtraction,
    outer: dict[str, tuple[DrawingContour, tuple[float, float, float, float]]],
) -> tuple[TableMeasure, ...]:
    entities = {item.id: item for item in extraction.entities}
    views = {item.id: item for item in extraction.views}
    candidates: dict[tuple[str, int], dict[str, set[str]]] = {}

    def add(value: float, relation: str, view_id: str, entity_ids: set[str]) -> None:
        key = (relation, round(value / TOLERANCE_MM))
        item = candidates.setdefault(key, {"views": set(), "entities": set(), "evidence": set()})
        item["views"].add(view_id)
        item["entities"].update(entity_ids)
        item["evidence"].update(_geometry_evidence(extraction, entity_ids))

    for label, (contour, bounds) in outer.items():
        min_x, min_y, max_x, max_y = bounds
        width, height = max_x - min_x, max_y - min_y
        view = views[contour.view_id]
        horizontal: list[tuple[float, str]] = []
        vertical: list[tuple[float, str]] = []
        for entity_id in view.entity_ids:
            entity = entities[entity_id]
            if entity.kind != "LINE" or entity.points_mm is None or len(entity.points_mm) != 2:
                continue
            first, second = entity.points_mm
            if abs(first.y - second.y) <= TOLERANCE_MM and abs(first.x - second.x) >= 0.8 * width:
                if min_y + TOLERANCE_MM < first.y < max_y - TOLERANCE_MM:
                    horizontal.append((first.y, entity_id))
            if abs(first.x - second.x) <= TOLERANCE_MM and abs(first.y - second.y) >= 0.8 * height:
                if min_x + TOLERANCE_MM < first.x < max_x - TOLERANCE_MM:
                    vertical.append((first.x, entity_id))
        for y, entity_id in horizontal:
            gap = max_y - y
            if gap <= 0.25 * height:
                add(gap, "offset_from_max_y", view.id, {entity_id, *contour.source_entity_ids})
        left = [(x - min_x, entity_id) for x, entity_id in vertical if x - min_x <= 0.25 * width]
        right = [(max_x - x, entity_id) for x, entity_id in vertical if max_x - x <= 0.25 * width]
        matched: set[str] = set()
        for left_gap, left_id in left:
            counterpart = next(
                ((right_gap, right_id) for right_gap, right_id in right if abs(left_gap - right_gap) <= TOLERANCE_MM),
                None,
            )
            if counterpart is not None:
                add(left_gap, "opposite_offsets", view.id, {left_id, counterpart[1], *contour.source_entity_ids})
                matched.update((left_id, counterpart[1]))
        for gap, entity_id in left:
            if entity_id not in matched:
                add(gap, "offset_from_min_x", view.id, {entity_id, *contour.source_entity_ids})
        for gap, entity_id in right:
            if entity_id not in matched:
                add(gap, "offset_from_max_x", view.id, {entity_id, *contour.source_entity_ids})

    result = []
    for index, ((relation, bucket), refs) in enumerate(sorted(candidates.items()), start=1):
        result.append(TableMeasure(
            id=f"table-measure-section-{index}", semantic="unknown", axis="section",
            value_mm=bucket * TOLERANCE_MM, state="observed",
            view_ids=tuple(sorted(refs["views"])), evidence_ids=tuple(sorted(refs["evidence"])),
            source_entity_ids=tuple(sorted(refs["entities"])), geometry_relation=relation,
        ))
    return tuple(result)


def analyze_mounted_table(extraction: DrawingExtraction) -> MountedTableAnalysis:
    if extraction.input_kind != "mounted_orthographic_views":
        raise ValueError("mounted table analysis requires mounted_orthographic_views input")
    outer = _outer_contours(extraction)
    geometry = {
        "overall_width": [
            (bounds[2] - bounds[0], contour)
            for label, (contour, bounds) in outer.items() if label in ("FRONT", "TOP")
        ],
        "overall_height": [
            (bounds[3] - bounds[1], contour)
            for label, (contour, bounds) in outer.items() if label in ("FRONT", "SIDE")
        ],
        "overall_depth": [
            ((bounds[2] - bounds[0]) if label == "SIDE" else (bounds[3] - bounds[1]), contour)
            for label, (contour, bounds) in outer.items() if label in ("TOP", "SIDE")
        ],
    }
    measures = [
        _overall_measure(extraction, "overall_width", "width", geometry["overall_width"]),
        _overall_measure(extraction, "overall_height", "height", geometry["overall_height"]),
        _overall_measure(extraction, "overall_depth", "depth", geometry["overall_depth"]),
    ]
    measures.extend(_section_measures(extraction, outer))
    measures.extend(
        TableMeasure(
            id=f"table-measure-slot-{semantic}", semantic=semantic, axis=axis,
            value_mm=None, state="unknown", slot_origin="profile_required_slot",
            geometry_relation="profile_required_slot",
        )
        for semantic, axis in PROFILE_SLOTS
    )
    missing = [label for label in REQUIRED_VIEWS if label not in outer]
    warnings = list(extraction.warnings)
    warnings.extend(f"missing_required_view:{label}" for label in missing)
    warnings.extend(
        f"profile_measure_unknown:{item.semantic}"
        for item in measures if item.slot_origin == "profile_required_slot"
    )
    if any(item.state == "conflict" for item in measures):
        warnings.append("table_measure_conflict")
    ledger_revision = sha256(
        f"{extraction.drawing_id}|rectangular_table_v1|{','.join(item.id for item in measures)}".encode("utf-8")
    ).hexdigest()
    return MountedTableAnalysis(
        drawing_id=extraction.drawing_id, ledger_revision=ledger_revision,
        measures=tuple(measures), admitted_measurement_ids=tuple(item.id for item in measures),
        state="needs_review" if warnings or any(item.state != "observed" for item in measures) else "ready",
        warnings=tuple(warnings),
    )


def _measure_ref(measure_id: str) -> TableOperandRef:
    return TableOperandRef(ref_type="measure", ref_id=measure_id)


def _binding_ref(binding_id: str) -> TableOperandRef:
    return TableOperandRef(ref_type="binding", ref_id=binding_id)


def catalog_table_programs(analysis: MountedTableAnalysis) -> tuple[TableProgramProposal, ...]:
    measures = {item.semantic: item for item in analysis.measures if item.semantic != "unknown"}
    sections = {
        item.geometry_relation: item
        for item in analysis.measures
        if item.semantic == "unknown" and item.axis == "section" and item.state == "observed"
    }
    slots = {
        item.semantic: item
        for item in analysis.measures if item.slot_origin == "profile_required_slot"
    }
    required = ("overall_width", "overall_height", "overall_depth")
    if any(item not in measures for item in required):
        return ()
    tabletop_section = sections.get("offset_from_max_y", slots["tabletop_thickness"])

    def build(support_role: str) -> TableProgramProposal:
        if support_role == "side_support":
            support_section = sections.get("opposite_offsets", slots["support_thickness"])
            support_width = measures["overall_depth"]
            support_thickness = support_section
            template_id = "side_supports_v1"
            quantity_rule = "two_side_supports"
            placement_rule = "side_supports_flush"
        else:
            support_width = slots["support_depth"]
            support_thickness = sections.get("opposite_offsets", slots["support_width"])
            template_id = "corner_supports_v1"
            quantity_rule = "four_corner_supports"
            placement_rule = "corner_supports_flush"

        bindings = (
            TableBinding(id="binding-top-length", operation="copy", operand_refs=(_measure_ref(measures["overall_width"].id),)),
            TableBinding(id="binding-top-width", operation="copy", operand_refs=(_measure_ref(measures["overall_depth"].id),)),
            TableBinding(id="binding-top-thickness", operation="copy", operand_refs=(_measure_ref(tabletop_section.id),)),
            TableBinding(
                id="binding-support-length", operation="subtract",
                operand_refs=(_measure_ref(measures["overall_height"].id), _binding_ref("binding-top-thickness")),
            ),
            TableBinding(id="binding-support-width", operation="copy", operand_refs=(_measure_ref(support_width.id),)),
            TableBinding(id="binding-support-thickness", operation="copy", operand_refs=(_measure_ref(support_thickness.id),)),
        )
        premises = (
            TablePremise(id=f"premise-{template_id}-topology", kind="topology", description=f"The {template_id} topology is a design hypothesis."),
            TablePremise(id=f"premise-{template_id}-flush", kind="flush_placement", description="Supports and tabletop use the versioned flush placement rule."),
            TablePremise(id=f"premise-{template_id}-rectangular", kind="rectangular_components", description="Proposed components are rectangular solids without hidden joinery."),
            TablePremise(id=f"premise-{template_id}-section", kind="section_assignment", description="Observed section gaps are assigned to component fields by hypothesis."),
        )
        premise_ids = tuple(item.id for item in premises)
        evidence_ids = tuple(sorted({
            evidence_id
            for measure in (measures["overall_width"], measures["overall_height"], measures["overall_depth"], tabletop_section, support_width, support_thickness)
            for evidence_id in measure.evidence_ids
        }))
        return TableProgramProposal(
            id=f"catalog-{template_id}", ledger_revision=analysis.ledger_revision,
            proposal_origin="catalog_baseline", table_template_id=template_id,
            bindings=bindings,
            components=(
                TableComponentSpec(
                    id="component-tabletop", role="tabletop",
                    length_binding_id="binding-top-length", width_binding_id="binding-top-width",
                    thickness_binding_id="binding-top-thickness", quantity_rule_id="top_one",
                    placement_rule_id="top_flush", evidence_ids=evidence_ids,
                    premise_ids=(premise_ids[1], premise_ids[2], premise_ids[3]),
                ),
                TableComponentSpec(
                    id=f"component-{support_role.replace('_', '-')}", role=support_role,
                    length_binding_id="binding-support-length", width_binding_id="binding-support-width",
                    thickness_binding_id="binding-support-thickness", quantity_rule_id=quantity_rule,
                    placement_rule_id=placement_rule, evidence_ids=evidence_ids, premise_ids=premise_ids,
                ),
            ),
            premises=premises,
            assumptions=(
                "Catalog alternatives are explicit hypotheses and are never selected from drawing appearance.",
                "Observed geometric sections remain measurements; their component assignment is proposed.",
                "No joinery, material, strength, or manufacturing readiness is inferred.",
            ),
            evidence_ids=evidence_ids,
        )

    return build("side_support"), build("corner_support")


def _normalize_program(program: TableProgramProposal) -> TableProgramProposal:
    raw_bindings = {item.id: item for item in program.bindings}
    normalized_bindings: list[TableBinding] = []
    normalized_by_raw: dict[str, str] = {}
    normalized_by_signature: dict[str, str] = {}

    def normalize_binding(raw_id: str) -> str:
        if raw_id in normalized_by_raw:
            return normalized_by_raw[raw_id]
        raw = raw_bindings[raw_id]
        operands = []
        for item in raw.operand_refs:
            operands.append(TableOperandRef(
                ref_type=item.ref_type,
                ref_id=normalize_binding(item.ref_id) if item.ref_type == "binding" else item.ref_id,
            ))
        if raw.operation == "add":
            operands.sort(key=lambda item: (item.ref_type, item.ref_id))
        elif raw.operation == "subtract" and len(operands) > 2:
            operands = operands[:1] + sorted(operands[1:], key=lambda item: (item.ref_type, item.ref_id))
        signature = json.dumps(
            {"operation": raw.operation, "operands": [item.model_dump() for item in operands]},
            sort_keys=True, separators=(",", ":"),
        )
        normalized_id = normalized_by_signature.get(signature)
        if normalized_id is None:
            normalized_id = f"binding-{sha256(signature.encode('utf-8')).hexdigest()[:16]}"
            normalized_by_signature[signature] = normalized_id
            normalized_bindings.append(TableBinding(
                id=normalized_id, operation=raw.operation, operand_refs=tuple(operands),
            ))
        normalized_by_raw[raw_id] = normalized_id
        return normalized_id

    premise_map: dict[str, str] = {}
    normalized_premises: dict[str, TablePremise] = {}
    for premise in program.premises:
        signature = json.dumps(
            {"kind": premise.kind, "description": premise.description},
            sort_keys=True, separators=(",", ":"),
        )
        normalized_id = f"premise-{sha256(signature.encode('utf-8')).hexdigest()[:16]}"
        premise_map[premise.id] = normalized_id
        normalized_premises.setdefault(normalized_id, premise.model_copy(update={"id": normalized_id}))

    role_order = {"tabletop": 0, "side_support": 1, "corner_support": 2}
    normalized_components = []
    for component in sorted(program.components, key=lambda item: role_order[item.role]):
        normalized_components.append(component.model_copy(update={
            "id": f"component-{component.role.replace('_', '-')}",
            "length_binding_id": normalize_binding(component.length_binding_id),
            "width_binding_id": normalize_binding(component.width_binding_id),
            "thickness_binding_id": normalize_binding(component.thickness_binding_id),
            "premise_ids": tuple(sorted(premise_map[item] for item in component.premise_ids)),
            "evidence_ids": tuple(sorted(component.evidence_ids)),
        }))
    support = next(item.role for item in normalized_components if item.role != "tabletop")
    return TableProgramProposal(
        id=f"normalized-{program.proposal_origin}-{support}", ledger_revision=program.ledger_revision,
        profile=program.profile, proposal_origin=program.proposal_origin,
        table_template_id=program.table_template_id,
        bindings=tuple(normalized_bindings), components=tuple(normalized_components),
        premises=tuple(sorted(normalized_premises.values(), key=lambda item: item.id)),
        assumptions=tuple(sorted(program.assumptions)), evidence_ids=tuple(sorted(program.evidence_ids)),
    )


def _program_hash(program: TableProgramProposal) -> str:
    payload = json.dumps(program.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def evaluate_table_program(
    analysis: MountedTableAnalysis,
    program: TableProgramProposal,
    decisions: tuple[TableReviewDecision, ...] = (),
    confirmed_values: tuple[TableConfirmedValue, ...] = (),
) -> EvaluatedTableProgram:
    if program.ledger_revision != analysis.ledger_revision or program.profile != analysis.profile:
        raise ValueError("table program does not match analysis ledger/profile")
    normalized = _normalize_program(program)
    issues: list[TableProgramIssue] = []
    accepted: set[tuple[str, str]] = set()
    rejected: set[tuple[str, str]] = set()
    valid_targets = {
        ("program", program.id),
        *(("component", item.id) for item in program.components),
        *(("premise", item.id) for item in program.premises),
    }
    seen_decisions: set[tuple[str, str]] = set()
    for decision in decisions:
        target = (decision.target_kind, decision.target_id)
        if target in seen_decisions or target not in valid_targets:
            issues.append(TableProgramIssue(
                code="invalid_review_target", severity="error",
                message="Review decision does not target one unique program item.",
                target_ids=(decision.target_id,),
            ))
            continue
        seen_decisions.add(target)
        (accepted if decision.action == "accept" else rejected).add(target)

    measures = {item.id: item for item in analysis.measures}
    confirmed = {item.target_id: item for item in confirmed_values}
    if len(confirmed) != len(confirmed_values):
        issues.append(TableProgramIssue(
            code="duplicate_confirmed_value", severity="error",
            message="A measurement slot can only be confirmed once.",
        ))
    measure_fields: dict[str, TableFieldValue] = {}
    for measure_id, measure in measures.items():
        overlay = confirmed.get(measure_id)
        if overlay is not None and measure.state == "observed":
            issues.append(TableProgramIssue(
                code="observed_measure_override_rejected", severity="error",
                message="Observed CAD measures cannot be overwritten by review.", target_ids=(measure_id,),
            ))
            overlay = None
        if overlay is not None:
            measure_fields[measure_id] = TableFieldValue(
                value_mm=overlay.value_mm, state="confirmed",
                dependency_refs=(f"measure:{measure_id}",), evidence_ids=measure.evidence_ids,
            )
        else:
            measure_fields[measure_id] = TableFieldValue(
                value_mm=measure.value_mm, state=measure.state,
                dependency_refs=(f"measure:{measure_id}",), evidence_ids=measure.evidence_ids,
            )
    for target_id in confirmed:
        if target_id not in measures:
            issues.append(TableProgramIssue(
                code="unknown_measurement_slot", severity="error",
                message="Confirmed value targets an unknown measurement slot.", target_ids=(target_id,),
            ))

    program_accepted = ("program", program.id) in accepted
    evaluated_bindings: list[EvaluatedTableBinding] = []
    binding_fields: dict[str, TableFieldValue] = {}
    for binding in program.bindings:
        operand_fields = [
            measure_fields[item.ref_id] if item.ref_type == "measure" else binding_fields[item.ref_id]
            for item in binding.operand_refs
        ]
        dependencies = tuple(
            f"{item.ref_type}:{item.ref_id}" for item in binding.operand_refs
        )
        evidence = tuple(sorted({value for item in operand_fields for value in item.evidence_ids}))
        states = {item.state for item in operand_fields}
        value = None
        if "conflict" in states:
            state = "conflict"
        elif "unknown" in states:
            state = "unknown"
        else:
            values = [item.value_mm for item in operand_fields]
            assert all(item is not None for item in values)
            numeric = [float(item) for item in values if item is not None]
            if binding.operation == "copy":
                value = numeric[0]
            elif binding.operation == "add":
                value = sum(numeric)
            else:
                value = numeric[0] - sum(numeric[1:])
            if value <= 0:
                value = None
                state = "conflict"
                issues.append(TableProgramIssue(
                    code="non_positive_binding", severity="error",
                    message="Binding result must be strictly positive.", target_ids=(binding.id,),
                ))
            else:
                state = "calculated" if program_accepted else "proposed"
        field = TableFieldValue(
            value_mm=value, state=state, dependency_refs=dependencies, evidence_ids=evidence,
        )
        binding_fields[binding.id] = field
        evaluated_bindings.append(EvaluatedTableBinding(
            id=binding.id, operation=binding.operation,
            operand_refs=binding.operand_refs, result=field,
        ))

    evaluated_components: list[EvaluatedTableComponent] = []
    for component in program.components:
        component_accepted = ("component", component.id) in accepted

        def component_field(binding_id: str) -> TableFieldValue:
            source = binding_fields[binding_id]
            if source.state in ("unknown", "conflict"):
                return source
            return source.model_copy(update={
                "state": "calculated" if program_accepted and component_accepted else "proposed",
            })

        quantity = {"top_one": 1, "two_side_supports": 2, "four_corner_supports": 4}[component.quantity_rule_id]
        evaluated_components.append(EvaluatedTableComponent(
            id=component.id, role=component.role,
            length=component_field(component.length_binding_id),
            width=component_field(component.width_binding_id),
            thickness=component_field(component.thickness_binding_id),
            quantity=quantity, quantity_rule_id=component.quantity_rule_id,
            placement_rule_id=component.placement_rule_id, accepted=component_accepted,
            premise_ids=component.premise_ids, evidence_ids=component.evidence_ids,
        ))

    component_by_id = {item.id: item for item in evaluated_components}
    occurrences = tuple(
        TableOccurrence(id=f"occurrence-{item.id}-{index}", component_id=item.id, occurrence_index=index)
        for item in evaluated_components for index in range(1, (item.quantity or 0) + 1)
    )
    effective_overall = {
        item.semantic: measure_fields[item.id]
        for item in analysis.measures if item.semantic in ("overall_width", "overall_height", "overall_depth")
    }
    overall = TableOverallDimensions(
        width_mm=effective_overall["overall_width"].value_mm,
        depth_mm=effective_overall["overall_depth"].value_mm,
        height_mm=effective_overall["overall_height"].value_mm,
    )

    placements: list[TablePlacement] = []
    for occurrence in occurrences:
        component = component_by_id[occurrence.component_id]
        fields = (component.length, component.width, component.thickness)
        placement_dependencies = tuple(sorted({
            dependency for field in fields for dependency in field.dependency_refs
        }))
        placement_state = "proposed"
        position = None
        dimensions = None
        if any(item.state == "conflict" for item in fields) or any(
            item.state == "conflict" for item in effective_overall.values()
        ):
            placement_state = "conflict"
        elif any(item.value_mm is None for item in fields) or any(
            item.value_mm is None for item in effective_overall.values()
        ):
            placement_state = "unknown"
        else:
            width = overall.width_mm
            height = overall.height_mm
            depth = overall.depth_mm
            assert width is not None and height is not None and depth is not None
            assert component.length.value_mm is not None and component.width.value_mm is not None and component.thickness.value_mm is not None
            if component.role == "tabletop":
                position = Point3D(x=0.0, y=height - component.thickness.value_mm, z=0.0)
                dimensions = Size3D(x=component.length.value_mm, y=component.thickness.value_mm, z=component.width.value_mm)
            elif component.role == "side_support":
                x = 0.0 if occurrence.occurrence_index == 1 else width - component.thickness.value_mm
                position = Point3D(x=x, y=0.0, z=0.0)
                dimensions = Size3D(x=component.thickness.value_mm, y=component.length.value_mm, z=component.width.value_mm)
            else:
                x = 0.0 if occurrence.occurrence_index in (1, 3) else width - component.thickness.value_mm
                z = 0.0 if occurrence.occurrence_index in (1, 2) else depth - component.width.value_mm
                position = Point3D(x=x, y=0.0, z=z)
                dimensions = Size3D(x=component.thickness.value_mm, y=component.length.value_mm, z=component.width.value_mm)
            premises_accepted = all(("premise", item) in accepted for item in component.premise_ids)
            if program_accepted and component.accepted and premises_accepted:
                placement_state = "pass"
        rule_spec = next(item for item in program.components if item.id == component.id)
        placements.append(TablePlacement(
            occurrence_id=occurrence.id, position_mm=position, dimensions_mm=dimensions,
            rule_id=rule_spec.placement_rule_id, rule_version=rule_spec.placement_rule_version,
            state=placement_state, dependency_refs=placement_dependencies,
        ))

    consumed = tuple(sorted({
        operand.ref_id
        for binding in program.bindings for operand in binding.operand_refs
        if operand.ref_type == "measure"
    }))
    dispositions = tuple(
        TableMeasurementDisposition(
            measurement_id=item.id,
            reason="Profile slot is not required by the selected support topology."
            if item.slot_origin == "profile_required_slot"
            else "Observed drawing measure is not assigned by the proposed program.",
            blocking=item.slot_origin != "profile_required_slot",
        )
        for item in analysis.measures if item.id not in consumed
    )
    for item in dispositions:
        if item.blocking:
            issues.append(TableProgramIssue(
                code="unassigned_drawing_measure", severity="review",
                message=item.reason, target_ids=(item.measurement_id,),
            ))
    for warning in analysis.warnings:
        if warning.startswith("missing_required_view:"):
            issues.append(TableProgramIssue(
                code="missing_required_view", severity="error", message=warning,
            ))
    if rejected:
        issues.append(TableProgramIssue(
            code="review_target_rejected", severity="error",
            message="A required program target was rejected.",
            target_ids=tuple(sorted(item[1] for item in rejected)),
        ))

    all_components_accepted = all(("component", item.id) in accepted for item in program.components)
    all_premises_accepted = all(("premise", item.id) in accepted for item in program.premises)
    resolved_bindings = all(item.result.state == "calculated" for item in evaluated_bindings)
    pass_placements = all(item.state == "pass" for item in placements)
    blockers = any(item.blocking for item in dispositions) or any(item.severity != "warning" for item in issues)
    if rejected:
        state = "rejected"
    elif program_accepted and all_components_accepted and all_premises_accepted and resolved_bindings and pass_placements and not blockers:
        state = "completed"
    elif not decisions and not confirmed_values:
        state = "hypothesis"
    else:
        state = "needs_review"

    registry_versions = {
        "profile": "rectangular_table_v1",
        **{f"quantity:{item.quantity_rule_id}": item.quantity_rule_version for item in program.components},
        **{f"placement:{item.placement_rule_id}": item.placement_rule_version for item in program.components},
    }
    return EvaluatedTableProgram(
        raw_program=program, normalized_program=normalized,
        program_hash=_program_hash(normalized), ledger_revision=analysis.ledger_revision,
        registry_versions=registry_versions, bindings=tuple(evaluated_bindings),
        components=tuple(evaluated_components), occurrences=occurrences,
        placements=tuple(placements), overall_dimensions=overall,
        consumed_measurement_ids=consumed, measurement_dispositions=dispositions,
        accepted_target_ids=tuple(sorted(item[1] for item in accepted)),
        rejected_target_ids=tuple(sorted(item[1] for item in rejected)),
        issues=tuple(issues), state=state,
    )
