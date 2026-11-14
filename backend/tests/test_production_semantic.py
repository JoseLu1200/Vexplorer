from __future__ import annotations

from backend.app.contratos.modelos import TableCostScope
from backend.app.semantic.descriptor import build_descriptor, semantic_text
from backend.tests.test_backend_semantic import _completed_table_result, _reviewed_result


def test_missing_piece_material_prevents_false_uniform_material(tmp_path) -> None:
    result = _reviewed_result(tmp_path)
    pieces = list(result.pieces)
    pieces[0] = pieces[0].model_copy(update={"material": None})

    descriptor = build_descriptor(result.model_copy(update={"pieces": tuple(pieces)}))

    assert descriptor.material is None
    assert "material" in descriptor.unknown_fields


def test_table_descriptor_keeps_component_material_overrides_without_price_claim() -> None:
    result = _completed_table_result().model_copy(
        update={"table_cost_scope": TableCostScope(
            material_tariff_id="board-real",
            component_material_tariff_ids={"supports": "solid-real"},
        )}
    )

    descriptor = build_descriptor(result)
    by_role = {item.role: item.material_tariff_id for item in descriptor.components}
    text = semantic_text(descriptor)

    assert descriptor.material_tariff_id is None
    assert by_role == {"tabletop": "board-real", "side_support": "solid-real"}
    assert "price" not in text and "precio" not in text
