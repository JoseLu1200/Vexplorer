from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import ezdxf

from backend.app.contratos.modelos import Result, ReviewRequest
from backend.app.geometria import extract_drawing
from backend.app.geometria.extraction import derive_rectangular_hypotheses
from backend.app.semantic.descriptor import build_descriptor, descriptor_fingerprint, semantic_text
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.servicios.reconstruction import reconstruct_scene
from backend.app.servicios.repository import DemoRepository


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime" / "audit-geometria"
OUT.mkdir(parents=True, exist_ok=True)


def save_nonplanar_lines() -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    points = ((0, 0, 0), (600, 0, 0), (600, 300, 10), (0, 300, 0))
    for start, end in zip(points, points[1:] + points[:1], strict=True):
        msp.add_line(start, end)
    msp.add_text("FRONT").set_placement((0, -20))
    path = OUT / "nonplanar-lines.dxf"
    doc.saveas(path)
    return path


def save_ocs_polyline() -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    poly = msp.add_lwpolyline(((0, 0), (600, 0), (600, 300), (0, 300)), close=True)
    poly.dxf.extrusion = (0, 1, 0)
    msp.add_text("FRONT").set_placement((0, -20))
    path = OUT / "ocs-polyline.dxf"
    doc.saveas(path)
    return path


def save_ocs_three_views() -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    for offset, size, label in (
        ((0, 0), (600, 300), "FRONT"),
        ((1000, 0), (600, 200), "TOP"),
        ((2000, 0), (200, 300), "RIGHT"),
    ):
        x, y = offset
        width, height = size
        poly = msp.add_lwpolyline(((x, y), (x + width, y), (x + width, y + height), (x, y + height)), close=True)
        poly.dxf.extrusion = (0, 1, 0)
        msp.add_text(label).set_placement((x, -20))
    path = OUT / "ocs-three-views.dxf"
    doc.saveas(path)
    return path


def save_dimlfac() -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    dim = doc.modelspace().add_linear_dim(base=(0, 50), p1=(0, 0), p2=(600, 0), override={"dimlfac": 2})
    dim.render()
    path = OUT / "dimlfac.dxf"
    doc.saveas(path)
    return path


def reviewed_result() -> Result:
    fixture = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    repository = DemoRepository(OUT / "descriptor.sqlite3")
    from uuid import uuid4
    run_id = "audit-descriptor-" + uuid4().hex
    repository.create_run(run_id, "geometry_only", extraction, derive_decomposition_scenarios(extraction))
    from backend.app.contratos.modelos import ReviewRequest

    return repository.review(
        run_id,
        ReviewRequest(
            base_result_revision=1,
            reviewer_name="Audit",
            scenario_id="scenario-between-sides",
            confirmed_thickness_mm=18,
            material="Tablero",
            finish="Melamina",
            notes="Audit",
        ),
    )


for label, path in (("nonplanar", save_nonplanar_lines()), ("ocs", save_ocs_polyline()), ("ocs-three", save_ocs_three_views())):
    extraction = extract_drawing(path)
    print(label, "contours", [c.points_source for c in extraction.contours])
    print(label, "hypotheses", derive_rectangular_hypotheses(extraction))
    print(label, "scenarios", [s.id for s in derive_decomposition_scenarios(extraction)])

dim_path = save_dimlfac()
dim_extraction = extract_drawing(dim_path)
print("dimlfac dimension", dim_extraction.dimensions)
print("dimlfac graphic", dim_extraction.dimension_graphics)
print("dimlfac warnings", dim_extraction.warnings)
doc = ezdxf.readfile(dim_path)
dimension = next(entity for entity in doc.modelspace() if entity.dxftype() == "DIMENSION")
print("dimlfac virtual text", [(e.dxftype(), e.dxf.text) for e in dimension.virtual_entities() if e.dxftype() in {"TEXT", "MTEXT"}])

base = reviewed_result()
thick = DemoRepository(OUT / "descriptor.sqlite3").review(
    base.run_id,
    ReviewRequest(
        base_result_revision=base.result_revision,
        reviewer_name="Agente auditor",
        scenario_id="scenario-between-sides",
        confirmed_thickness_mm=36,
        material="Tablero",
        finish="Melamina",
        notes="Segunda revisión real para auditar dependencia del espesor.",
    ),
)
print("36mm reviewed lengths", [(piece.role, piece.length_mm) for piece in thick.pieces])
print("36mm scene", reconstruct_scene(extract_drawing(ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"), thick).state)
material_payload = deepcopy(base.model_dump(mode="json"))
for piece in material_payload["pieces"]:
    piece["material"] = "Acero"
material_changed = Result.model_validate(material_payload)
for label, value in (("18mm", base), ("36mm", thick), ("material-acero", material_changed)):
    descriptor = build_descriptor(value)
    print(label, descriptor.model_dump(mode="json"))
    print(label, descriptor_fingerprint(descriptor), semantic_text(descriptor))
