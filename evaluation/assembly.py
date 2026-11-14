"""Independent geometry evaluator for frozen furniture assembly scenes.

The runtime never imports this module.  It accepts public scene output and an
evaluator-only reference, normalizes both to oriented boxes, and finds exactly
one proper orthogonal transform plus one bijective occurrence assignment.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Sequence


class AssemblyEvaluationError(ValueError):
    """Raised when an assembly artifact is malformed or ambiguous."""


Vector = tuple[float, float, float]
Matrix = tuple[Vector, Vector, Vector]
_AXIS_NAMES = ("length", "width", "thickness")
_IDENTITY: Matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@dataclass(frozen=True)
class _Box:
    identifier: str
    center: Vector
    dimensions: Vector
    axes: Matrix  # local length/width/thickness axes expressed in world coordinates
    normal: Vector

    def transformed(self, rotation: Matrix, translation: Vector) -> "_Box":
        return _Box(
            identifier=self.identifier,
            center=_add(_mat_vec(rotation, self.center), translation),
            dimensions=self.dimensions,
            axes=tuple(_mat_vec(rotation, axis) for axis in self.axes),  # type: ignore[arg-type]
            normal=_mat_vec(rotation, self.normal),
        )

    def aabb(self) -> tuple[Vector, Vector]:
        half = tuple(
            sum(abs(self.axes[local][world]) * self.dimensions[local] for local in range(3)) / 2
            for world in range(3)
        )
        return _sub(self.center, half), _add(self.center, half)


def _add(left: Vector, right: Vector) -> Vector:
    return tuple(left[index] + right[index] for index in range(3))  # type: ignore[return-value]


def _sub(left: Vector, right: Vector) -> Vector:
    return tuple(left[index] - right[index] for index in range(3))  # type: ignore[return-value]


def _scale(vector: Vector, factor: float) -> Vector:
    return tuple(value * factor for value in vector)  # type: ignore[return-value]


def _dot(left: Vector, right: Vector) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _norm(vector: Vector) -> float:
    return math.sqrt(_dot(vector, vector))


def _distance(left: Vector, right: Vector) -> float:
    return _norm(_sub(left, right))


def _mat_vec(matrix: Matrix, vector: Vector) -> Vector:
    return tuple(_dot(row, vector) for row in matrix)  # type: ignore[return-value]


def _determinant(matrix: Matrix) -> int:
    value = (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )
    return int(round(value))


def _proper_rotations() -> tuple[Matrix, ...]:
    rotations: list[Matrix] = []
    for permutation in itertools.permutations(range(3)):
        for signs in itertools.product((-1.0, 1.0), repeat=3):
            rows = tuple(
                tuple(signs[row] if permutation[row] == column else 0.0 for column in range(3))
                for row in range(3)
            )
            matrix: Matrix = rows  # type: ignore[assignment]
            if _determinant(matrix) == 1:
                rotations.append(matrix)
    return tuple(sorted(rotations))


_ROTATIONS = _proper_rotations()


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssemblyEvaluationError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        qualifier = "positive and " if positive else ""
        raise AssemblyEvaluationError(f"{label} must be {qualifier}finite")
    return result


def _vector(value: Any, label: str) -> Vector:
    if isinstance(value, dict) and set(("x", "y", "z")) <= set(value):
        raw = [value[name] for name in ("x", "y", "z")]
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        raw = value
    else:
        raise AssemblyEvaluationError(f"{label} must be [x,y,z] or an x/y/z object")
    return tuple(_number(item, f"{label}[{index}]") for index, item in enumerate(raw))  # type: ignore[return-value]


def _orientation(value: Any, label: str) -> Matrix:
    if not isinstance(value, dict):
        raise AssemblyEvaluationError(f"{label} must be an object")
    axes_list = []
    for name in _AXIS_NAMES:
        raw_axis = value.get(name, value.get(f"{name}_axis"))
        if isinstance(raw_axis, str) and raw_axis in {"+x", "-x", "+y", "-y", "+z", "-z"}:
            sign = 1.0 if raw_axis[0] == "+" else -1.0
            axis = tuple(sign if raw_axis[1] == world else 0.0 for world in "xyz")
        else:
            axis = _vector(raw_axis, f"{label}.{name}")
        axes_list.append(axis)
    axes = tuple(axes_list)
    if any(abs(_norm(axis) - 1.0) > 1e-8 for axis in axes) or any(
        abs(_dot(axes[left], axes[right])) > 1e-8
        for left in range(3)
        for right in range(left + 1, 3)
    ):
        raise AssemblyEvaluationError(f"{label} must be proper orthogonal signed unit axes")
    if any(abs(abs(component) - 1.0) > 1e-8 for axis in axes for component in axis if component):
        raise AssemblyEvaluationError(f"{label} must use signed world axes")
    axes_matrix: Matrix = axes  # type: ignore[assignment]
    if _determinant(axes_matrix) != 1:
        raise AssemblyEvaluationError(f"{label} must be a proper orthogonal frame")
    return axes  # type: ignore[return-value]


def _dimensions(value: Any, label: str) -> Vector:
    if isinstance(value, dict):
        raw = [value.get(name) for name in _AXIS_NAMES]
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        raw = value
    else:
        raise AssemblyEvaluationError(f"{label} must contain length, width and thickness")
    return tuple(_number(item, f"{label}.{name}", positive=True) for name, item in zip(_AXIS_NAMES, raw))  # type: ignore[return-value]


def _identifier(row: dict[str, Any], index: int) -> str:
    value = row.get("id", row.get("occurrence_id", row.get("source_index", index)))
    return str(value)


def _canonical_box(row: Any, index: int, label: str) -> _Box:
    if not isinstance(row, dict):
        raise AssemblyEvaluationError(f"{label}[{index}] must be an object")
    axes = _orientation(row.get("orientation", {}), f"{label}[{index}].orientation")
    dimensions = _dimensions(row.get("dimensions_mm"), f"{label}[{index}].dimensions_mm")
    position = _vector(row.get("position_mm"), f"{label}[{index}].position_mm")
    position_kind = row.get("position_kind", "local_corner")
    if position_kind == "center":
        center = position
    elif position_kind == "local_corner":
        center = position
        for dimension, axis in zip(dimensions, axes):
            center = _add(center, _scale(axis, dimension / 2))
    elif position_kind == "world_aabb_min":
        minimum, maximum = _aabb_from_axes_at_origin(dimensions, axes)
        extents = _sub(maximum, minimum)
        center = _add(position, _scale(extents, 0.5))
    else:
        raise AssemblyEvaluationError(f"{label}[{index}].position_kind is unsupported")
    normal = _vector(row["normal"], f"{label}[{index}].normal") if row.get("normal") is not None else axes[2]
    if abs(_norm(normal) - 1.0) > 1e-8:
        raise AssemblyEvaluationError(f"{label}[{index}].normal must be a unit vector")
    return _Box(_identifier(row, index), center, dimensions, axes, normal)


def _aabb_from_axes_at_origin(dimensions: Vector, axes: Matrix) -> tuple[Vector, Vector]:
    points = []
    for choices in itertools.product((0.0, 1.0), repeat=3):
        point: Vector = (0.0, 0.0, 0.0)
        for local in range(3):
            point = _add(point, _scale(axes[local], dimensions[local] * choices[local]))
        points.append(point)
    return (
        tuple(min(point[axis] for point in points) for axis in range(3)),  # type: ignore[arg-type]
        tuple(max(point[axis] for point in points) for axis in range(3)),  # type: ignore[arg-type]
    )


def _placement_box(row: Any, index: int, label: str) -> _Box:
    if not isinstance(row, dict):
        raise AssemblyEvaluationError(f"{label}[{index}] must be an object")
    axes = _orientation(row.get("orientation", {}), f"{label}[{index}].orientation")
    world_size = _vector(row.get("size_mm"), f"{label}[{index}].size_mm")
    if any(value <= 0 for value in world_size):
        raise AssemblyEvaluationError(f"{label}[{index}].size_mm must be positive")
    dimensions = tuple(
        world_size[next(world for world, value in enumerate(axis) if abs(value) > 0.5)]
        for axis in axes
    )
    minimum = _vector(row.get("position_mm"), f"{label}[{index}].position_mm")
    center = _add(minimum, _scale(world_size, 0.5))
    return _Box(_identifier(row, index), center, dimensions, axes, axes[2])  # type: ignore[arg-type]


def _bounds_box(row: Any, index: int, label: str) -> _Box:
    if not isinstance(row, dict):
        raise AssemblyEvaluationError(f"{label}[{index}] must be an object")
    bounds = row.get("bounds_mm")
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 6:
        raise AssemblyEvaluationError(f"{label}[{index}].bounds_mm must have six numbers")
    values = tuple(_number(value, f"{label}[{index}].bounds_mm") for value in bounds)
    minimum = values[:3]
    maximum = values[3:]
    dimensions = _sub(maximum, minimum)  # type: ignore[arg-type]
    if any(value <= 0 for value in dimensions):
        raise AssemblyEvaluationError(f"{label}[{index}].bounds_mm must have positive extents")
    normal = _vector(row["normal"], f"{label}[{index}].normal") if row.get("normal") is not None else _IDENTITY[2]
    return _Box(
        _identifier(row, index),
        _scale(_add(minimum, maximum), 0.5),  # type: ignore[arg-type]
        dimensions,
        _IDENTITY,
        normal,
    )


def _boxes(payload: Any, label: str) -> list[_Box]:
    if not isinstance(payload, dict):
        raise AssemblyEvaluationError(f"{label} must be an object")
    if isinstance(payload.get("assembly_attempt"), dict):
        return _boxes(payload["assembly_attempt"], f"{label}.assembly_attempt")
    if isinstance(payload.get("report"), dict):
        return _boxes(payload["report"], f"{label}.report")
    if isinstance(payload.get("pieces"), list):
        rows, adapter = payload["pieces"], _canonical_box
    elif isinstance(payload.get("placements"), list):
        rows, adapter = payload["placements"], _placement_box
    elif isinstance(payload.get("components"), list) and all(
        isinstance(row, dict) and "bounds_mm" in row for row in payload["components"]
    ):
        rows, adapter = payload["components"], _bounds_box
    elif isinstance(payload.get("scene"), dict) and isinstance(payload["scene"].get("items"), list):
        rows = payload["scene"]["items"]
        adapter = _placement_box if all(isinstance(row, dict) and "size_mm" in row for row in rows) else _canonical_box
    else:
        raise AssemblyEvaluationError(
            f"{label} must expose pieces, placements, bounds components, or scene.items"
        )
    result = [adapter(row, index, f"{label}.{adapter.__name__}") for index, row in enumerate(rows)]
    identifiers = [box.identifier for box in result]
    if len(identifiers) != len(set(identifiers)):
        raise AssemblyEvaluationError(f"{label} contains duplicate occurrence ids")
    return result


def _axis_match(predicted: _Box, reference: _Box) -> tuple[float, float, tuple[int, int, int]]:
    best: tuple[float, float, tuple[int, int, int]] | None = None
    for permutation in itertools.permutations(range(3)):
        dimension_error = max(
            abs(predicted.dimensions[local] - reference.dimensions[permutation[local]])
            for local in range(3)
        )
        axis_error = max(
            math.degrees(math.acos(min(1.0, abs(_dot(predicted.axes[local], reference.axes[permutation[local]])))))
            for local in range(3)
        )
        candidate = (dimension_error, axis_error, permutation)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return best


def _intrinsic_cost(predicted: _Box, reference: _Box) -> float:
    dimension_error, axis_error, _ = _axis_match(predicted, reference)
    normal_error = 1.0 - abs(_dot(predicted.normal, reference.normal))
    return 100.0 * dimension_error**2 + 1_000.0 * axis_error**2 + 1_000_000.0 * normal_error**2


def _hungarian(cost: Sequence[Sequence[float]]) -> list[int]:
    """Return a deterministic minimum-cost row-to-column assignment (O(n^3))."""
    size = len(cost)
    if size == 0 or any(len(row) != size for row in cost):
        raise AssemblyEvaluationError("internal matching matrix must be non-empty and square")
    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    matched_row = [0] * (size + 1)
    path = [0] * (size + 1)
    for row in range(1, size + 1):
        matched_row[0] = row
        minimum = [math.inf] * (size + 1)
        used = [False] * (size + 1)
        column = 0
        while True:
            used[column] = True
            current_row = matched_row[column]
            delta = math.inf
            next_column = 0
            for candidate_column in range(1, size + 1):
                if used[candidate_column]:
                    continue
                reduced = cost[current_row - 1][candidate_column - 1] - u[current_row] - v[candidate_column]
                if reduced < minimum[candidate_column]:
                    minimum[candidate_column] = reduced
                    path[candidate_column] = column
                if minimum[candidate_column] < delta:
                    delta = minimum[candidate_column]
                    next_column = candidate_column
            for candidate_column in range(size + 1):
                if used[candidate_column]:
                    u[matched_row[candidate_column]] += delta
                    v[candidate_column] -= delta
                else:
                    minimum[candidate_column] -= delta
            column = next_column
            if matched_row[column] == 0:
                break
        while True:
            previous = path[column]
            matched_row[column] = matched_row[previous]
            column = previous
            if column == 0:
                break
    assignment = [-1] * size
    for column in range(1, size + 1):
        if matched_row[column]:
            assignment[matched_row[column] - 1] = column - 1
    return assignment


def _assignment(
    predicted: list[_Box],
    reference: list[_Box],
    intrinsic: Sequence[Sequence[float]] | None = None,
) -> tuple[list[tuple[int, int]], float]:
    size = max(len(predicted), len(reference))
    real_costs = [
        [
            _distance(left.center, right.center) ** 2
            + (intrinsic[row][column] if intrinsic is not None else _intrinsic_cost(left, right))
            for column, right in enumerate(reference)
        ]
        for row, left in enumerate(predicted)
    ]
    largest = max((value for row in real_costs for value in row), default=1.0)
    dummy = largest * (size + 1) + 1_000_000_000.0
    square = [
        [real_costs[row][column] if row < len(predicted) and column < len(reference) else dummy for column in range(size)]
        for row in range(size)
    ]
    selected = _hungarian(square)
    pairs = [(row, column) for row, column in enumerate(selected) if row < len(predicted) and column < len(reference)]
    return pairs, sum(real_costs[row][column] for row, column in pairs)


def _candidate_translations(predicted: list[_Box], reference: list[_Box]) -> Iterable[Vector]:
    compatible = []
    for left in predicted:
        signature_left = sorted(left.dimensions)
        for right in reference:
            if max(abs(a - b) for a, b in zip(signature_left, sorted(right.dimensions))) < 1e-6:
                compatible.append(_sub(right.center, left.center))
    candidates = compatible or [_sub(right.center, left.center) for left in predicted for right in reference]
    return sorted(set(candidates))


def _align(predicted: list[_Box], reference: list[_Box]) -> tuple[Matrix, Vector, list[_Box], list[tuple[int, int]]]:
    if not predicted or not reference:
        return _IDENTITY, (0.0, 0.0, 0.0), predicted, []
    best: tuple[float, Matrix, Vector, list[_Box], list[tuple[int, int]]] | None = None
    for rotation in _ROTATIONS:
        rotated = [box.transformed(rotation, (0.0, 0.0, 0.0)) for box in predicted]
        intrinsic = [[_intrinsic_cost(left, right) for right in reference] for left in rotated]
        for translation in _candidate_translations(rotated, reference):
            transformed = [box.transformed(_IDENTITY, translation) for box in rotated]
            pairs, cost = _assignment(transformed, reference, intrinsic)
            # An anchor difference only seeds the discrete bijection.  Once a
            # bijection exists, least-squares center alignment supplies the
            # one translation shared by every occurrence.  Reassigning after
            # refinement keeps the process deterministic without allowing
            # any per-piece transform.
            for _ in range(4):
                if not pairs:
                    break
                optimized = tuple(
                    sum(reference[right].center[axis] - rotated[left].center[axis] for left, right in pairs)
                    / len(pairs)
                    for axis in range(3)
                )
                transformed = [box.transformed(_IDENTITY, optimized) for box in rotated]
                refined_pairs, cost = _assignment(transformed, reference, intrinsic)
                stable = refined_pairs == pairs
                translation = optimized  # type: ignore[assignment]
                pairs = refined_pairs
                if stable:
                    break
            candidate = (cost, rotation, translation, transformed, pairs)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    assert best is not None
    return best[1], best[2], best[3], best[4]


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"max": None, "mean": None, "rmse": None}
    return {
        "max": max(values),
        "mean": sum(values) / len(values),
        "rmse": math.sqrt(sum(value * value for value in values) / len(values)),
    }


def _face_error(left: _Box, right: _Box) -> float:
    left_min, left_max = left.aabb()
    right_min, right_max = right.aabb()
    return max(*(abs(a - b) for a, b in zip(left_min, right_min)), *(abs(a - b) for a, b in zip(left_max, right_max)))


def _penetration(left: _Box, right: _Box) -> float:
    left_min, left_max = left.aabb()
    right_min, right_max = right.aabb()
    overlaps = [min(left_max[axis], right_max[axis]) - max(left_min[axis], right_min[axis]) for axis in range(3)]
    return min(overlaps) if all(value > 0 for value in overlaps) else 0.0


def _scene_diagonal(boxes: list[_Box]) -> float:
    if not boxes:
        return 0.0
    bounds = [box.aabb() for box in boxes]
    minimum = tuple(min(bound[0][axis] for bound in bounds) for axis in range(3))
    maximum = tuple(max(bound[1][axis] for bound in bounds) for axis in range(3))
    return _distance(minimum, maximum)  # type: ignore[arg-type]


def evaluate_assembly(
    prediction: dict[str, Any],
    reference: dict[str, Any],
    *,
    tolerance_mm: float = 1.0,
) -> dict[str, Any]:
    """Evaluate two assembly scenes without exposing the reference to runtime code."""
    tolerance = _number(tolerance_mm, "tolerance_mm", positive=True)
    predicted = _boxes(prediction, "prediction")
    expected = _boxes(reference, "reference")
    rotation, translation, aligned, pairs = _align(predicted, expected)

    center_errors = [_distance(aligned[left].center, expected[right].center) for left, right in pairs]
    face_errors = [_face_error(aligned[left], expected[right]) for left, right in pairs]
    axis_results = [_axis_match(aligned[left], expected[right]) for left, right in pairs]
    dimension_errors = [result[0] for result in axis_results]
    axis_errors = [result[1] for result in axis_results]
    normal_errors = [
        math.degrees(math.acos(min(1.0, abs(_dot(aligned[left].normal, expected[right].normal)))))
        for left, right in pairs
    ]

    matched_reference = {right: left for left, right in pairs}
    unexplained: list[float] = []
    predicted_penetrations: list[float] = []
    reference_penetrations: list[float] = []
    for first, second in itertools.combinations(sorted(matched_reference), 2):
        predicted_depth = _penetration(aligned[matched_reference[first]], aligned[matched_reference[second]])
        reference_depth = _penetration(expected[first], expected[second])
        predicted_penetrations.append(predicted_depth)
        reference_penetrations.append(reference_depth)
        unexplained.append(max(0.0, predicted_depth - reference_depth))

    reference_count = len(expected)
    predicted_count = len(predicted)
    matched_count = len(pairs)
    diagonal = _scene_diagonal(expected)
    normalized_centers = [value / diagonal for value in center_errors] if diagonal else center_errors
    normalized_faces = [value / diagonal for value in face_errors] if diagonal else face_errors
    counts = {
        "reference": reference_count,
        "predicted": predicted_count,
        "matched": matched_count,
        "missing": max(0, reference_count - matched_count),
        "extra": max(0, predicted_count - matched_count),
    }
    within_tolerance = sum(
        center < tolerance and face < tolerance and dimension < tolerance and axis < 1e-6 and normal < 1e-6
        for center, face, dimension, axis, normal in zip(
            center_errors, face_errors, dimension_errors, axis_errors, normal_errors
        )
    )
    max_unexplained = max(unexplained, default=0.0)
    passed = (
        reference_count > 0
        and counts["missing"] == 0
        and counts["extra"] == 0
        and within_tolerance == reference_count
        and max_unexplained <= tolerance
    )

    available_views = {"front_xy": (0, 1), "top_xz": (0, 2), "side_yz": (1, 2)}
    declared_views = reference.get("used_views")
    if declared_views is None:
        view_axes = available_views
    else:
        if (
            not isinstance(declared_views, list)
            or not declared_views
            or len(declared_views) != len(set(declared_views))
            or any(view not in available_views for view in declared_views)
        ):
            raise AssemblyEvaluationError(
                "reference.used_views must be unique supported orthographic view names"
            )
        view_axes = {view: available_views[view] for view in declared_views}
    reprojection = {}
    for view, axes in view_axes.items():
        errors = []
        for left, right in pairs:
            left_bounds, right_bounds = aligned[left].aabb(), expected[right].aabb()
            errors.append(max(abs(left_bounds[bound][axis] - right_bounds[bound][axis]) for bound in (0, 1) for axis in axes))
        reprojection[view] = _summary(errors)

    return {
        "passed": passed,
        "passes_reference_relative_acceptance": passed,
        "collision_free_at_tolerance": max(predicted_penetrations, default=0.0) <= tolerance,
        "tolerance_mm": tolerance,
        "counts": counts,
        "coverage": matched_count / reference_count if reference_count else 0.0,
        "precision": matched_count / predicted_count if predicted_count else 0.0,
        "within_tolerance": within_tolerance,
        "alignment": {
            "rotation": [list(row) for row in rotation],
            "translation_mm": list(translation),
            "determinant": _determinant(rotation),
        },
        "center_error_mm": _summary(center_errors),
        "face_error_mm": _summary(face_errors),
        "dimension_error_mm": _summary(dimension_errors),
        "normalized_by_reference_diagonal": {
            "reference_diagonal_mm": diagonal,
            "center": _summary(normalized_centers),
            "face": _summary(normalized_faces),
        },
        "orientation": {
            "all_axes_equivalent": all(value < 1e-6 for value in axis_errors),
            "all_normals_agree": all(value < 1e-6 for value in normal_errors),
            "max_axis_error_degrees": max(axis_errors, default=0.0),
            "max_normal_error_degrees": max(normal_errors, default=0.0),
        },
        "penetration": {
            "predicted_max_mm": max(predicted_penetrations, default=0.0),
            "predicted_pairs_over_tolerance": sum(
                value > tolerance for value in predicted_penetrations
            ),
            "reference_max_mm": max(reference_penetrations, default=0.0),
            "reference_pairs_over_tolerance": sum(
                value > tolerance for value in reference_penetrations
            ),
            "max_unexplained_mm": max_unexplained,
            "unexplained_pairs": sum(value > tolerance for value in unexplained),
        },
        "bijection": {
            "unique_predictions": len({left for left, _ in pairs}) == len(pairs),
            "unique_references": len({right for _, right in pairs}) == len(pairs),
            "reference_reuse": len(pairs) - len({right for _, right in pairs}),
        },
        "reprojection": reprojection,
        "matches": [
            {
                "prediction_id": predicted[left].identifier,
                "reference_id": expected[right].identifier,
                "center_error_mm": center_errors[index],
                "face_error_mm": face_errors[index],
                "dimension_error_mm": dimension_errors[index],
            }
            for index, (left, right) in enumerate(pairs)
        ],
    }


def evaluate_assembly_files(
    prediction_path: str | Path,
    reference_path: str | Path,
    *,
    tolerance_mm: float = 1.0,
) -> dict[str, Any]:
    """Evaluate a hash-bound frozen output, opening the private oracle second."""
    try:
        # Ordering is intentional: the public output is completely frozen in
        # memory and hashed before the evaluator-only reference is opened.
        prediction_bytes = Path(prediction_path).read_bytes()
        prediction = json.loads(prediction_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssemblyEvaluationError(f"cannot read frozen prediction: {exc}") from exc
    if not isinstance(prediction, dict):
        raise AssemblyEvaluationError("frozen prediction must be an object")
    digest = hashlib.sha256(prediction_bytes).hexdigest()

    try:
        reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssemblyEvaluationError(f"cannot read evaluator reference: {exc}") from exc
    if not isinstance(reference, dict):
        raise AssemblyEvaluationError("evaluator reference must be an object")
    expected_digest = reference.get("prediction_sha256")
    if not isinstance(expected_digest, str) or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
        raise AssemblyEvaluationError("reference.prediction_sha256 must be lowercase 64-hex")
    if digest != expected_digest:
        raise AssemblyEvaluationError("prediction_sha256 mismatch")
    policy = reference.get("access_policy")
    if not isinstance(policy, dict) or policy.get("evaluator_only") is not True or policy.get("runtime_allowed") is not False:
        raise AssemblyEvaluationError("reference access_policy must be evaluator-only")

    report = evaluate_assembly(prediction, reference, tolerance_mm=tolerance_mm)
    return {**report, "frozen_prediction_sha256": digest}
