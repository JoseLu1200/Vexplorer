from __future__ import annotations

import ezdxf

from backend.app.geometria import extract_drawing
from backend.app.servicios.decomposition import derive_decomposition_scenarios


def test_coherent_trapezoid_views_do_not_create_rectangular_shelving_scenarios(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    # Bounding boxes satisfy W/H/D compatibility, while the evidence is non-rectangular.
    modelspace.add_lwpolyline([(0, 0), (400, 0), (360, 1200), (30, 1200)], close=True)
    modelspace.add_text("FRONT").set_placement((0, -50))
    modelspace.add_lwpolyline([(1000, 0), (1400, 0), (1360, 600), (1030, 600)], close=True)
    modelspace.add_text("TOP").set_placement((1000, -50))
    modelspace.add_lwpolyline([(2000, 0), (2600, 0), (2560, 1200), (2030, 1200)], close=True)
    modelspace.add_text("RIGHT").set_placement((2000, -50))
    path = tmp_path / "coherent-trapezoids.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert {view.label for view in extraction.views} == {"FRONT", "TOP", "SIDE"}
    assert len(extraction.contours) == 3
    assert derive_decomposition_scenarios(extraction) == ()
