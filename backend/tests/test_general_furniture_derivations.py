from __future__ import annotations

import csv
import io
import json

import ezdxf
import pytest

from backend.app.contratos.modelos import (
    GeneralAutoReviewCheck,
    GeneralComponentReview,
    GeneralFurnitureReview,
    GeneralMachineFieldReview,
    GeneralMachineProvenance,
    GeneralOccurrence,
    GeneralQuantity,
    GeneralScenarioOccurrence,
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


def _machine_review(*, length_status: str, quantity_status: str) -> GeneralFurnitureReview:
    component = GeneralComponentReview(
        id="machine-side", label="Lateral propuesto", kind="panel", role="side_panel",
        length=GeneralValue(
            value_mm=720, state="hypothesis",
            dependency_refs=("measurement:contour:side:span-y",),
        ),
        width=GeneralValue(
            value_mm=400, state="hypothesis",
            dependency_refs=("measurement:contour:side:span-x",),
        ),
        thickness=GeneralValue(value_mm=None, state="unknown"),
        quantity=GeneralQuantity(
            value=2, state="hypothesis", dependency_refs=("premise:two-sides",),
        ),
        material=GeneralTextValue(value=None, state="unknown"),
        finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=("machine-side",),
        source_document_refs=("document:page-1",),
        assumptions=("Interpretación provisional.",),
        unknown_fields=("thickness", "material", "finish"),
    )
    checks = (
        GeneralAutoReviewCheck(
            id="length-check", kind="visual_consistency",
            outcome="pass" if length_status == "accepted" else "fail",
            method="model_visual", target_refs=("component:machine-side.length",),
            source_refs=("document:page-1",), summary="Contraste visual del largo.",
        ),
        GeneralAutoReviewCheck(
            id="width-check", kind="visual_consistency", outcome="pass",
            method="model_visual", target_refs=("component:machine-side.width",),
            source_refs=("document:page-1",), summary="Ancho coherente.",
        ),
        GeneralAutoReviewCheck(
            id="quantity-basis", kind="quantity_basis", outcome="pass",
            method="model_visual", target_refs=("component:machine-side.quantity",),
            source_refs=("document:page-1",), summary="Dos grupos candidatos.",
        ),
        GeneralAutoReviewCheck(
            id="duplicate-scan", kind="duplicate_scan", outcome="pass",
            method="model_visual", target_refs=("component:machine-side.quantity",),
            source_refs=("document:page-1",), summary="Escaneo de duplicados.",
        ),
    )
    field_reviews = (
        GeneralMachineFieldReview(
            target_ref="component:machine-side.length", status=length_status,
            check_ids=("length-check",),
        ),
        GeneralMachineFieldReview(
            target_ref="component:machine-side.width", status="accepted",
            check_ids=("width-check",),
        ),
        GeneralMachineFieldReview(
            target_ref="component:machine-side.quantity", status=quantity_status,
            check_ids=("quantity-basis", "duplicate-scan"),
        ),
    )
    scenario_occurrences = tuple(
        GeneralScenarioOccurrence(
            id=f"scenario:machine-side:{index}", component_id="machine-side",
            occurrence_index=index, scenario_id="scenario-machine",
            quantity_target_ref="component:machine-side.quantity",
            check_ids=("quantity-basis", "duplicate-scan"),
            premise_refs=("premise:two-sides",),
            source_refs=("document:page-1",),
        )
        for index in (1, 2)
    )
    return GeneralFurnitureReview(
        run_id="run-machine", proposal_id="proposal-machine",
        proposal_revision=1, review_revision=1,
        reviewer_name="autonomous-reviewer", reviewer_kind="machine",
        machine_provenance=GeneralMachineProvenance(
            model="reviewer-model", policy_version="mask-test",
            response_ids=("response-1",), review_relation="separate_model",
        ),
        reason="Revisión automática provisional.",
        reviewed_at="2026-11-14T12:00:00+00:00",
        operations=(), components=(component,), occurrences=(),
        scenario_occurrences=scenario_occurrences,
        machine_checks=checks, machine_field_reviews=field_reviews,
        auto_review_status="incomplete", status="reviewed_incomplete",
    )


def test_machine_derivation_masks_rejected_and_unreviewed_fields_without_mutating_raw() -> None:
    review = _machine_review(length_status="rejected", quantity_status="rejected")

    package = derive_general_package(review)

    raw = review.components[0]
    row = package.bom_rows[0]
    assert raw.length.value_mm == 720
    assert raw.quantity.value == 2
    assert row.length.value_mm is None
    assert row.length.state == "unknown"
    assert row.length.dependency_refs == raw.length.dependency_refs
    assert row.quantity.value is None
    assert row.quantity.state == "unknown"
    assert row.quantity.dependency_refs == raw.quantity.dependency_refs
    assert row.width == raw.width
    assert row.scenario_occurrence_ids == ()
    assert row.occurrence_status == "unknown"
    statuses = {item.field: item for item in row.machine_field_reviews}
    assert statuses["length"].status == "rejected"
    assert statuses["length"].check_summaries == ("Contraste visual del largo.",)
    assert statuses["thickness"].status == "unreviewed"
    assert statuses["length"].source_refs == ("document:page-1",)

    csv_artifact = next(item for item in package.artifacts if item.kind == "bom_csv")
    csv_row = next(csv.DictReader(io.StringIO(csv_artifact.content.decode("utf-8-sig"))))
    assert csv_row["length_mm"] == ""
    assert csv_row["quantity"] == ""
    assert csv_row["length_review_status"] == "rejected"
    assert csv_row["quantity_review_status"] == "rejected"
    json_artifact = next(item for item in package.artifacts if item.kind == "bom_json")
    json_row = json.loads(json_artifact.content)[0]
    assert json_row["length"]["value_mm"] is None
    assert json_row["quantity"]["value"] is None
    assert package.scene.items[0].length.value_mm is None
    assert package.scene.items[0].status == "unavailable"
    svg = next(item for item in package.artifacts if item.kind == "drawing_svg")
    assert b'class="component-outline"' not in svg.content
    dxf = next(item for item in package.artifacts if item.kind == "drawing_dxf")
    document = ezdxf.read(io.StringIO(dxf.content.decode("utf-8")))
    assert len(document.modelspace().query("LWPOLYLINE")) == 0


def test_machine_derivation_keeps_only_explicitly_accepted_values_and_occurrences() -> None:
    review = _machine_review(length_status="accepted", quantity_status="accepted")

    package = derive_general_package(review)
    row = package.bom_rows[0]

    assert row.length == review.components[0].length
    assert row.width == review.components[0].width
    assert row.quantity == review.components[0].quantity
    assert row.scenario_occurrence_ids == (
        "scenario:machine-side:1", "scenario:machine-side:2",
    )
    assert row.occurrence_status == "provisional"
    svg = next(item for item in package.artifacts if item.kind == "drawing_svg")
    assert b'class="component-outline"' in svg.content


@pytest.mark.parametrize("status", ("rejected", "conflict", "abstained"))
def test_machine_derivation_masks_every_nonaccepted_decision(status: str) -> None:
    review = _machine_review(length_status=status, quantity_status="accepted")

    row = derive_general_package(review).bom_rows[0]

    assert row.length.value_mm is None
    assert row.length.state == "unknown"
    decision = next(item for item in row.machine_field_reviews if item.field == "length")
    assert decision.status == status


def test_machine_derivation_masks_numeric_field_with_no_field_review() -> None:
    review = _machine_review(length_status="accepted", quantity_status="accepted")
    review = review.model_copy(
        update={
            "machine_field_reviews": tuple(
                item
                for item in review.machine_field_reviews
                if item.target_ref != "component:machine-side.width"
            )
        }
    )

    row = derive_general_package(review).bom_rows[0]

    assert review.components[0].width.value_mm == 400
    assert row.width.value_mm is None
    assert row.width.state == "unknown"
    decision = next(item for item in row.machine_field_reviews if item.field == "width")
    assert decision.status == "unreviewed"


def test_machine_derived_json_serializes_accepted_rejected_abstained_and_unreviewed() -> None:
    source = _machine_review(length_status="rejected", quantity_status="rejected")
    data = source.model_dump(mode="python")
    data["machine_checks"] = (*source.machine_checks, GeneralAutoReviewCheck(
        id="thickness-abstention", kind="visual_consistency", outcome="unknown",
        method="model_visual", target_refs=("component:machine-side.thickness",),
        source_refs=("document:page-1",), summary="La imagen no resuelve el espesor.",
    ))
    data["machine_field_reviews"] = (*source.machine_field_reviews, GeneralMachineFieldReview(
        target_ref="component:machine-side.thickness", status="abstained",
        check_ids=("thickness-abstention",),
    ))
    review = GeneralFurnitureReview.model_validate(data)

    package = derive_general_package(review)
    artifact = next(item for item in package.artifacts if item.kind == "bom_json")
    row = json.loads(artifact.content)[0]
    statuses = {
        item["field"]: item["status"] for item in row["machine_field_reviews"]
    }

    assert statuses["width"] == "accepted"
    assert statuses["length"] == "rejected"
    assert statuses["thickness"] == "abstained"
    assert statuses["material"] == "unreviewed"
    assert row["length"]["value_mm"] is None
    assert row["thickness"]["value_mm"] is None
    assert row["material"]["value"] is None


def test_manual_derivation_remains_unmasked_and_has_no_machine_field_metadata() -> None:
    review = _review()

    package = derive_general_package(review)

    assert package.bom_rows[0].length == review.components[0].length
    assert package.bom_rows[0].quantity == review.components[0].quantity
    assert package.bom_rows[0].machine_field_reviews == ()
