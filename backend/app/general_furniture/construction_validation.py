from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from backend.app.contratos.modelos import (
    GeneralConstructionIssue,
    GeneralConstructionValidation,
    GeneralConstraintResult,
    GeneralDimensionRange,
    GeneralFurnitureDraft,
    GeneralFurnitureProposal,
)


_MAX_EXPRESSION_DEPTH = 8
_EPSILON = 1e-9
_DETAIL_TOLERANCE_MM = 0.1


@dataclass(frozen=True)
class _Affine:
    constant: float
    coefficients: tuple[tuple[str, float], ...] = ()

    @classmethod
    def variable(cls, name: str) -> _Affine:
        return cls(0.0, ((name, 1.0),))

    def _mapping(self) -> dict[str, float]:
        return dict(self.coefficients)

    def plus(self, other: _Affine, factor: float = 1.0) -> _Affine:
        values = self._mapping()
        for name, coefficient in other.coefficients:
            values[name] = values.get(name, 0.0) + factor * coefficient
        return _Affine(
            self.constant + factor * other.constant,
            tuple(
                sorted(
                    (name, value)
                    for name, value in values.items()
                    if abs(value) > _EPSILON
                )
            ),
        )

    def scaled(self, factor: float) -> _Affine:
        return _Affine(
            self.constant * factor,
            tuple((name, coefficient * factor) for name, coefficient in self.coefficients),
        )


@dataclass(frozen=True)
class _Resolved:
    expression: _Affine
    state: str
    depth: int


class _Resolver:
    def __init__(
        self, proposal: GeneralFurnitureProposal, draft: GeneralFurnitureDraft
    ) -> None:
        self.proposal = proposal
        self.draft = draft
        self.parameter_specs = {item.id: item for item in proposal.construction_parameters}
        self.parameters = {item.id: item for item in draft.construction_parameters}
        self.bindings = {item.id: item for item in proposal.bindings}
        self.parameter_cache: dict[str, _Resolved | None] = {}
        self.binding_cache: dict[str, _Resolved | None] = {}
        self.stack: list[str] = []
        self.parameter_order: list[str] = []
        self.base_ranges: dict[str, tuple[float, float]] = {}
        self.base_nominals: dict[str, float] = {}
        self.issues: list[GeneralConstructionIssue] = []
        self.max_depth = 0

    def issue(
        self, severity: str, code: str, message: str, *target_refs: str
    ) -> None:
        self.issues.append(
            GeneralConstructionIssue(
                severity=severity,
                code=code,
                message=message,
                target_refs=tuple(target_refs),
            )
        )

    def _enter(self, ref: str) -> None:
        if ref in self.stack:
            raise ValueError("construction_expression_cycle")
        self.stack.append(ref)

    def _leave(self) -> None:
        self.stack.pop()

    def _record_depth(self, resolved: _Resolved | None) -> None:
        if resolved is None:
            return
        if resolved.depth > _MAX_EXPRESSION_DEPTH:
            raise ValueError("construction_expression_depth_exceeded")
        self.max_depth = max(self.max_depth, resolved.depth)

    def parameter(self, parameter_id: str) -> _Resolved | None:
        if parameter_id in self.parameter_cache:
            return self.parameter_cache[parameter_id]
        spec = self.parameter_specs.get(parameter_id)
        actual = self.parameters.get(parameter_id)
        if spec is None:
            raise ValueError("construction_parameter_unknown")
        if actual is None:
            self.issue(
                "error",
                "construction_parameter_unresolved",
                f"Parameter {parameter_id} is absent from the materialized draft.",
                f"parameter:{parameter_id}",
            )
            self.parameter_cache[parameter_id] = None
            return None
        ref = f"parameter:{parameter_id}"
        self._enter(ref)
        try:
            if spec.basis == "estimated":
                if (
                    actual.state != "estimated"
                    or spec.nominal_mm is None
                    or spec.range_mm is None
                    or abs(actual.nominal_mm - spec.nominal_mm) > _EPSILON
                    or actual.range_mm != spec.range_mm
                ):
                    self.issue(
                        "error",
                        "construction_parameter_mismatch",
                        f"Estimated parameter {parameter_id} differs from the proposal.",
                        ref,
                    )
                variable = f"estimate:{parameter_id}"
                self.base_ranges[variable] = (
                    actual.range_mm.min_mm,
                    actual.range_mm.max_mm,
                )
                self.base_nominals[variable] = actual.nominal_mm
                resolved = _Resolved(_Affine.variable(variable), "estimated", 0)
            elif spec.basis == "observed":
                if actual.state != "observed":
                    self.issue(
                        "error",
                        "construction_parameter_mismatch",
                        f"Observed parameter {parameter_id} changed authority.",
                        ref,
                    )
                if abs(actual.range_mm.max_mm - actual.range_mm.min_mm) <= _EPSILON:
                    expression = _Affine(actual.nominal_mm)
                else:
                    variable = f"observed:{parameter_id}"
                    self.base_ranges[variable] = (
                        actual.range_mm.min_mm,
                        actual.range_mm.max_mm,
                    )
                    self.base_nominals[variable] = actual.nominal_mm
                    expression = _Affine.variable(variable)
                resolved = _Resolved(expression, "observed", 0)
            else:
                if spec.binding_id is None:
                    raise ValueError("construction_deduced_parameter_without_binding")
                binding = self.binding(spec.binding_id)
                if binding is None:
                    resolved = None
                else:
                    state = "estimated" if self._depends_on_estimate(binding.expression) else "deduced"
                    expected_nominal = self.nominal(binding.expression)
                    expected_range = self.interval(binding.expression)
                    if (
                        actual.state != state
                        or abs(actual.nominal_mm - expected_nominal) > _EPSILON
                        or abs(actual.range_mm.min_mm - expected_range[0]) > _EPSILON
                        or abs(actual.range_mm.max_mm - expected_range[1]) > _EPSILON
                    ):
                        self.issue(
                            "error",
                            "construction_parameter_mismatch",
                            f"Deduced parameter {parameter_id} does not match its binding.",
                            ref,
                            f"binding:{spec.binding_id}",
                        )
                    resolved = _Resolved(binding.expression, state, binding.depth)
        finally:
            self._leave()
        self._record_depth(resolved)
        self.parameter_cache[parameter_id] = resolved
        self.parameter_order.append(parameter_id)
        return resolved

    def binding(self, binding_id: str) -> _Resolved | None:
        if binding_id in self.binding_cache:
            return self.binding_cache[binding_id]
        binding = self.bindings.get(binding_id)
        if binding is None:
            raise ValueError("construction_binding_unknown")
        ref = f"binding:{binding_id}"
        self._enter(ref)
        try:
            operands = [self.reference(value) for value in binding.operand_refs]
            if any(item is None for item in operands):
                resolved = None
            else:
                known = [item for item in operands if item is not None]
                expression = known[0].expression
                if binding.operation == "scale_rational":
                    expression = expression.scaled(
                        binding.rational_numerator / binding.rational_denominator
                    )
                elif binding.operation == "add":
                    for item in known[1:]:
                        expression = expression.plus(item.expression)
                elif binding.operation == "subtract":
                    for item in known[1:]:
                        expression = expression.plus(item.expression, -1.0)
                state = (
                    "estimated"
                    if any(item.state == "estimated" for item in known)
                    else "deduced"
                )
                resolved = _Resolved(
                    expression, state, max(item.depth for item in known) + 1
                )
        finally:
            self._leave()
        self._record_depth(resolved)
        self.binding_cache[binding_id] = resolved
        return resolved

    def reference(self, ref: str) -> _Resolved | None:
        kind, separator, identifier = ref.partition(":")
        if not separator:
            raise ValueError("construction_reference_invalid")
        if kind == "parameter":
            return self.parameter(identifier)
        if kind == "binding":
            return self.binding(identifier)
        # Raw ledger operands are resolved by the materializer into an observed
        # construction parameter. They are intentionally not re-read here.
        return None

    def nominal(self, expression: _Affine) -> float:
        return expression.constant + sum(
            coefficient * self.base_nominals[name]
            for name, coefficient in expression.coefficients
        )

    def interval(self, expression: _Affine) -> tuple[float, float]:
        minimum = maximum = expression.constant
        for name, coefficient in expression.coefficients:
            low, high = self.base_ranges[name]
            if coefficient >= 0:
                minimum += coefficient * low
                maximum += coefficient * high
            else:
                minimum += coefficient * high
                maximum += coefficient * low
        return minimum, maximum

    @staticmethod
    def _depends_on_estimate(expression: _Affine) -> bool:
        return any(name.startswith("estimate:") for name, _ in expression.coefficients)


def _range(values: tuple[float, float]) -> GeneralDimensionRange | None:
    if values[0] <= 0 or values[1] <= 0:
        return None
    return GeneralDimensionRange(min_mm=values[0], max_mm=values[1])


def _sum_refs(resolver: _Resolver, refs: tuple[str, ...]) -> _Resolved | None:
    values = [resolver.reference(ref) for ref in refs]
    if any(item is None for item in values):
        return None
    known = [item for item in values if item is not None]
    expression = _Affine(0.0)
    for item in known:
        expression = expression.plus(item.expression)
    return _Resolved(
        expression,
        "estimated" if any(item.state == "estimated" for item in known) else "deduced",
        max((item.depth for item in known), default=0) + 1,
    )


def validate_construction_scenario(
    proposal: GeneralFurnitureProposal,
    draft: GeneralFurnitureDraft,
) -> GeneralConstructionValidation:
    """Recalculate one construction scenario without inventing values or pieces."""
    if proposal.id != draft.proposal_id or proposal.drawing_id != draft.drawing_id:
        raise ValueError("construction_proposal_draft_mismatch")
    if proposal.construction_scenario_id != draft.construction_scenario_id:
        raise ValueError("construction_scenario_mismatch")

    resolver = _Resolver(proposal, draft)
    parameter_bindings = [
        item.binding_id
        for item in proposal.construction_parameters
        if item.binding_id is not None
    ]
    if len(parameter_bindings) != len(set(parameter_bindings)):
        raise ValueError("construction_parameter_binding_alias")
    for parameter in proposal.construction_parameters:
        if parameter.basis != "observed" or parameter.binding_id is None:
            continue
        binding = resolver.bindings.get(parameter.binding_id)
        if (
            binding is None
            or binding.operation != "copy"
            or len(binding.operand_refs) != 1
            or not binding.operand_refs[0].startswith(("dimension:", "measurement:"))
        ):
            resolver.issue(
                "error",
                "construction_observed_binding_invalid",
                f"Observed parameter {parameter.id} is not a direct ledger copy.",
                f"parameter:{parameter.id}",
                f"binding:{parameter.binding_id}",
            )
    for parameter in proposal.construction_parameters:
        resolver.parameter(parameter.id)

    proposal_parameter_ids = {item.id for item in proposal.construction_parameters}
    extra_parameters = set(resolver.parameters) - proposal_parameter_ids
    if extra_parameters:
        raise ValueError("construction_draft_parameter_unknown")

    draft_components = {item.id: item for item in draft.components}
    proposal_components = {item.id: item for item in proposal.components}
    for component in proposal.components:
        quantity_ref = f"component:{component.id}.quantity"
        if component.quantity.value is not None and not component.quantity_basis_refs:
            resolver.issue(
                "error",
                "construction_quantity_basis_missing",
                f"Component {component.id} has quantity without a construction basis.",
                quantity_ref,
            )
        if any(
            ref.startswith(("view:", "projection:", "projection-hypothesis:"))
            for ref in component.quantity_basis_refs
        ):
            resolver.issue(
                "error",
                "construction_quantity_counts_views",
                f"Component {component.id} uses a view or projection as quantity.",
                quantity_ref,
            )

    detail_unknown = False
    for detail in proposal.construction_details:
        if detail.geometry is None:
            continue
        detail_dimensions: list[tuple[str, _Resolved]] = []
        for ref in detail.geometry.dimension_refs:
            resolved_dimension = resolver.reference(ref)
            if resolved_dimension is None:
                detail_unknown = True
                resolver.issue(
                    "warning",
                    "construction_detail_dimension_unresolved",
                    f"Detail {detail.id} has an unresolved dimension reference.",
                    f"detail:{detail.id}",
                    ref,
                )
            else:
                detail_dimensions.append((ref, resolved_dimension))
        for component_id in detail.component_ids:
            component = draft_components.get(component_id)
            proposal_component = proposal_components.get(component_id)
            if component is None or proposal_component is None:
                raise ValueError("construction_detail_component_unknown")
            if proposal_component.geometry.shape_kind not in {"rectangle", "linear"}:
                continue
            if component.length.value_mm is None or component.width.value_mm is None:
                detail_unknown = True
                resolver.issue(
                    "warning",
                    "construction_detail_bounds_unresolved",
                    f"Detail {detail.id} cannot be bounded without piece dimensions.",
                    f"detail:{detail.id}",
                    f"component:{component_id}.geometry",
                )
                continue
            length = float(component.length.value_mm)
            width = float(component.width.value_mm)
            points = detail.geometry.points_mm
            outside = any(
                point.x < -_DETAIL_TOLERANCE_MM
                or point.y < -_DETAIL_TOLERANCE_MM
                or point.x > length + _DETAIL_TOLERANCE_MM
                or point.y > width + _DETAIL_TOLERANCE_MM
                for point in points
            )
            if detail.geometry.kind == "circle":
                center, edge = points
                radius = hypot(edge.x - center.x, edge.y - center.y)
                outside = outside or (
                    radius <= _EPSILON
                    or center.x - radius < -_DETAIL_TOLERANCE_MM
                    or center.y - radius < -_DETAIL_TOLERANCE_MM
                    or center.x + radius > length + _DETAIL_TOLERANCE_MM
                    or center.y + radius > width + _DETAIL_TOLERANCE_MM
                )
                if detail_dimensions:
                    dimension_ref, dimension = detail_dimensions[0]
                    declared_nominal = resolver.nominal(dimension.expression)
                    declared_range = resolver.interval(dimension.expression)
                    geometry_diameter = 2.0 * radius
                    if (
                        abs(geometry_diameter - declared_nominal)
                        > _DETAIL_TOLERANCE_MM
                        or geometry_diameter
                        < declared_range[0] - _DETAIL_TOLERANCE_MM
                        or geometry_diameter
                        > declared_range[1] + _DETAIL_TOLERANCE_MM
                    ):
                        resolver.issue(
                            "error",
                            "construction_detail_dimension_mismatch",
                            f"Detail {detail.id} geometry disagrees with {dimension_ref}.",
                            f"detail:{detail.id}",
                            dimension_ref,
                        )
            if outside:
                resolver.issue(
                    "error",
                    "construction_detail_out_of_bounds",
                    f"Detail {detail.id} falls outside piece {component_id}.",
                    f"detail:{detail.id}",
                    f"component:{component_id}.geometry",
                )
    results: list[GeneralConstraintResult] = []
    has_unknown = False
    for constraint in proposal.construction_constraints:
        left = _sum_refs(resolver, constraint.left_refs)
        right = _sum_refs(resolver, constraint.right_refs)
        if left is None or right is None:
            has_unknown = True
            results.append(
                GeneralConstraintResult(
                    constraint_id=constraint.id,
                    status="unknown",
                    left_range_mm=None,
                    right_range_mm=None,
                    residual_mm=None,
                )
            )
            resolver.issue(
                constraint.severity,
                "construction_constraint_unresolved",
                f"Constraint {constraint.id} has unresolved operands.",
                f"constraint:{constraint.id}",
            )
            continue

        left_interval = resolver.interval(left.expression)
        right_interval = resolver.interval(right.expression)
        difference = left.expression.plus(right.expression, -1.0)
        difference_interval = resolver.interval(difference)
        signed_residual = resolver.nominal(difference)
        if constraint.kind == "greater_equal":
            if difference_interval[0] >= -constraint.tolerance_mm:
                status = "pass"
            elif difference_interval[1] < -constraint.tolerance_mm:
                status = "fail"
            else:
                status = "unknown"
            residual = max(0.0, -signed_residual)
        else:
            if (
                difference_interval[0] >= -constraint.tolerance_mm
                and difference_interval[1] <= constraint.tolerance_mm
            ):
                status = "pass"
            elif (
                difference_interval[0] > constraint.tolerance_mm
                or difference_interval[1] < -constraint.tolerance_mm
            ):
                status = "fail"
            else:
                status = "unknown"
            residual = abs(signed_residual)
        if status == "unknown":
            has_unknown = True
        if status == "fail":
            resolver.issue(
                constraint.severity,
                "construction_constraint_failed",
                f"Constraint {constraint.id} exceeds its tolerance.",
                f"constraint:{constraint.id}",
            )
        results.append(
            GeneralConstraintResult(
                constraint_id=constraint.id,
                status=status,
                left_range_mm=_range(left_interval),
                right_range_mm=_range(right_interval),
                residual_mm=residual,
            )
        )

    incomplete_codes = {
        "construction_parameter_unresolved",
        "construction_constraint_unresolved",
    }
    has_unknown = detail_unknown or has_unknown or any(
        item.code in incomplete_codes for item in resolver.issues
    )
    invalid = any(
        item.severity == "error" and item.code not in incomplete_codes
        for item in resolver.issues
    )
    status = "invalid" if invalid else "incomplete" if has_unknown else "valid"
    return GeneralConstructionValidation(
        status=status,
        parameter_order=tuple(resolver.parameter_order),
        max_depth=resolver.max_depth,
        constraint_results=tuple(results),
        issues=tuple(resolver.issues),
    )


__all__ = ["validate_construction_scenario"]
