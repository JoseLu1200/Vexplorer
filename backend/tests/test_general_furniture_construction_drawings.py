from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import ezdxf

from backend.app.general_furniture.construction_drawings import (
    render_construction_sheet_dxf,
    render_construction_sheet_svg,
)


def _point(x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(x=x, y=y)


def _primitive(
    primitive_id: str,
    kind: str,
    points: tuple[tuple[float, float], ...],
    *,
    state: str,
    text: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=primitive_id,
        kind=kind,
        points_mm=tuple(_point(x, y) for x, y in points),
        text=text,
        state=state,
        source_refs=("parameter:panel_length",),
    )


def _piece_sheet() -> SimpleNamespace:
    return SimpleNamespace(
        sheet_id="piece:side-panel",
        kind="piece",
        piece_id="side-panel",
        title="Costado lateral",
        warnings=(SimpleNamespace(
            code="estimated_board",
            message="Confirmar espesor dentro del rango 16–19 mm.",
            severity="warning",
            consequence="provisional_only",
        ),),
        primitives=(
            _primitive(
                "face-outline",
                "polyline",
                ((0, 0), (720, 0), (720, 560), (0, 560), (0, 0)),
                state="estimated",
            ),
            _primitive(
                "length-dimension",
                "dimension",
                ((0, 0), (720, 0), (0, -45)),
                state="estimated",
                text="≈ 720 mm [710–730]",
            ),
            _primitive(
                "width-dimension",
                "dimension",
                ((0, 0), (0, 560), (-45, 0)),
                state="deduced",
                text="560 mm",
            ),
            _primitive(
                "thickness-view",
                "polyline",
                ((820, 0), (838, 0), (838, 560), (820, 560), (820, 0)),
                state="observed",
            ),
            _primitive(
                "thickness-dimension",
                "dimension",
                ((820, 0), (838, 0), (820, -45)),
                state="observed",
                text="18 mm",
            ),
            _primitive(
                "quantity",
                "text",
                ((0, 625),),
                state="estimated",
                text="Cantidad propuesta: ≈ 2 uds.",
            ),
            _primitive(
                "detail",
                "detail_callout",
                ((720, 280), (850, 280), (850, 650), (920, 650)),
                state="estimated",
                text="D01 · Ranura propuesta 6 × 8 mm",
            ),
        ),
    )


def test_piece_svg_has_exact_nominal_geometry_dimensions_and_authority_legend() -> None:
    root = ET.fromstring(render_construction_sheet_svg(_piece_sheet()))

    assert root.attrib["data-coordinate-unit"] == "mm"
    assert root.attrib["data-sheet-kind"] == "piece"
    assert root.attrib["data-piece-id"] == "side-panel"
    text = " ".join(value.strip() for value in root.itertext() if value.strip())
    assert "≈ 720 mm [710–730]" in text
    assert "560 mm" in text
    assert "18 mm" in text
    assert "Cantidad propuesta: ≈ 2 uds." in text
    assert "D01 · Ranura propuesta 6 × 8 mm" in text
    assert "OBSERVADO" in text
    assert "DEDUCIDO" in text
    assert "ESTIMADO" in text
    assert "PROPUESTA CONSTRUCTIVA · COTAS ESTIMADAS SEÑALADAS" in text
    assert "RESTRICCIÓN: Confirmar espesor dentro del rango 16–19 mm." in text
    assert "NO VALIDADO PARA FABRICACIÓN" not in text

    estimated = root.findall(".//*[@data-state='estimated']")
    assert estimated
    assert any("stroke-dasharray" in item.attrib for group in estimated for item in group.iter())
    dimension_groups = root.findall(".//*[@data-kind='dimension']")
    assert dimension_groups
    assert all(
        len(group.findall(".//*[@data-role='dimension-terminator']")) == 2
        for group in dimension_groups
    )
    callout = root.find(".//*[@data-kind='detail_callout']")
    assert callout is not None
    assert len(callout.findall(".//*[@data-role='detail-leader']")) >= 2
    callout_text = callout.find(".//{http://www.w3.org/2000/svg}text")
    assert callout_text.attrib["x"] == "920"
    view_x, _, view_width, _ = (float(value) for value in root.attrib["viewBox"].split())
    assert float(callout_text.attrib["x"]) + len(callout_text.text) * 6 < view_x + view_width


def test_piece_dxf_preserves_exact_mm_extents_and_separate_authority_layers() -> None:
    document = ezdxf.read(StringIO(render_construction_sheet_dxf(_piece_sheet()).decode("utf-8")))

    assert document.header["$INSUNITS"] == 4
    face = document.modelspace().query('LWPOLYLINE[layer=="VX_ESTIMATED"]')[0]
    points = [(point[0], point[1]) for point in face.get_points()]
    assert max(x for x, _ in points) - min(x for x, _ in points) == 720
    assert max(y for _, y in points) - min(y for _, y in points) == 560
    layers = {entity.dxf.layer for entity in document.modelspace()}
    assert {"VX_OBSERVED", "VX_DEDUCED", "VX_ESTIMATED"} <= layers
    assert document.layers.get("VX_OBSERVED").dxf.color == 7
    assert document.layers.get("VX_DEDUCED").dxf.color == 5
    assert document.layers.get("VX_ESTIMATED").dxf.color == 30
    assert document.layers.get("VX_OBSERVED").dxf.linetype == "Continuous"
    assert document.layers.get("VX_DEDUCED").dxf.linetype == "CENTER"
    assert document.layers.get("VX_ESTIMATED").dxf.linetype == "DASHED"
    visible_text = " ".join(
        entity.dxf.text
        for entity in document.modelspace().query("TEXT")
        if entity.dxf.layer != "VX_PROVENANCE"
    )
    assert "~ 720 mm [710-730]" in visible_text
    assert "Cantidad propuesta: ~ 2 uds." in visible_text
    assert "Ranura propuesta 6 x 8 mm" in visible_text
    assert "Costado lateral" in visible_text
    assert "PROPUESTA CONSTRUCTIVA - COTAS ESTIMADAS SENALADAS" in visible_text
    assert "OBSERVADO" in visible_text
    assert "DEDUCIDO" in visible_text
    assert "ESTIMADO" in visible_text
    assert "RESTRICCION: Confirmar espesor dentro del rango 16-19 mm." in visible_text


def test_visible_dimension_labels_use_hundredth_mm_without_changing_geometry() -> None:
    raw_thickness = 4.999943339249739
    sheet = SimpleNamespace(
        sheet_id="piece:precision",
        kind="piece",
        piece_id="precision",
        title="Pieza de precisión",
        warnings=(),
        primitives=(
            _primitive(
                "raw-precision",
                "dimension",
                ((0, 0), (raw_thickness, 0), (0, -45)),
                state="deduced",
                text="4.999943339249739 mm",
            ),
            _primitive(
                "negative-zero",
                "dimension",
                ((0, 20), (10, 20), (0, -25)),
                state="observed",
                text="-0.0004 mm",
            ),
            _primitive(
                "estimated-range",
                "dimension",
                ((0, 40), (18.004, 40), (0, -5)),
                state="estimated",
                text="≈ 18.004 mm [17.4999–18.5001]",
            ),
            _primitive(
                "unknown",
                "dimension",
                ((0, 60), (10, 60), (0, 15)),
                state="unknown",
                text="?",
            ),
        ),
    )

    svg_root = ET.fromstring(render_construction_sheet_svg(sheet))
    svg_text = [value.strip() for value in svg_root.itertext() if value.strip()]
    assert "5 mm" in svg_text
    assert "0 mm" in svg_text
    assert "≈ 18 mm [17.5–18.5]" in svg_text
    assert "?" in svg_text
    assert "4.999943339249739 mm" not in svg_text
    raw_group = svg_root.find(".//*[@data-primitive-id='raw-precision']")
    assert raw_group is not None
    assert any(line.attrib.get("x2") == "4.999943" for line in raw_group)

    document = ezdxf.read(StringIO(render_construction_sheet_dxf(sheet).decode("utf-8")))
    visible_text = {
        entity.dxf.text
        for entity in document.modelspace().query("TEXT")
        if entity.dxf.layer != "VX_PROVENANCE"
    }
    assert {"5 mm", "0 mm", "~ 18 mm [17.5-18.5]", "?"} <= visible_text
    raw_lines = [
        entity
        for entity in document.modelspace().query('LINE[layer=="VX_DEDUCED"]')
        if entity.has_xdata("VEXPLORER")
        and entity.get_xdata("VEXPLORER")[0].value == "raw-precision"
    ]
    assert any(entity.dxf.end.x == raw_thickness for entity in raw_lines)
    assert sheet.primitives[0].text == "4.999943339249739 mm"


def _assert_svg_text_inside_viewbox(root: ET.Element) -> None:
    view_x, view_y, view_width, view_height = (
        float(value) for value in root.attrib["viewBox"].split()
    )
    view_right = view_x + view_width
    view_bottom = view_y + view_height
    for item in root.findall(".//{http://www.w3.org/2000/svg}text"):
        if not item.text:
            continue
        x = float(item.attrib["x"])
        y = float(item.attrib["y"])
        font_size = float(item.attrib.get("font-size", "12"))
        text_width = len(item.text) * font_size * 0.6
        left = x - text_width / 2 if item.attrib.get("text-anchor") == "middle" else x
        right = x + text_width / 2 if item.attrib.get("text-anchor") == "middle" else x + text_width
        assert left >= view_x, item.text
        assert right <= view_right, item.text
        assert y - font_size >= view_y, item.text
        assert y + font_size * 0.3 <= view_bottom, item.text


def test_svg_bounds_include_long_estimated_vertical_dimension_label_to_the_left() -> None:
    sheet = SimpleNamespace(
        sheet_id="piece:box-sides",
        kind="piece",
        piece_id="box-sides",
        title="Laterales de caja",
        warnings=(),
        primitives=(
            _primitive(
                "outline", "polyline",
                ((0, 0), (400, 0), (400, 180), (0, 180), (0, 0)),
                state="estimated",
            ),
            _primitive(
                "vertical-estimate", "dimension",
                ((0, 0), (0, 180), (-45, 0)),
                state="estimated", text="≈ 180 mm [160–200]",
            ),
        ),
    )

    root = ET.fromstring(render_construction_sheet_svg(sheet))

    label = next(
        item for item in root.findall(".//{http://www.w3.org/2000/svg}text")
        if item.text == "≈ 180 mm [160–200]"
    )
    assert label.attrib["text-anchor"] == "middle"
    _assert_svg_text_inside_viewbox(root)


def test_svg_bounds_include_all_labels_when_sheet_has_no_geometry() -> None:
    sheet = SimpleNamespace(
        sheet_id="piece:guides",
        kind="piece",
        piece_id="guides",
        title="Guías interiores propuestas sin geometría local disponible",
        warnings=(SimpleNamespace(
            code="piece_geometry_incomplete",
            message="La pieza no tiene forma explícita y tres dimensiones aceptadas.",
            severity="warning",
            consequence="provisional_only",
        ),),
        primitives=(
            _primitive(
                "quantity", "text", ((0, 0),), state="estimated",
                text="Cantidad propuesta: ≈ 6 uds.",
            ),
        ),
    )

    root = ET.fromstring(render_construction_sheet_svg(sheet))

    text = " ".join(value.strip() for value in root.itertext() if value.strip())
    assert sheet.title in text
    assert "PROPUESTA CONSTRUCTIVA · COTAS ESTIMADAS SEÑALADAS" in text
    assert "RESTRICCIÓN: La pieza no tiene forma explícita" in text
    _assert_svg_text_inside_viewbox(root)

