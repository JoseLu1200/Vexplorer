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
