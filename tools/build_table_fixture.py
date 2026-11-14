"""Build original DXF fixtures containing mounted orthographic views."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import ezdxf
from ezdxf import units


GEOMETRY_LAYER: Final = "VIEW_GEOMETRY"
DIMENSIONS_LAYER: Final = "DIMENSIONS"
LABELS_LAYER: Final = "LABELS"


@dataclass(frozen=True)
class FixtureSpec:
    width: float
    depth: float
    height: float
    top_thickness: float
    side_offset: float
    include_side: bool = True
    width_dimension_text: str = "<>"

    @property
    def lower_height(self) -> float:
        return self.height - self.top_thickness


BASE = FixtureSpec(1200.0, 700.0, 750.0, 30.0, 18.0)
FIXTURES: Final = {
    "mesa_demo_001.dxf": BASE,
    "mesa_demo_002.dxf": FixtureSpec(1400.0, 800.0, 760.0, 32.0, 20.0),
    "mesa_demo_003.dxf": FixtureSpec(
        1200.0, 700.0, 750.0, 30.0, 18.0, include_side=False
    ),
    "mesa_demo_004.dxf": FixtureSpec(
        1200.0, 700.0, 750.0, 30.0, 18.0, width_dimension_text="1190"
    ),
}


def _rectangle(modelspace, x: float, y: float, width: float, height: float) -> None:
    modelspace.add_lwpolyline(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        close=True,
        dxfattribs={"layer": GEOMETRY_LAYER},
    )


def _line(
    modelspace, start: tuple[float, float], end: tuple[float, float]
) -> None:
    modelspace.add_line(start, end, dxfattribs={"layer": GEOMETRY_LAYER})


def _label(modelspace, text: str, position: tuple[float, float]) -> None:
    modelspace.add_text(
        text,
        height=24.0,
        dxfattribs={"layer": LABELS_LAYER},
    ).set_placement(position)


def _dimension(
    modelspace,
    *,
    base: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    angle: float,
    text: str = "<>",
) -> None:
    override = modelspace.add_linear_dim(
        base=base,
        p1=p1,
        p2=p2,
        angle=angle,
        dimstyle="Standard",
        dxfattribs={"layer": DIMENSIONS_LAYER},
    )
    override.dimension.dxf.text = text
    override.render()


def build_fixture(path: Path, spec: FixtureSpec) -> None:
    """Write one public DXF containing only mounted source views."""
    previous_fixed_metadata = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.MM
    doc.layers.add(GEOMETRY_LAYER, color=7)
    doc.layers.add(DIMENSIONS_LAYER, color=2)
    doc.layers.add(LABELS_LAYER, color=3)
    modelspace = doc.modelspace()

    # FRONT: one mounted outline and visible boundaries, not separate local views.
    _rectangle(modelspace, 0.0, 0.0, spec.width, spec.height)
    _line(modelspace, (0.0, spec.lower_height), (spec.width, spec.lower_height))
    _line(
        modelspace,
        (spec.side_offset, 0.0),
        (spec.side_offset, spec.lower_height),
    )
    _line(
        modelspace,
        (spec.width - spec.side_offset, 0.0),
        (spec.width - spec.side_offset, spec.lower_height),
    )
    _label(modelspace, "FRONT", (0.0, spec.height + 45.0))

    # TOP exposes only the assembled envelope.
    top_y = -(spec.depth + 300.0)
    _rectangle(modelspace, 0.0, top_y, spec.width, spec.depth)
    _label(modelspace, "TOP", (0.0, top_y + spec.depth + 45.0))

    # SIDE is intentionally absent from the incomplete public variant.
    side_x = spec.width + 300.0
    if spec.include_side:
        _rectangle(modelspace, side_x, 0.0, spec.depth, spec.height)
        _line(
            modelspace,
            (side_x, spec.lower_height),
            (side_x + spec.depth, spec.lower_height),
        )
        _label(modelspace, "SIDE", (side_x, spec.height + 45.0))

    _label(modelspace, "FIXTURE SINTETICO", (0.0, spec.height + 105.0))

    # Only overall source dimensions are published. Short distances remain
    # geometric observations for the downstream ledger.
    _dimension(
        modelspace,
        base=(0.0, -90.0),
        p1=(0.0, 0.0),
        p2=(spec.width, 0.0),
        angle=0.0,
        text=spec.width_dimension_text,
    )
    _dimension(
        modelspace,
        base=(-110.0, 0.0),
        p1=(0.0, 0.0),
        p2=(0.0, spec.height),
        angle=90.0,
    )
    _dimension(
        modelspace,
        base=(-120.0, top_y),
        p1=(0.0, top_y),
        p2=(0.0, top_y + spec.depth),
        angle=90.0,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.classes.add_required_classes(doc.dxfversion)
    doc.classes.classes = OrderedDict(sorted(doc.classes.classes.items()))
    try:
        doc.saveas(path)
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous_fixed_metadata


def build_all(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, spec in FIXTURES.items():
        build_fixture(output_dir / filename, spec)
    manifest = {
        "fixture_collection": "original_synthetic_mounted_orthographic_views",
        "provenance": "authored_for_development_not_derived_from_a_corpus",
        "license_audit": "no_third_party_source_assets",
        "input_contract": {
            "format": "DXF R2010",
            "units": "mm",
            "semantics": "mounted_orthographic_views",
            "views": ["FRONT", "TOP", "SIDE"],
            "local_axes": ["FRONT=(W,H)", "TOP=(W,D)", "SIDE=(D,H)"],
        },
        "cases": {
            filename: {"purpose": "mounted_orthographic_views_development_case"}
            for filename in FIXTURES
        },
    }
    (output_dir / "mesa_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/planos_demo"))
    args = parser.parse_args()
    build_all(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
