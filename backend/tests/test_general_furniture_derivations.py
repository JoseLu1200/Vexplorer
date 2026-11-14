from __future__ import annotations

from backend.app.contratos.modelos import (
    GeneralComponentReview,
    GeneralFurnitureReview,
    GeneralOccurrence,
    GeneralQuantity,
    GeneralTextValue,
    GeneralValue,
)
from backend.app.general_furniture.derivations import _bom_csv, derive_general_package


def _review() -> GeneralFurnitureReview:
    component = GeneralComponentReview(
        id="side", label="Lateral", kind="panel", role="side_panel",
        length=GeneralValue(value_mm=720, state="confirmed", dependency_refs=("human:length",)),
        width=GeneralValue(value_mm=400, state="derived", dependency_refs=("dimension:depth",)),
        thickness=GeneralValue(value_mm=None, state="unknown"),
        quantity=GeneralQuantity(value=2, state="confirmed", dependency_refs=("human:quantity",)),
        material=GeneralTextValue(value=None, state="unknown"), finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=("side-proposal",), source_view_ids=("front",),
        source_observation_ids=("obs",), source_evidence_ids=("ev",), source_dimension_ids=("depth",),
        assumptions=(), unknown_fields=("thickness", "material", "finish", "placement"),
    )
    return GeneralFurnitureReview(
        run_id="run-1", proposal_id="proposal-1", proposal_revision=1, review_revision=1,
        reviewer_name="tecnica", reason="Revisión parcial", reviewed_at="2026-11-14T12:00:00+00:00",
        operations=(), components=(component,),
        occurrences=(GeneralOccurrence(id="side:1", component_id="side", occurrence_index=1), GeneralOccurrence(id="side:2", component_id="side", occurrence_index=2)),
        status="reviewed_incomplete",
    )


def test_derivations_keep_unknowns_and_never_invent_3d_placement_or_cost() -> None:
    package = derive_general_package(_review())

    assert package.status == "incomplete"
    assert package.bom_rows[0].occurrence_ids == ("side:1", "side:2")
    assert package.bom_rows[0].thickness.state == "unknown"
    assert package.scene.items[0].position_mm is None
    assert package.scene.items[0].status == "schematic_unplaced"
    assert package.cost_basis.contributors[0].area_m2 == 0.576
    assert package.cost_basis.contributors[0].volume_m3 is None
    assert "thickness" in package.cost_basis.contributors[0].missing_data


def test_derivations_emit_auditable_csv_svg_dxf_and_json_artifacts() -> None:
    package = derive_general_package(_review())

    assert {item.kind for item in package.artifacts} == {"bom_csv", "bom_json", "drawing_svg", "drawing_dxf"}
    assert all(item.content for item in package.artifacts)
    assert all(item.review_revision == 1 for item in package.artifacts)


def test_csv_labels_provisional_quantity_separately_from_physical_occurrences() -> None:
    row = derive_general_package(_review()).bom_rows[0].model_copy(
        update={
            "quantity": GeneralQuantity(
                value=2, state="hypothesis", dependency_refs=("premise:two-sides",)
            ),
            "occurrence_ids": (),
            "scenario_occurrence_ids": ("scenario:side:1", "scenario:side:2"),
            "occurrence_status": "provisional",
        }
    )

    csv_text = _bom_csv((row,)).decode("utf-8-sig")

    header, values = csv_text.splitlines()[:2]
    assert "quantity_state" in header
    assert "occurrence_status" in header
    assert "physical_occurrence_ids" in header
    assert "scenario_occurrence_ids" in header
    assert "hypothesis" in values
    assert "provisional" in values
    assert "scenario:side:1|scenario:side:2" in values
