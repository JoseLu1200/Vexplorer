import json
from pathlib import Path

import pytest

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    DescriptorPartFeature,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    TableDescriptorComponentFeature,
)
from tools.semantic_lab.components import compare_components, main


STATES = {
    "quantity": "confirmed",
    "length_mm": "confirmed",
    "width_mm": "confirmed",
    "thickness_mm": "confirmed",
}


def component(
    role: str,
    quantity: int,
    length: float,
    width: float,
    thickness: float,
    material: str | None = "board-a",
) -> TableDescriptorComponentFeature:
    return TableDescriptorComponentFeature(
        role=role,
        quantity=quantity,
        length_mm=length,
        width_mm=width,
        thickness_mm=thickness,
        material_tariff_id=material,
        field_states=STATES,
    )


def table(*components: TableDescriptorComponentFeature) -> FurnitureDescriptorV3:
    return FurnitureDescriptorV3(
        dimensions=DescriptorDimensions(width_mm=1200, depth_mm=600, height_mm=750),
        structure="side_support_table",
        components=components,
        material_tariff_id=None,
    )


def test_exact_composition_is_independent_of_component_order_and_planar_orientation() -> None:
    left = table(
        component("tabletop", 1, 1200, 600, 30),
        component("side_support", 2, 720, 550, 18),
    )
    reordered = table(
        component("side_support", 2, 720, 550, 18),
        component("tabletop", 1, 600, 1200, 30),
    )

    result = compare_components(left, reordered)

    assert result["score"] == pytest.approx(1.0)
    assert result["coverage"] == pytest.approx(1.0)
    assert result["differences"] == []
    assert result["components"]["matching"]["matched_quantity"] == 3
    assert result["components"]["matching"]["expanded_occurrences"] == 0


def test_support_width_change_is_visible_and_reduces_similarity() -> None:
    baseline = table(
        component("tabletop", 1, 1200, 600, 30),
        component("side_support", 2, 720, 550, 18),
    )
    narrower = table(
        component("tabletop", 1, 1200, 600, 30),
        component("side_support", 2, 720, 200, 18),
    )

    result = compare_components(baseline, narrower)

    assert result["score"] < 0.9
    assert result["components"]["width_mm"]["score"] < 0.7
    assert any(diff["field"] == "width_mm" and diff["role"] == "side_support" for diff in result["differences"])


def test_double_thickness_and_known_material_change_are_not_equivalent() -> None:
    baseline = table(component("tabletop", 1, 1200, 600, 18, "melamine-white"))
    thicker = table(component("tabletop", 1, 1200, 600, 36, "oak"))

    result = compare_components(baseline, thicker)

    assert result["score"] < 0.75
    assert result["components"]["thickness_mm"]["score"] < 0.6
    assert result["components"]["material"]["score"] == 0.0
    assert {item["field"] for item in result["differences"]} >= {"thickness_mm", "material"}


def test_unknown_v2_fields_reduce_coverage_and_cannot_make_a_perfect_match() -> None:
    unknown_part = DescriptorPartFeature(
        length_mm=800,
        width_mm=None,
        thickness_mm=None,
        quantity=None,
        unknown_fields=("width_mm", "thickness_mm", "quantity"),
        field_states={
            "length_mm": "observed",
            "width_mm": "unknown",
            "thickness_mm": "unknown",
            "quantity": "unknown",
        },
    )
    descriptor = FurnitureDescriptorV2(
        family="unknown",
        dimensions=DescriptorDimensions(),
        roles=(),
        structure="unknown",
        thicknesses_mm=(),
        classification_status="hypothesis",
        part_features=(unknown_part,),
        unknown_fields=("material",),
    )

    result = compare_components(descriptor, descriptor)

    assert 0 < result["coverage"] < 0.5
    assert result["score"] < 1.0
    assert result["components"]["width_mm"]["status"] == "unknown"
    assert result["components"]["matching"]["matched_quantity_kind"] == "observation_weight_not_physical_quantity"
    assert result["components"]["matching"]["unknown_quantity_observations"] == {"left": 1, "right": 1}
    assert any(item["kind"] == "unknown_evidence" for item in result["differences"])


def test_zero_affinity_v2_observations_still_match_to_expose_known_material_difference() -> None:
    feature = DescriptorPartFeature(
        unknown_fields=("length_mm", "width_mm", "thickness_mm", "quantity"),
        field_states={
            "length_mm": "unknown",
            "width_mm": "unknown",
            "thickness_mm": "unknown",
            "quantity": "unknown",
        },
    )

    def descriptor(material: str) -> FurnitureDescriptorV2:
        return FurnitureDescriptorV2(
            family="unknown",
            dimensions=DescriptorDimensions(),
            roles=(),
            structure="unknown",
            material=material,
            thicknesses_mm=(),
            classification_status="hypothesis",
            part_features=(feature,),
            unknown_fields=("dimensions", "quantity"),
        )

    result = compare_components(descriptor("board-a"), descriptor("board-b"))

    matching = result["components"]["matching"]
    assert matching["matched_quantity"] == 1
    assert matching["matched_quantity_kind"] == "observation_weight_not_physical_quantity"
    assert result["components"]["material"]["coverage"] == pytest.approx(1.0)
    assert result["components"]["material"]["score"] == 0.0
    assert any(item["field"] == "material" and item["kind"] == "value_difference" for item in result["differences"])


def test_heterogeneous_thicknesses_with_same_average_remain_distinguishable() -> None:
    heterogeneous = table(
        component("tabletop", 1, 1000, 500, 10),
        component("side_support", 1, 700, 500, 30),
    )
    same_average = table(
        component("tabletop", 1, 1000, 500, 20),
        component("side_support", 1, 700, 500, 20),
    )

    exact = compare_components(heterogeneous, heterogeneous)
    result = compare_components(heterogeneous, same_average)

    assert exact["score"] == pytest.approx(1.0)
    assert result["score"] < exact["score"]
    assert result["components"]["thickness_mm"]["score"] < 1.0
    assert sum(item["field"] == "thickness_mm" for item in result["differences"]) == 2


def test_quantity_matching_does_not_expand_large_component_counts() -> None:
    left = table(component("corner_support", 1_000_000, 700, 60, 60))
    right = table(component("corner_support", 999_999, 700, 60, 60))

    result = compare_components(left, right)

    assert result["components"]["matching"]["matched_quantity"] == 999_999
    assert result["components"]["matching"]["unmatched_left_quantity"] == 1
    assert result["components"]["matching"]["expanded_occurrences"] == 0
    assert result["score"] < 1.0


def test_known_roles_cannot_exchange_quantities_even_when_geometry_matches() -> None:
    left = table(
        component("tabletop", 2, 700, 500, 18),
        component("side_support", 1, 700, 500, 18),
    )
    swapped_quantities = table(
        component("tabletop", 1, 700, 500, 18),
        component("side_support", 2, 700, 500, 18),
    )

    result = compare_components(left, swapped_quantities)

    assert result["components"]["matching"]["matched_quantity"] == 2
    assert result["components"]["matching"]["unmatched_left_quantity"] == 1
    assert result["score"] < 0.8
    assert any(item["field"] == "role" for item in result["differences"])


def test_grouping_repeated_role_components_does_not_change_score_or_coverage() -> None:
    grouped = table(component("side_support", 2, 720, 550, 18))
    split = table(
        component("side_support", 1, 720, 550, 18),
        component("side_support", 1, 720, 550, 18),
    )

    result = compare_components(grouped, split)

    assert result["score"] == pytest.approx(1.0)
    assert result["coverage"] == pytest.approx(1.0)
    assert result["components"]["role"]["score"] == pytest.approx(1.0)
    assert result["differences"] == []


def test_score_and_coverage_are_symmetric() -> None:
    left = table(
        component("tabletop", 1, 1200, 600, 30, "board-a"),
        component("side_support", 2, 720, 550, 18, "board-a"),
    )
    right = table(
        component("tabletop", 1, 1200, 600, 36, "board-b"),
        component("side_support", 1, 720, 200, 18, "board-a"),
    )

    forward = compare_components(left, right)
    reverse = compare_components(right, left)

    assert forward["score"] == pytest.approx(reverse["score"])
    assert forward["coverage"] == pytest.approx(reverse["coverage"])


def test_synthetic_control_cli_writes_an_explicitly_labeled_json_report(tmp_path: Path) -> None:
    destination = tmp_path / "components-control.json"

    assert main(["control", "--output", str(destination)]) == 0
    report = json.loads(destination.read_text(encoding="utf-8"))

    assert report["evidence_kind"] == "synthetic-control"
    assert report["claims"] == {"real_accuracy": False, "cost_equivalence": False}
    assert {case["id"] for case in report["cases"]} >= {
        "exact_reordered",
        "support_width_changed",
        "thickness_doubled",
        "material_changed",
    }
