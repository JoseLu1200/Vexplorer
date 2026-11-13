"""Build the public synthetic shelving DXF fixtures.

This module deliberately knows only the assembled views and their public
overall annotations.  The evaluator's part reference is authored and stored
outside every runtime surface and is never imported here.
"""

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
    height: float
    depth: float
    shelf_levels: tuple[float, ...]
    visible_offset: float = 18.0
    incomplete: bool = False
    source_unit: int = units.MM
    trapezoid_inset: float = 0.0


FIXTURES: Final = {
    "estanteria_montada.dxf": FixtureSpec(900.0, 1200.0, 300.0, (400.0, 800.0)),
    "estanteria_incompleta.dxf": FixtureSpec(
        900.0, 1200.0, 300.0, (400.0, 800.0), incomplete=True
    ),
    "mueble_demo_002.dxf": FixtureSpec(
        1000.0, 1300.0, 320.0, (433.0, 866.0)
    ),
    "mueble_demo_003.dxf": FixtureSpec(700.0, 800.0, 280.0, (400.0,)),
    "mueble_demo_unidades_desconocidas.dxf": FixtureSpec(
        900.0, 1200.0, 300.0, (400.0, 800.0), source_unit=0
    ),
    "mueble_demo_trapecio.dxf": FixtureSpec(
        900.0, 1200.0, 300.0, (), trapezoid_inset=80.0
    ),
}


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
        dimstyle="Standard",
        dxfattribs={"layer": DIMENSIONS_LAYER},
    )
    dimension.render()


def build_fixture(path: Path, spec: FixtureSpec) -> None:
    """Write one public DXF containing only assembled orthographic views."""
    previous_fixed_metadata = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    doc = ezdxf.new("R2010", setup=True)
    doc.units = spec.source_unit
    doc.layers.add(GEOMETRY_LAYER, color=7)
    doc.layers.add(DIMENSIONS_LAYER, color=2)
    doc.layers.add(LABELS_LAYER, color=3)
    modelspace = doc.modelspace()

    # FRONT: assembled outline plus two unresolved internal boundaries.
    if spec.trapezoid_inset:
        modelspace.add_lwpolyline(
            [
                (0.0, 0.0),
                (spec.width, 0.0),
                (spec.width - spec.trapezoid_inset, spec.height),
                (spec.trapezoid_inset, spec.height),
            ],
            close=True,
            dxfattribs={"layer": GEOMETRY_LAYER},
        )
    else:
        _rectangle(modelspace, 0.0, 0.0, spec.width, spec.height)
        for shelf_level in spec.shelf_levels:
            _line(modelspace, (0.0, shelf_level), (spec.width, shelf_level))
        if not spec.incomplete:
            _line(
                modelspace,
                (spec.visible_offset, 0.0),
                (spec.visible_offset, spec.height),
            )
            _line(
                modelspace,
                (spec.width - spec.visible_offset, 0.0),
                (spec.width - spec.visible_offset, spec.height),
            )
    _label(modelspace, "FRONT", (0.0, spec.height + 45.0))

    # TOP: only the mounted envelope is certain in the incomplete variant.
    top_y = -(spec.depth + 200.0)
    _rectangle(modelspace, 0.0, top_y, spec.width, spec.depth)
    if not spec.incomplete and not spec.trapezoid_inset:
        _line(
            modelspace,
            (spec.visible_offset, top_y),
            (spec.visible_offset, top_y + spec.depth),
        )
        _line(
            modelspace,
            (spec.width - spec.visible_offset, top_y),
            (spec.width - spec.visible_offset, top_y + spec.depth),
        )
    _label(modelspace, "TOP", (0.0, top_y + spec.depth + 45.0))

    # RIGHT: the horizontal boundaries remain observations, not part counts.
    right_x = spec.width + 300.0
    _rectangle(modelspace, right_x, 0.0, spec.depth, spec.height)
    if not spec.trapezoid_inset:
        for shelf_level in spec.shelf_levels:
            _line(
                modelspace,
                (right_x, shelf_level),
                (right_x + spec.depth, shelf_level),
            )
    _label(modelspace, "RIGHT", (right_x, spec.height + 45.0))

    _label(
        modelspace,
        "FIXTURE SINTETICO",
        (0.0, spec.height + 110.0),
        height=24.0,
    )

    # Public general dimensions.  The short observation is deliberately
    # absent from the incomplete variant, so thickness must remain unknown.
    _dimension(
        modelspace,
        base=(0.0, -90.0),
        p1=(0.0, 0.0),
        p2=(spec.width, 0.0),
        angle=0.0,
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
    if not spec.incomplete and not spec.trapezoid_inset:
        _dimension(
            modelspace,
            base=(0.0, top_y - 75.0),
            p1=(0.0, top_y),
            p2=(spec.visible_offset, top_y),
            angle=0.0,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    # ezdxf normally records timestamps and random GUIDs.  Fixed metadata and
    # stable class ordering make this authored fixture byte-reproducible.
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
            "mueble_demo_002.dxf": {
                "purpose": "development_fixture_with_changed_overall_dimensions",
                "requires_human_mounting_confirmation": True,
                "expected_unknown_fields": [],
            },
            "mueble_demo_003.dxf": {
                "purpose": "development_fixture_with_changed_internal_structure",
                "requires_human_mounting_confirmation": True,
                "expected_unknown_fields": [],
            },
            "mueble_demo_unidades_desconocidas.dxf": {
                "purpose": "negative_preview_fixture_with_unknown_source_units",
                "requires_human_mounting_confirmation": True,
                "expected_unknown_fields": ["effective_unit", "metric_dimensions"],
            },
            "mueble_demo_trapecio.dxf": {
                "purpose": "negative_preview_fixture_outside_rectangular_decomposition",
                "requires_human_mounting_confirmation": False,
                "expected_unknown_fields": [],
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

