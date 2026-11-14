from io import StringIO
import json
from xml.etree import ElementTree as ET

import ezdxf

from backend.app.contratos.modelos import GeneralBomRow, GeneralQuantity, GeneralTextValue, GeneralValue
from backend.app.general_furniture.drawing_renderer import render_general_component_drawings


def _row() -> GeneralBomRow:
    return GeneralBomRow(
        component_id="side-panel", label="Lateral", kind="panel", role="side",
        occurrence_ids=("side-left", "side-right"),
        quantity=GeneralQuantity(value=2, state="confirmed", dependency_refs=("human:qty",)),
        length=GeneralValue(value_mm=720, state="observed", dimension_ids=("dim-h",), evidence_ids=("evidence-height",)),
        width=GeneralValue(value_mm=None, state="unknown"),
        thickness=GeneralValue(value_mm=None, state="unknown"),
        material=GeneralTextValue(value=None, state="unknown"), finish=GeneralTextValue(value=None, state="unknown"),
        source_view_ids=("view-front",), source_observation_ids=("obs-front",),
        source_contour_ids=("contour-left",), source_evidence_ids=("evidence-height",),
        source_dimension_ids=("dim-h",), source_document_refs=("document:page-1",),
    )


def _provisional_long_row() -> GeneralBomRow:
    long_id = "provisional:scenario:component-with-a-very-long-name:occurrence-0001"
    long_evidence = "evidence:" + "source-segment-" * 9 + "final"
    return GeneralBomRow(
        component_id="top-panel-candidate", label="Panel superior candidato con denominación completa",
        kind="panel", role="top", occurrence_ids=(), scenario_occurrence_ids=(long_id,),
        occurrence_status="provisional",
        quantity=GeneralQuantity(value=1, state="hypothesis", dependency_refs=("premise:single-top",)),
        length=GeneralValue(value_mm=1200, state="hypothesis", dependency_refs=("binding:top-length",)),
        width=GeneralValue(value_mm=700, state="hypothesis", dependency_refs=("binding:top-width",)),
        thickness=GeneralValue(value_mm=None, state="unknown"),
        material=GeneralTextValue(value=None, state="unknown"), finish=GeneralTextValue(value=None, state="unknown"),
        source_view_ids=("view-front", "view-side", "view-top"), source_observation_ids=(),
        source_contour_ids=("contour-front", "contour-side", "contour-top"),
        source_evidence_ids=(long_evidence,), source_dimension_ids=(),
        source_document_refs=("document:qa-source-page-0001",),
    )


def _texts(root: ET.Element) -> str:
    return "\n".join("".join(item.itertext()) for item in root.iter() if item.tag.rsplit("}", 1)[-1] in {"text", "tspan"})


def test_renderer_emits_readable_spanish_svg_with_complete_provenance() -> None:
    rows = (_row(), _provisional_long_row())
    artifacts = render_general_component_drawings(rows, review_revision=3)

    assert [item.kind for item in artifacts] == ["drawing_svg", "drawing_dxf"]
    assert all(item.status == "incomplete" for item in artifacts)
    root = ET.fromstring(artifacts[0].content)
    visible = _texts(root)
    assert "ESQUEMA PROVISIONAL" in visible and "NO APTO PARA FABRICACIÓN" in visible
    assert "Ocurrencia física: side-left [confirmada]" in visible
    assert "Escenario provisional:" in visible
    assert "Largo: 720 mm [observado]" in visible
    assert "Ancho: desconocido [desconocido]" in visible
    assert "Cantidad: 1 [hipótesis]" in visible
    assert "not manufacturing-ready" not in visible and "unknown" not in visible
    assert "view-front" not in visible and "evidence-" not in visible
    assert "detalle íntegro en metadatos" in visible

    metadata = next(item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "metadata")
    payload = json.loads(metadata.text or "")
    assert payload[1]["scenario_occurrence_ids"] == list(rows[1].scenario_occurrence_ids)
    assert payload[1]["source_evidence_ids"] == list(rows[1].source_evidence_ids)
    descriptions = "\n".join(item.text or "" for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "desc")
    assert rows[1].scenario_occurrence_ids[0] in descriptions
    assert rows[1].source_evidence_ids[0] in descriptions

    viewbox = [float(value) for value in root.attrib["viewBox"].split()]
    y_values = [float(item.attrib["y"]) for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "text" and "y" in item.attrib]
    assert max(y_values) < viewbox[3] - 20
    assert root.attrib["height"] == f"{viewbox[3]:g}"
    assert root.attrib["data-authority"] == "esquema_sin_colocacion_no_fabricacion"


def test_unknown_geometry_has_no_fallback_rectangle_or_false_scale() -> None:
    artifact = render_general_component_drawings((_row(),), review_revision=1)[0]
    root = ET.fromstring(artifact.content)
    component_rectangles = [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "rect" and item.attrib.get("class") == "component-outline"]
    assert component_rectangles == []
    assert "Geometría no dibujada: falta largo o ancho" in _texts(root)


def test_three_provisional_occurrences_all_fit_inside_real_viewbox_height() -> None:
    row = _provisional_long_row().model_copy(
        update={
            "scenario_occurrence_ids": (
                "provisional:top:1",
                "provisional:top:2",
                "provisional:top:3",
            ),
            "quantity": GeneralQuantity(
                value=3,
                state="hypothesis",
                dependency_refs=("premise:three-top-candidates",),
            ),
        }
    )
    artifact = render_general_component_drawings((row,), review_revision=4)[0]
    root = ET.fromstring(artifact.content)
    visible = _texts(root)
    assert all(identifier in visible for identifier in row.scenario_occurrence_ids)
    assert visible.count("Escenario provisional:") == 3
    height = float(root.attrib["viewBox"].split()[3])
    y_values = [
        float(item.attrib["y"])
        for item in root.iter()
        if item.tag.rsplit("}", 1)[-1] == "text" and "y" in item.attrib
    ]
    assert max(y_values) < height - 20


def test_dxf_keeps_spanish_labels_full_refs_and_mm_without_fake_geometry() -> None:
    rows = (_row(), _provisional_long_row())
    artifact = render_general_component_drawings(rows, review_revision=3)[1]
    document = ezdxf.read(StringIO(artifact.content.decode("utf-8")))
    assert document.header["$INSUNITS"] == 4
    texts = "\n".join([item.dxf.text for item in document.modelspace().query("TEXT")] + [item.plain_text() for item in document.modelspace().query("MTEXT")])
    assert "ESQUEMA PROVISIONAL" in texts
    assert "Ocurrencia física: side-left [confirmada]" in texts
    assert "Escenario provisional:" in texts
    assert "Largo: 720 mm [observado]" in texts
    assert "Ancho: desconocido [desconocido]" in texts
    assert rows[1].scenario_occurrence_ids[0] in texts
    assert rows[1].source_evidence_ids[0] in texts
    assert "unknown" not in texts
    assert document.layers.get("PROVENANCE").is_off()
    provenance_entities = list(document.modelspace().query("MTEXT[layer=='PROVENANCE']"))
    assert provenance_entities
    assert all(item.dxf.layer == "PROVENANCE" for item in provenance_entities)
    outlines = list(document.modelspace().query("LWPOLYLINE"))
    assert len(outlines) == 1
    points = list(outlines[0].get_points("xy"))
    assert max(point[0] for point in points) - min(point[0] for point in points) == 1200
    assert max(point[1] for point in points) - min(point[1] for point in points) == 700


def test_renderer_does_not_invent_occurrences_or_manufacturing_details() -> None:
    row = _row().model_copy(update={"occurrence_ids": (), "quantity": GeneralQuantity(value=None, state="unknown")})
    artifacts = render_general_component_drawings((row,), review_revision=1)
    combined = b"\n".join(item.content for item in artifacts).lower()
    assert b"occurrence-1" not in combined
    assert b"hole" not in combined and b"joint" not in combined and b"machining" not in combined
    assert "cantidad: desconocida [desconocido]" in combined.decode("utf-8")
