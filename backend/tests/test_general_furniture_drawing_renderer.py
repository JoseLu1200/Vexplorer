from io import StringIO

import ezdxf

from backend.app.contratos.modelos import (
    GeneralBomRow,
    GeneralQuantity,
    GeneralTextValue,
    GeneralValue,
)
from backend.app.general_furniture.drawing_renderer import (
    render_general_component_drawings,
)


def _row() -> GeneralBomRow:
    return GeneralBomRow(
        component_id="side-panel",
        label="Lateral",
        kind="panel",
        role="side",
        occurrence_ids=("side-left", "side-right"),
        quantity=GeneralQuantity(value=2, state="confirmed", dependency_refs=("human:qty",)),
        length=GeneralValue(value_mm=720, state="observed", dimension_ids=("dim-h",), evidence_ids=("evidence-height",)),
        width=GeneralValue(value_mm=None, state="unknown"),
        thickness=GeneralValue(value_mm=None, state="unknown"),
        material=GeneralTextValue(value=None, state="unknown"),
        finish=GeneralTextValue(value=None, state="unknown"),
        source_view_ids=("view-front",),
        source_observation_ids=("obs-front",),
        source_contour_ids=("contour-left",),
        source_evidence_ids=("evidence-height",),
        source_dimension_ids=("dim-h",),
        source_document_refs=("document:page-1",),
    )


def test_renderer_emits_annotated_svg_and_mm_dxf_per_occurrence() -> None:
    artifacts = render_general_component_drawings((_row(),), review_revision=3)

    assert [item.kind for item in artifacts] == ["drawing_svg", "drawing_dxf"]
    assert all(item.status == "incomplete" for item in artifacts)
    assert all(item.review_revision == 3 for item in artifacts)
    svg = artifacts[0].content.decode("utf-8")
    assert "side-left" in svg and "side-right" in svg
    assert "L=720 mm [observed]" in svg
    assert "W=unknown [unknown]" in svg
    assert "T=unknown [unknown]" in svg
    assert "Q=2 [confirmed]" in svg
    assert "source: view-front; contour-left; dim-h; document:page-1" in svg
    assert "schematic; not manufacturing-ready" in svg

    document = ezdxf.read(StringIO(artifacts[1].content.decode("utf-8")))
    assert document.header["$INSUNITS"] == 4
    texts = "\n".join(entity.dxf.text for entity in document.modelspace().query("TEXT"))
    assert "side-left" in texts and "side-right" in texts
    assert "L=720 mm [observed]" in texts
    assert "W=unknown [unknown]" in texts
    assert "T=unknown [unknown]" in texts
    assert "Q=2 [confirmed]" in texts
    assert len(document.modelspace().query("LWPOLYLINE")) == 2


def test_renderer_does_not_invent_occurrences_or_manufacturing_details() -> None:
    row = _row().model_copy(
        update={
            "occurrence_ids": (),
            "quantity": GeneralQuantity(value=None, state="unknown"),
        }
    )

    artifacts = render_general_component_drawings((row,), review_revision=1)

    combined = b"\n".join(item.content for item in artifacts).lower()
    assert b"occurrence-1" not in combined
    assert b"hole" not in combined
    assert b"joint" not in combined
    assert b"machining" not in combined
    assert b"q=unknown [unknown]" in combined
