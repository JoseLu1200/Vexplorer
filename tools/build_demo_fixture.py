"""Build the public synthetic shelving DXF fixtures.

This module deliberately knows only the assembled views and their public
overall annotations.  The evaluator's part reference is authored and stored
outside every runtime surface and is never imported here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

import ezdxf
from ezdxf import units


WIDTH: Final = 900.0
HEIGHT: Final = 1200.0
DEPTH: Final = 300.0
VISIBLE_OFFSET: Final = 18.0

GEOMETRY_LAYER: Final = "VIEW_GEOMETRY"
DIMENSIONS_LAYER: Final = "DIMENSIONS"
LABELS_LAYER: Final = "LABELS"


def _rectangle(modelspace, x: float, y: float, width: float, height: float) -> None:
    modelspace.add_lwpolyline(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        close=True,
        dxfattribs={"layer": GEOMETRY_LAYER},
    )


def _line(modelspace, start: tuple[float, float], end: tuple[float, float]) -> None:
    modelspace.add_line(start, end, dxfattribs={"layer": GEOMETRY_LAYER})


def _label(modelspace, text: str, position: tuple[float, float], height: float = 30.0) -> None:
    modelspace.add_text(
        text,
        height=height,
        dxfattribs={"layer": LABELS_LAYER},
    ).set_placement(position)


def _dimension(
    modelspace,
    *,
    base: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    angle: float,
) -> None:
    dimension = modelspace.add_linear_dim(
        base=base,
        p1=p1,
        p2=p2,
        angle=angle,
        dimstyle="EZDXF",
        dxfattribs={"layer": DIMENSIONS_LAYER},
    )
    dimension.render()


def build_fixture(path: Path, *, incomplete: bool) -> None:
    """Write one public DXF containing only assembled orthographic views."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.MM
    doc.layers.add(GEOMETRY_LAYER, color=7)
    doc.layers.add(DIMENSIONS_LAYER, color=2)
    doc.layers.add(LABELS_LAYER, color=3)
    modelspace = doc.modelspace()

    # FRONT: assembled outline plus two unresolved internal boundaries.
    _rectangle(modelspace, 0.0, 0.0, WIDTH, HEIGHT)
    _line(modelspace, (0.0, 400.0), (WIDTH, 400.0))
    _line(modelspace, (0.0, 800.0), (WIDTH, 800.0))
    if not incomplete:
        _line(modelspace, (VISIBLE_OFFSET, 0.0), (VISIBLE_OFFSET, HEIGHT))
        _line(modelspace, (WIDTH - VISIBLE_OFFSET, 0.0), (WIDTH - VISIBLE_OFFSET, HEIGHT))
    _label(modelspace, "FRONT", (0.0, HEIGHT + 45.0))

    # TOP: only the mounted envelope is certain in the incomplete variant.
    top_y = -500.0
    _rectangle(modelspace, 0.0, top_y, WIDTH, DEPTH)
    if not incomplete:
        _line(modelspace, (VISIBLE_OFFSET, top_y), (VISIBLE_OFFSET, top_y + DEPTH))
        _line(
            modelspace,
            (WIDTH - VISIBLE_OFFSET, top_y),
            (WIDTH - VISIBLE_OFFSET, top_y + DEPTH),
        )
    _label(modelspace, "TOP", (0.0, top_y + DEPTH + 45.0))

    # RIGHT: the horizontal boundaries remain observations, not part counts.
    right_x = 1200.0
    _rectangle(modelspace, right_x, 0.0, DEPTH, HEIGHT)
    _line(modelspace, (right_x, 400.0), (right_x + DEPTH, 400.0))
    _line(modelspace, (right_x, 800.0), (right_x + DEPTH, 800.0))
    _label(modelspace, "RIGHT", (right_x, HEIGHT + 45.0))

    _label(modelspace, "FIXTURE SINTETICO", (0.0, HEIGHT + 110.0), height=24.0)

    # Public general dimensions.  The short observation is deliberately
    # absent from the incomplete variant, so thickness must remain unknown.
    _dimension(
        modelspace,
        base=(0.0, -90.0),
        p1=(0.0, 0.0),
        p2=(WIDTH, 0.0),
        angle=0.0,
    )
    _dimension(
        modelspace,
        base=(-110.0, 0.0),
        p1=(0.0, 0.0),
        p2=(0.0, HEIGHT),
        angle=90.0,
    )
    _dimension(
        modelspace,
        base=(-120.0, top_y),
        p1=(0.0, top_y),
        p2=(0.0, top_y + DEPTH),
        angle=90.0,
    )
    if not incomplete:
        _dimension(
            modelspace,
            base=(0.0, top_y - 75.0),
            p1=(0.0, top_y),
            p2=(VISIBLE_OFFSET, top_y),
            angle=0.0,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


def build_all(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    build_fixture(output_dir / "estanteria_montada.dxf", incomplete=False)
    build_fixture(output_dir / "estanteria_incompleta.dxf", incomplete=True)
    manifest = {
        "fixture_family": "synthetic_rectangular_shelving",
        "provenance": "original_development_fixture_not_derived_from_a_corpus",
        "license_audit": "no_third_party_source_assets",
        "input_contract": {
            "format": "DXF R2010",
            "units": "mm",
            "views": ["FRONT", "TOP", "RIGHT"],
            "layers": [GEOMETRY_LAYER, DIMENSIONS_LAYER, LABELS_LAYER],
            "semantics": "assembled_views_are_observations_not_physical_quantities",
        },
        "cases": {
            "estanteria_montada.dxf": {
                "purpose": "development_fixture_with_general_dimensions_and_mounting_ambiguity",
                "requires_human_mounting_confirmation": True,
                "expected_unknown_fields": [],
            },
            "estanteria_incompleta.dxf": {
                "purpose": "development_fixture_with_missing_thickness_evidence",
                "requires_human_mounting_confirmation": True,
                "expected_unknown_fields": ["thickness"],
            },
        },
    }
    (output_dir / "fixture_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/planos_demo"),
        help="Public output directory (default: data/planos_demo)",
    )
    args = parser.parse_args()
    build_all(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

