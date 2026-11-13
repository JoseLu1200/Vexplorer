"""Build original DXF fixtures made only of separate local part views.

The generated drawings expose opaque grouping keys and optional quantities as
visible text. They deliberately contain no furniture, role, construction, or
bill-of-material semantics. Evaluator-only references live outside this module.
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


GEOMETRY_LAYER: Final = "PART_GEOMETRY"
DIMENSIONS_LAYER: Final = "DIMENSIONS"
LABELS_LAYER: Final = "LABELS"


@dataclass(frozen=True)
class PartSpec:
    key: str
    length: float
    width: float
    thickness: float
    qty: int


@dataclass(frozen=True)
class FixtureSpec:
    parts: tuple[PartSpec, ...]
    missing_qty_keys: frozenset[str] = frozenset()
    missing_thickness_keys: frozenset[str] = frozenset()
    origin_x: float = 0.0
    origin_y: float = 0.0
    ambiguous: bool = False


BASE_PARTS: Final = (
    PartSpec("K1", 1200.0, 300.0, 18.0, 2),
    PartSpec("K2", 864.0, 300.0, 18.0, 2),
    PartSpec("K3", 864.0, 300.0, 18.0, 2),
)
THICK_PARTS: Final = (
    PartSpec("K1", 1200.0, 300.0, 36.0, 2),
    PartSpec("K2", 828.0, 300.0, 36.0, 2),
    PartSpec("K3", 828.0, 300.0, 36.0, 2),
)
VARIANT_PARTS: Final = (
    PartSpec("K1", 1300.0, 320.0, 18.0, 2),
    PartSpec("K2", 964.0, 320.0, 18.0, 2),
    PartSpec("K3", 964.0, 320.0, 18.0, 2),
)
TRANSLATED_PARTS: Final = (
    PartSpec("R7", 1200.0, 300.0, 18.0, 2),
    PartSpec("R8", 864.0, 300.0, 18.0, 2),
    PartSpec("R9", 864.0, 300.0, 18.0, 2),
)

FIXTURES: Final = {
    "piezas_completo.dxf": FixtureSpec(BASE_PARTS),
    "piezas_qty_desconocida.dxf": FixtureSpec(
        BASE_PARTS, missing_qty_keys=frozenset({"K3"})
    ),
    "piezas_espesor_desconocido.dxf": FixtureSpec(
        BASE_PARTS, missing_thickness_keys=frozenset({"K3"})
    ),
    "piezas_dimensiones_variante.dxf": FixtureSpec(VARIANT_PARTS),
    "piezas_espesor_36.dxf": FixtureSpec(THICK_PARTS),
    "piezas_ids_trasladados.dxf": FixtureSpec(
        TRANSLATED_PARTS, origin_x=5000.0, origin_y=2500.0
    ),
    "piezas_ambigua_sin_id.dxf": FixtureSpec((BASE_PARTS[0],), ambiguous=True),
}


def _rectangle(modelspace, x: float, y: float, width: float, height: float) -> None:
    modelspace.add_lwpolyline(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        close=True,
        dxfattribs={"layer": GEOMETRY_LAYER},
    )


def _label(modelspace, text: str, position: tuple[float, float]) -> None:
    modelspace.add_text(
        text,
        height=22.0,
        dxfattribs={"layer": LABELS_LAYER},
    ).set_placement(position)


def _horizontal_dimension(
    modelspace, x: float, y: float, width: float, *, offset: float = 45.0
) -> None:
    dimension = modelspace.add_linear_dim(
        base=(x, y - offset),
        p1=(x, y),
        p2=(x + width, y),
        angle=0.0,
        dimstyle="Standard",
        dxfattribs={"layer": DIMENSIONS_LAYER},
    )
    dimension.render()


def _vertical_dimension(
    modelspace, x: float, y: float, height: float, *, offset: float = 45.0
) -> None:
    dimension = modelspace.add_linear_dim(
        base=(x - offset, y),
        p1=(x, y),
        p2=(x, y + height),
        angle=90.0,
        dimstyle="Standard",
        dxfattribs={"layer": DIMENSIONS_LAYER},
    )
    dimension.render()


def _view(
    modelspace,
    *,
    key: str | None,
    view: str,
    x: float,
    y: float,
    axis_x: float,
    axis_y: float,
) -> None:
    _rectangle(modelspace, x, y, axis_x, axis_y)
    _horizontal_dimension(modelspace, x, y, axis_x)
    _vertical_dimension(modelspace, x, y, axis_y)
    _label(modelspace, f"PART {key} {view}" if key else view, (x, y + axis_y + 30.0))


def build_fixture(path: Path, spec: FixtureSpec) -> None:
    """Write a DXF whose only geometry is separate local views."""
    previous_fixed_metadata = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.MM
    doc.layers.add(GEOMETRY_LAYER, color=7)
    doc.layers.add(DIMENSIONS_LAYER, color=2)
    doc.layers.add(LABELS_LAYER, color=3)
    modelspace = doc.modelspace()

    column_x = (spec.origin_x, spec.origin_x + 1500.0, spec.origin_x + 3000.0)
    row_y = spec.origin_y
    for part in spec.parts:
        public_key = None if spec.ambiguous else part.key
        _view(
            modelspace,
            key=public_key,
            view="FRONT",
            x=column_x[0],
            y=row_y,
            axis_x=part.length,
            axis_y=part.width,
        )
        if part.key not in spec.missing_thickness_keys:
            _view(
                modelspace,
                key=public_key,
                view="TOP",
                x=column_x[1],
                y=row_y,
                axis_x=part.length,
                axis_y=part.thickness,
            )
            _view(
                modelspace,
                key=public_key,
                view="SIDE",
                x=column_x[2],
                y=row_y,
                axis_x=part.thickness,
                axis_y=part.width,
            )
        if spec.ambiguous:
            _label(modelspace, f"QTY {part.qty}", (column_x[0], row_y + part.width + 65.0))
        elif part.key not in spec.missing_qty_keys:
            _label(
                modelspace,
                f"QTY {part.key} {part.qty}",
                (column_x[0], row_y + part.width + 65.0),
            )
        row_y += max(part.width, 320.0) + 260.0

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
        "fixture_collection": "original_synthetic_separate_part_views",
        "provenance": "authored_for_development_not_derived_from_a_corpus",
        "license_audit": "no_third_party_source_assets",
        "input_contract": {
            "format": "DXF R2010",
            "units": "mm",
            "semantics": "separate_local_part_views",
            "visible_labels": ["PART <opaque_key> FRONT|TOP|SIDE", "QTY <opaque_key> <n>"],
            "local_axes": ["FRONT=(L,W)", "TOP=(L,T)", "SIDE=(T,W)"],
        },
        "cases": {
            "piezas_completo.dxf": {"purpose": "complete_visible_evidence"},
            "piezas_qty_desconocida.dxf": {"purpose": "one_missing_qty_annotation"},
            "piezas_espesor_desconocido.dxf": {"purpose": "one_missing_thickness_view_pair"},
            "piezas_dimensiones_variante.dxf": {"purpose": "changed_local_dimensions"},
            "piezas_espesor_36.dxf": {"purpose": "changed_visible_thickness"},
            "piezas_ids_trasladados.dxf": {"purpose": "changed_keys_and_global_translation"},
            "piezas_ambigua_sin_id.dxf": {"purpose": "views_without_grouping_key"},
        },
    }
    (output_dir / "piezas_manifest.json").write_text(
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
