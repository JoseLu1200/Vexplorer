from __future__ import annotations

from io import StringIO
from xml.etree import ElementTree as ET

import ezdxf
import pytest

from backend.app.contratos.modelos import (
    EvaluatedTableComponent,
    Point2D,
    TableDrawingPlan,
    TableDrawingPrimitive,
    TableFieldValue,
    TableOccurrence,
    TableOverallDimensions,
    TableSheetPlan,
)


PROGRAM_HASH = "a" * 64


def _component(quantity: int = 4) -> EvaluatedTableComponent:
    return EvaluatedTableComponent(
        id="legs",
        role="corner_support",
        length=TableFieldValue(value_mm=700, state="calculated", dependency_refs=("binding:leg-height",)),
        width=TableFieldValue(value_mm=60, state="confirmed", dependency_refs=("human:leg-width",)),
        thickness=TableFieldValue(value_mm=60, state="proposed", dependency_refs=("binding:leg-depth",)),
        quantity=quantity,
        quantity_rule_id="four_corner_supports",
        placement_rule_id="corner_supports_flush",
        accepted=True,
        premise_ids=("premise:corner-supports",),
        evidence_ids=("evidence:height",),
    )


def _plan(
    *sheets: TableSheetPlan,
    revision: int = 3,
    program_hash: str = PROGRAM_HASH,
    occurrences: int = 4,
) -> TableDrawingPlan:
    return TableDrawingPlan(
        drawing_id="drawing-table",
        result_revision=revision,
        program_hash=program_hash,
        registry_versions={"profile": "rectangular_table_v1@1", "placement": "corner_supports_flush@1"},
        overall_dimensions=TableOverallDimensions(width_mm=1200, depth_mm=700, height_mm=750),
        components=(_component(occurrences),),
        occurrences=tuple(
            TableOccurrence(id=f"leg-{index}", component_id="legs", occurrence_index=index)
            for index in range(1, occurrences + 1)
        ),
        placements=(),
        sheets=sheets,
    )


def _artifact(exports, sheet_id: str, format_: str) -> bytes:
    return next(
        item.content
        for item in exports.artifacts
        if item.sheet_id == sheet_id and item.format == format_
    )


def _read_dxf(content: bytes):
    return ezdxf.read(StringIO(content.decode("utf-8")))


def test_render_reopens_mm_dxf_and_preserves_numeric_dimensions_and_provenance():
    from backend.app.salida.technical_drawings import render_table_drawings

    sheet = TableSheetPlan(
        sheet_id="general",
        kind="general",
        title="Plano general",
        page=1,
        status="ready",
        primitives=(
            TableDrawingPrimitive(
                id="outline",
                kind="rect",
                points_mm=(Point2D(x=0, y=0), Point2D(x=1200, y=750)),
                state="proposed",
                dependency_refs=("program:table",),
            ),
            TableDrawingPrimitive(
                id="width",
                kind="dimension",
                points_mm=(Point2D(x=0, y=0), Point2D(x=1200, y=0), Point2D(x=0, y=-80)),
                value_mm=1200,
                state="observed",
                dependency_refs=("measure:width",),
            ),
        ),
    )

    exports = render_table_drawings(_plan(sheet))

    assert exports.result_revision == 3
    assert exports.program_hash == PROGRAM_HASH
    assert [(item.sheet_id, item.format, item.media_type) for item in exports.artifacts] == [
        ("general", "svg", "image/svg+xml"),
        ("general", "dxf", "application/dxf"),
    ]
    document = _read_dxf(_artifact(exports, "general", "dxf"))
    assert document.units == 4
    assert {layer.dxf.name for layer in document.layers} >= {"VX_OBSERVED", "VX_PROPOSED", "VX_METADATA"}
    dimensions = list(document.modelspace().query("DIMENSION"))
    assert len(dimensions) == 1
    assert dimensions[0].dxf.text == "1200 mm"
    assert tuple(dimensions[0].dxf.defpoint2)[:2] == (0.0, 0.0)
    assert tuple(dimensions[0].dxf.defpoint3)[:2] == (1200.0, 0.0)
    metadata = "\n".join(entity.plain_text() for entity in document.modelspace().query("MTEXT"))
    assert "Plano general" in metadata
    assert f"program_hash={PROGRAM_HASH}" in metadata
    assert "result_revision=3" in metadata


def test_unknown_dimension_is_question_mark_not_a_numeric_cad_dimension():
    from backend.app.salida.technical_drawings import render_table_drawings

    sheet = TableSheetPlan(
        sheet_id="unknown-detail",
        kind="component",
        title="Detalle incompleto",
        component_id="legs",
        page=1,
        status="incomplete",
        warnings=("thickness_unknown",),
        primitives=(
            TableDrawingPrimitive(
                id="unknown-thickness",
                kind="dimension",
                points_mm=(Point2D(x=0, y=0), Point2D(x=60, y=0), Point2D(x=0, y=-15)),
                text="Espesor ?",
                state="unknown",
                dependency_refs=("binding:leg-depth",),
            ),
        ),
    )

    exports = render_table_drawings(_plan(sheet))

    svg_root = ET.fromstring(_artifact(exports, "unknown-detail", "svg"))
    svg_text = " ".join(value for value in svg_root.itertext())
    assert "Espesor ?" in svg_text
    document = _read_dxf(_artifact(exports, "unknown-detail", "dxf"))
    dimensions = list(document.modelspace().query("DIMENSION"))
    assert len(dimensions) == 1
    assert dimensions[0].dxf.text == "??"
    assert "60 mm" not in "\n".join(entity.plain_text() for entity in document.modelspace().query("MTEXT"))


def test_component_has_quantity_and_three_dimensions_and_cut_sheet_uses_occurrences_not_views():
    from backend.app.salida.technical_drawings import render_table_drawings

    component = TableSheetPlan(
        sheet_id="component-legs",
        kind="component",
        title="Soporte de esquina",
        component_id="legs",
        page=1,
        status="ready",
        primitives=(
            TableDrawingPrimitive(
                id="part",
                kind="rect",
                points_mm=(Point2D(x=0, y=0), Point2D(x=700, y=60)),
                state="proposed",
            ),
            TableDrawingPrimitive(
                id="qty",
                kind="text",
                points_mm=(Point2D(x=0, y=100),),
                text="Cantidad: 4",
                state="calculated",
            ),
            TableDrawingPrimitive(
                id="length",
                kind="dimension",
                points_mm=(
                    Point2D(x=0, y=0),
                    Point2D(x=700, y=0),
                    Point2D(x=0, y=-40),
                ),
                value_mm=700,
                state="calculated",
            ),
            TableDrawingPrimitive(
                id="width",
                kind="dimension",
                points_mm=(
                    Point2D(x=0, y=0),
                    Point2D(x=0, y=60),
                    Point2D(x=-40, y=0),
                ),
                value_mm=60,
                state="confirmed",
            ),
            TableDrawingPrimitive(
                id="thickness",
                kind="dimension",
                points_mm=(
                    Point2D(x=0, y=60),
                    Point2D(x=60, y=60),
                    Point2D(x=0, y=90),
                ),
                value_mm=60,
                state="proposed",
            ),
        ),
    )
    cut_sheet = TableSheetPlan(
        sheet_id="cut-sheet",
        kind="cut_sheet",
        title="Hoja de despiece",
        page=2,
        status="ready",
        primitives=tuple(
            TableDrawingPrimitive(
                id=f"occurrence-{index}",
                kind="rect",
                points_mm=(Point2D(x=(index - 1) * 80, y=0), Point2D(x=(index - 1) * 80 + 60, y=700)),
                state="proposed",
                dependency_refs=(f"occurrence:leg-{index}",),
            )
            for index in range(1, 5)
        ),
    )

    exports = render_table_drawings(_plan(component, cut_sheet, occurrences=4))

    component_doc = _read_dxf(_artifact(exports, "component-legs", "dxf"))
    assert len(list(component_doc.modelspace().query("DIMENSION"))) == 3
    assert "Cantidad: 4" in "\n".join(entity.dxf.text for entity in component_doc.modelspace().query("TEXT"))
    cut_doc = _read_dxf(_artifact(exports, "cut-sheet", "dxf"))
    occurrence_rectangles = [
        entity
        for entity in cut_doc.modelspace().query("LWPOLYLINE")
        if entity.dxf.layer == "VX_PROPOSED" and entity.closed
    ]
    assert len(occurrence_rectangles) == 4
    assert len(occurrence_rectangles) != 3  # the source fixture has three orthographic views


def test_svg_escapes_untrusted_text_and_contains_no_active_elements():
    from backend.app.salida.technical_drawings import render_table_drawings

    hostile = '<script>alert("CAD")</script> & pieza'
    sheet = TableSheetPlan(
        sheet_id="safe-text",
        kind="general",
        title="Texto seguro",
        page=1,
        status="ready",
        primitives=(
            TableDrawingPrimitive(id="label", kind="text", points_mm=(Point2D(x=0, y=0),), text=hostile, state="observed"),
        ),
    )

    svg = _artifact(render_table_drawings(_plan(sheet)), "safe-text", "svg")

    root = ET.fromstring(svg)
    assert hostile in tuple(root.itertext())
    assert b"<script>" not in svg
    assert not {"script", "image", "foreignObject", "a"} & {
        element.tag.rsplit("}", 1)[-1] for element in root.iter()
    }
    assert not any(
        key.lower().startswith("on") or "href" in key.lower()
        for element in root.iter()
        for key in element.attrib
    )


def test_large_general_sheet_scales_fonts_and_keeps_warnings_inside_page():
    from backend.app.salida.technical_drawings import render_table_drawings

    sheet = TableSheetPlan(
        sheet_id="general-1200x700",
        kind="general",
        title="Mesa 1200 x 700 - planta y alzado",
        page=1,
        status="incomplete",
        warnings=("hipotesis de montaje", "espesor pendiente", "uniones no evaluadas", "no apto para fabricar"),
        primitives=(
            TableDrawingPrimitive(
                id="front",
                kind="rect",
                points_mm=(Point2D(x=0, y=0), Point2D(x=1200, y=750)),
                state="proposed",
            ),
            TableDrawingPrimitive(
                id="top",
                kind="rect",
                points_mm=(Point2D(x=1300, y=0), Point2D(x=2500, y=700)),
                state="proposed",
            ),
            TableDrawingPrimitive(
                id="width",
                kind="dimension",
                points_mm=(Point2D(x=0, y=0), Point2D(x=1200, y=0), Point2D(x=0, y=-50)),
                value_mm=1200,
                state="observed",
            ),
        ),
    )

    root = ET.fromstring(_artifact(render_table_drawings(_plan(sheet)), sheet.sheet_id, "svg"))

    _, _, view_width, view_height = (float(value) for value in root.attrib["viewBox"].split())
    intrinsic_width = float(root.attrib["width"])
    intrinsic_height = float(root.attrib["height"])
    text_nodes = [element for element in root.iter() if element.tag.endswith("text")]
    title = next(element for element in text_nodes if element.text == sheet.title)
    legend = [
        element
        for element in text_nodes
        if element.text in {"observado", "calculado", "hipotesis", "confirmado", "desconocido", "conflicto"}
    ]
    warnings = [element for element in text_nodes if (element.text or "").startswith("AVISO:")]
    assert float(title.attrib["font-size"]) / view_width * 800 >= 10
    assert min(float(element.attrib["font-size"]) for element in legend) / view_width * 800 >= 7
    assert intrinsic_width == 1600
    assert intrinsic_height / intrinsic_width == pytest.approx(view_height / view_width, abs=0.001)
    assert not any("vector-effect" in element.attrib for element in root.iter())
    stroke_widths = {
        float(element.attrib["stroke-width"])
        for element in root.iter()
        if "stroke-width" in element.attrib
    }
    assert len(stroke_widths) == 1
    stroke_width = next(iter(stroke_widths))
    assert stroke_width == pytest.approx(1.5 * (2500 / 900))
    assert 1.5 <= stroke_width / view_width * intrinsic_width <= 3.5
    assert len(warnings) == 4
    assert max(float(element.attrib["y"]) for element in warnings) < view_height


def test_render_is_byte_deterministic_and_revisions_do_not_cross_contaminate():
    from backend.app.salida.technical_drawings import render_table_drawings

    sheet = TableSheetPlan(
        sheet_id="deterministic",
        kind="general",
        title="Determinista",
        page=1,
        status="ready",
        primitives=(
            TableDrawingPrimitive(id="line", kind="line", points_mm=(Point2D(x=0, y=0), Point2D(x=100, y=50)), state="calculated"),
        ),
    )
    first_plan = _plan(sheet, revision=2, program_hash="b" * 64)
    second_plan = _plan(sheet, revision=7, program_hash="c" * 64)

    first = render_table_drawings(first_plan)
    repeated = render_table_drawings(first_plan)
    second = render_table_drawings(second_plan)

    assert [(item.filename, item.content) for item in first.artifacts] == [
        (item.filename, item.content) for item in repeated.artifacts
    ]
    first_svg = _artifact(first, "deterministic", "svg")
    second_svg = _artifact(second, "deterministic", "svg")
    assert b'data-result-revision="2"' in first_svg
    assert ("b" * 64).encode() in first_svg
    assert b'data-result-revision="7"' in second_svg
    assert ("c" * 64).encode() in second_svg
    assert ("b" * 64).encode() not in second_svg
    first_dxf = _artifact(first, "deterministic", "dxf")
    second_dxf = _artifact(second, "deterministic", "dxf")
    assert first_dxf != second_dxf
    assert ("b" * 64).encode() in first_dxf
    assert ("c" * 64).encode() in second_dxf
    assert ("b" * 64).encode() not in second_dxf
