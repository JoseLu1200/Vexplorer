from backend.app.contratos.modelos import TableConfirmedValue, TableMeasure, TableOperandRef
from backend.app.servicios.table_explanations import explain_table_result
from backend.tests.test_backend_semantic import _completed_table_result


def test_table_explanations_expose_sources_formulas_premises_and_states():
    bundle = explain_table_result(_completed_table_result())

    assert bundle.result_revision == 2
    assert {item.role for item in bundle.pieces} == {"tabletop", "side_support"}
    for piece in bundle.pieces:
        assert piece.formulas
        assert piece.premises
        assert piece.measurements["quantity"] is not None
        assert piece.field_states["length_mm"] in ("calculated", "confirmed")
        assert all(formula.expression.startswith(formula.field + "=binding:") for formula in piece.formulas)
        assert all("run-" not in formula.expression for formula in piece.formulas)


def test_table_explanations_keep_rule_quantity_proposed_before_review():
    result = _completed_table_result()
    evaluated = result.evaluated_table_program
    assert evaluated is not None
    hypothesis = evaluated.model_copy(update={
        "state": "hypothesis",
        "components": tuple(item.model_copy(update={"accepted": False}) for item in evaluated.components),
    })
    bundle = explain_table_result(result.model_copy(update={
        "result_revision": 1,
        "state": "needs_review",
        "evaluated_table_program": hypothesis,
    }))
    assert all(item.field_states["quantity"] == "hypothesis" for item in bundle.pieces)
    assert all("quantity" in item.unknown_fields for item in bundle.pieces)


def test_table_explanations_use_human_overlay_in_formula_operands():
    result = _completed_table_result()
    analysis = result.table_analysis
    evaluated = result.evaluated_table_program
    assert analysis is not None and evaluated is not None
    slot = TableMeasure(
        id="human-slot",
        semantic="tabletop_thickness",
        axis="section",
        state="unknown",
        slot_origin="profile_required_slot",
        geometry_relation="profile_required_slot",
    )
    top_length = evaluated.bindings[0].model_copy(update={
        "operand_refs": (TableOperandRef(ref_type="measure", ref_id=slot.id),),
    })
    reviewed = result.model_copy(update={
        "table_analysis": analysis.model_copy(update={
            "measures": (*analysis.measures, slot),
            "admitted_measurement_ids": (*analysis.admitted_measurement_ids, slot.id),
        }),
        "evaluated_table_program": evaluated.model_copy(update={
            "bindings": (top_length, *evaluated.bindings[1:]),
        }),
        "table_confirmed_values": (
            TableConfirmedValue(target_id=slot.id, value_mm=30, reason="Medición humana local"),
        ),
    })
    bundle = explain_table_result(reviewed)
    top = next(item for item in bundle.pieces if item.role == "tabletop")
    length = next(item for item in top.formulas if item.field == "length_mm")
    assert length.operands_mm[slot.id] == 30
