"""Build sparse mounted-CAD controls and their separately stored references.

The public bundles contain only assembled orthographic views and a completion
instruction.  They never contain a piece list, quantities, construction roles,
scenario keys, or paths to evaluator references.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Final
import zipfile

import ezdxf
from ezdxf import units


COMPLETION_INSTRUCTION: Final = (
    "Interpret the assembled furniture views, deduce or estimate missing dimensions "
    "and construction details, and propose necessary parts with dimensioned piece "
    "drawings. Keep observations distinct from explicit estimates and explain "
    "important decisions."
)
PUBLIC_CASE_IDS: Final = ("F01", "F02", "F03")
GEOMETRY_LAYER: Final = "G01"
ANNOTATION_LAYER: Final = "A01"
DIMENSION_LAYER: Final = "D01"
HIDDEN_LAYER: Final = "H01"
_ZIP_TIMESTAMP: Final = (2026, 11, 14, 0, 0, 0)


def _rectangle(
    modelspace: Any,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    layer: str = GEOMETRY_LAYER,
) -> None:
    modelspace.add_lwpolyline(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        close=True,
        dxfattribs={"layer": layer},
    )


def _text(modelspace: Any, value: str, at: tuple[float, float]) -> None:
    modelspace.add_text(
        value,
        height=22.0,
        dxfattribs={"layer": ANNOTATION_LAYER},
    ).set_placement(at)


def _dimension(
    modelspace: Any,
    *,
    base: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    angle: float,
) -> None:
    override = modelspace.add_linear_dim(
        base=base,
        p1=p1,
        p2=p2,
        angle=angle,
        dimstyle="Standard",
        dxfattribs={"layer": DIMENSION_LAYER},
    )
    override.render()


def _new_document() -> Any:
    previous = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    try:
        document = ezdxf.new("R2010", setup=True)
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous
    document.units = units.MM
    document.layers.add(GEOMETRY_LAYER, color=7)
    document.layers.add(ANNOTATION_LAYER, color=3)
    document.layers.add(DIMENSION_LAYER, color=2)
    document.layers.add(HIDDEN_LAYER, color=8, linetype="DASHED")
    return document


def _save_deterministic(document: Any, path: Path) -> bytes:
    previous = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    document.classes.add_required_classes(document.dxfversion)
    document.classes.classes = OrderedDict(sorted(document.classes.classes.items()))
    try:
        document.saveas(path)
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous
    return path.read_bytes()


def _build_f01(path: Path) -> bytes:
    """Mounted views with four source dimensions and hidden apron thickness."""

    document = _new_document()
    modelspace = document.modelspace()

    # V01: assembled elevation. Geometry determines 50 mm supports and 60 mm
    # edge offsets, but those distances are intentionally not dimension entities.
    _rectangle(modelspace, 0.0, 720.0, 1200.0, 30.0)
    _rectangle(modelspace, 60.0, 0.0, 50.0, 720.0)
    _rectangle(modelspace, 1090.0, 0.0, 50.0, 720.0)
    _rectangle(modelspace, 110.0, 620.0, 980.0, 100.0)
    _text(modelspace, "V01", (0.0, 800.0))

    # V02: assembled side elevation. The apron is visible face-on; its hidden
    # through-thickness remains genuinely underdetermined.
    side_x = 1500.0
    _rectangle(modelspace, side_x, 720.0, 600.0, 30.0)
    _rectangle(modelspace, side_x + 60.0, 0.0, 50.0, 720.0)
    _rectangle(modelspace, side_x + 490.0, 0.0, 50.0, 720.0)
    _rectangle(modelspace, side_x + 110.0, 620.0, 380.0, 100.0)
    _text(modelspace, "V02", (side_x, 800.0))

    # V03: assembled plan. Only support footprints are shown as hidden source
    # geometry; no local piece view or quantity annotation is supplied.
    plan_y = 1050.0
    _rectangle(modelspace, 0.0, plan_y, 1200.0, 600.0)
    for x in (60.0, 1090.0):
        for y in (plan_y + 60.0, plan_y + 490.0):
            _rectangle(modelspace, x, y, 50.0, 50.0, layer=HIDDEN_LAYER)
    _text(modelspace, "V03", (0.0, plan_y + 650.0))

    _dimension(
        modelspace,
        base=(0.0, -100.0),
        p1=(0.0, 0.0),
        p2=(1200.0, 0.0),
        angle=0.0,
    )
    _dimension(
        modelspace,
        base=(-120.0, 0.0),
        p1=(0.0, 0.0),
        p2=(0.0, 750.0),
        angle=90.0,
    )
    _dimension(
        modelspace,
        base=(side_x, -100.0),
        p1=(side_x, 0.0),
        p2=(side_x + 600.0, 0.0),
        angle=0.0,
    )
    _dimension(
        modelspace,
        base=(1230.0, 720.0),
        p1=(1200.0, 720.0),
        p2=(1200.0, 750.0),
        angle=90.0,
    )

    return _save_deterministic(document, path)


def _build_f02(path: Path) -> bytes:
    """Mounted three-front cabinet; joint order and drawer hardware stay hidden."""

    document = _new_document()
    modelspace = document.modelspace()
    # V01 front. The inner rectangle does not encode whether horizontal panels
    # terminate at the sides or cap them.
    _rectangle(modelspace, 0.0, 0.0, 900.0, 800.0)
    _rectangle(modelspace, 18.0, 18.0, 864.0, 764.0)
    for y in (21.0, 275.0, 529.0):
        _rectangle(modelspace, 21.0, y, 858.0, 250.0)
    _text(modelspace, "V01", (0.0, 850.0))

    # V02 side and V03 plan expose only assembled envelopes and visible front
    # divisions. Slide clearances, box depth and back thickness remain absent.
    side_x = 1200.0
    _rectangle(modelspace, side_x, 0.0, 450.0, 800.0)
    for y in (18.0, 272.0, 526.0, 782.0):
        modelspace.add_line(
            (side_x, y), (side_x + 450.0, y), dxfattribs={"layer": GEOMETRY_LAYER}
        )
    _text(modelspace, "V02", (side_x, 850.0))
    plan_y = 1050.0
    _rectangle(modelspace, 0.0, plan_y, 900.0, 450.0)
    modelspace.add_line(
        (18.0, plan_y), (18.0, plan_y + 450.0), dxfattribs={"layer": GEOMETRY_LAYER}
    )
    modelspace.add_line(
        (882.0, plan_y), (882.0, plan_y + 450.0), dxfattribs={"layer": GEOMETRY_LAYER}
    )
    _text(modelspace, "V03", (0.0, plan_y + 500.0))

    _dimension(modelspace, base=(0.0, -100.0), p1=(0.0, 0.0), p2=(900.0, 0.0), angle=0.0)
    _dimension(modelspace, base=(-120.0, 0.0), p1=(0.0, 0.0), p2=(0.0, 800.0), angle=90.0)
    _dimension(
        modelspace,
        base=(side_x, -100.0),
        p1=(side_x, 0.0),
        p2=(side_x + 450.0, 0.0),
        angle=0.0,
    )
    _dimension(modelspace, base=(930.0, 0.0), p1=(900.0, 0.0), p2=(900.0, 18.0), angle=90.0)
    return _save_deterministic(document, path)


def _build_f03(path: Path) -> bytes:
    """Mounted open shelving; rear stabilization is intentionally unresolved."""

    document = _new_document()
    modelspace = document.modelspace()
    _rectangle(modelspace, 0.0, 0.0, 800.0, 1800.0)
    _rectangle(modelspace, 18.0, 18.0, 764.0, 1764.0)
    for y in (360.0, 720.0, 1080.0, 1440.0):
        _rectangle(modelspace, 18.0, y, 764.0, 18.0)
    _text(modelspace, "V01", (0.0, 1850.0))

    side_x = 1100.0
    _rectangle(modelspace, side_x, 0.0, 300.0, 1800.0)
    for y in (18.0, 360.0, 720.0, 1080.0, 1440.0, 1782.0):
        modelspace.add_line(
            (side_x, y), (side_x + 300.0, y), dxfattribs={"layer": GEOMETRY_LAYER}
        )
    _text(modelspace, "V02", (side_x, 1850.0))
    plan_y = 2050.0
    _rectangle(modelspace, 0.0, plan_y, 800.0, 300.0)
    modelspace.add_line(
        (18.0, plan_y), (18.0, plan_y + 300.0), dxfattribs={"layer": GEOMETRY_LAYER}
    )
    modelspace.add_line(
        (782.0, plan_y), (782.0, plan_y + 300.0), dxfattribs={"layer": GEOMETRY_LAYER}
    )
    _text(modelspace, "V03", (0.0, plan_y + 350.0))

    _dimension(modelspace, base=(0.0, -100.0), p1=(0.0, 0.0), p2=(800.0, 0.0), angle=0.0)
    _dimension(modelspace, base=(-120.0, 0.0), p1=(0.0, 0.0), p2=(0.0, 1800.0), angle=90.0)
    _dimension(
        modelspace,
        base=(side_x, -100.0),
        p1=(side_x, 0.0),
        p2=(side_x + 300.0, 0.0),
        angle=0.0,
    )
    _dimension(modelspace, base=(830.0, 0.0), p1=(800.0, 0.0), p2=(800.0, 18.0), angle=90.0)
    return _save_deterministic(document, path)


def _exact(kind: str, value: float, relation: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": kind, "exact": value}
    if relation is not None:
        result["relation"] = relation
    return result


def _range(minimum: float, maximum: float, premise: str) -> dict[str, Any]:
    return {
        "kind": "estimated",
        "minimum": minimum,
        "maximum": maximum,
        "premise": premise,
    }


def _f01_reference(public_hash: str) -> dict[str, Any]:
    apron_thickness = _range(
        18.0,
        25.0,
        "panel apron thickness is not visible in the source views",
    )
    return {
        "schema_version": "1.0",
        "case_id": "F01",
        "reference_kind": "developer_functional_control",
        "public_input_sha256": public_hash,
        "acceptable_scenarios": [
            {
                "key": "four_supports_with_perimeter_aprons",
                "necessary_piece_types": [
                    {
                        "role": "work_surface",
                        "quantity": 1,
                        "dimensions_mm": {
                            "length": _exact("observed", 1200.0),
                            "width": _exact("observed", 600.0),
                            "thickness": _exact("observed", 30.0),
                        },
                    },
                    {
                        "role": "vertical_support",
                        "quantity": 4,
                        "dimensions_mm": {
                            "length": _exact(
                                "deduced",
                                720.0,
                                "overall_height - surface_thickness",
                            ),
                            "width": _exact("deduced", 50.0, "support footprint span"),
                            "thickness": _exact(
                                "deduced", 50.0, "support footprint span"
                            ),
                        },
                    },
                    {
                        "role": "longitudinal_apron",
                        "quantity": 2,
                        "dimensions_mm": {
                            "length": _exact(
                                "deduced",
                                980.0,
                                "overall_width - 2 * (edge_inset + support_width)",
                            ),
                            "width": _exact("deduced", 100.0, "visible elevation span"),
                            "thickness": apron_thickness,
                        },
                    },
                    {
                        "role": "transverse_apron",
                        "quantity": 2,
                        "dimensions_mm": {
                            "length": _exact(
                                "deduced",
                                380.0,
                                "overall_depth - 2 * (edge_inset + support_width)",
                            ),
                            "width": _exact("deduced", 100.0, "visible elevation span"),
                            "thickness": apron_thickness,
                        },
                    },
                ],
                "closure_constraints": [
                    "vertical_support.length + work_surface.thickness = 750",
                    "longitudinal_apron.length + 2 * (60 + vertical_support.width) = 1200",
                    "transverse_apron.length + 2 * (60 + vertical_support.width) = 600",
                    "all four supports terminate at the underside of the work surface",
                ],
                "allowed_variation": (
                    "Any numeric apron thickness in the stated interval is acceptable when "
                    "declared as an estimate with its premise; it is not source-confirmed."
                ),
            }
        ],
        "utility_checks": {
            "necessary_piece_types_complete": True,
            "scenario_quantities_numeric": True,
            "primary_piece_list_numeric": True,
            "closure_constraints_satisfied": True,
            "piece_drawings": {
                "required_formats": ["svg", "dxf"],
                "per_piece_type": True,
                "numeric_dimensions_required": True,
            },
        },
        "epistemic_rules": {
            "source_dimensions": "observed",
            "geometry_fixed_offsets": "deduced",
            "hidden_construction_values": "estimated_with_range_and_premise",
            "scenario_occurrences": "hypothesis",
        },
        "limitations": [
            "This authored fixture is a functional development control, not a blind benchmark.",
            "It checks a coherent provisional construction scenario, not fabrication certification.",
        ],
    }


def _common_reference(case_id: str, public_hash: str, scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "reference_kind": "developer_functional_control",
        "public_input_sha256": public_hash,
        "acceptable_scenarios": scenarios,
        "utility_checks": {
            "necessary_piece_types_complete": True,
            "scenario_quantities_numeric": True,
            "primary_piece_list_numeric": True,
            "closure_constraints_satisfied": True,
            "piece_drawings": {
                "required_formats": ["svg", "dxf"],
                "per_piece_type": True,
                "numeric_dimensions_required": True,
            },
        },
        "epistemic_rules": {
            "source_dimensions": "observed",
            "geometry_fixed_offsets": "deduced",
            "hidden_construction_values": "estimated_with_range_and_premise",
            "scenario_occurrences": "hypothesis",
        },
        "limitations": [
            "This authored fixture is a functional development control, not a blind benchmark.",
            "Alternative scenarios are accepted only when their own closure constraints hold.",
        ],
    }


def _f02_piece_types(*, capped: bool) -> list[dict[str, Any]]:
    side_length = 764.0 if capped else 800.0
    horizontal_length = 900.0 if capped else 864.0
    return [
        {
            "role": "side_panel",
            "quantity": 2,
            "dimensions_mm": {
                "length": _exact("deduced", side_length, "selected carcass joint scenario"),
                "width": _exact("observed", 450.0),
                "thickness": _exact("deduced", 18.0, "common panel span"),
            },
        },
        {
            "role": "top_bottom_panel",
            "quantity": 2,
            "dimensions_mm": {
                "length": _exact("deduced", horizontal_length, "selected carcass joint scenario"),
                "width": _exact("observed", 450.0),
                "thickness": _exact("deduced", 18.0, "common panel span"),
            },
        },
        {
            "role": "back_panel",
            "quantity": 1,
            "dimensions_mm": {
                "length": _range(760.0, 800.0, "overlay or inset back is not resolved"),
                "width": _range(860.0, 900.0, "overlay or inset back is not resolved"),
                "thickness": _range(3.0, 6.0, "back thickness is hidden"),
            },
        },
        {
            "role": "drawer_front",
            "quantity": 3,
            "dimensions_mm": {
                "length": _exact("deduced", 858.0, "front elevation span"),
                "width": _exact("deduced", 250.0, "front elevation span"),
                "thickness": _range(16.0, 19.0, "front thickness is hidden"),
            },
        },
        {
            "role": "drawer_box_side",
            "quantity": 6,
            "dimensions_mm": {
                "length": _range(380.0, 420.0, "runner setback and clearance are hidden"),
                "width": _range(160.0, 210.0, "box height is hidden behind the front"),
                "thickness": _range(12.0, 16.0, "drawer material is hidden"),
            },
        },
        {
            "role": "drawer_box_front_back",
            "quantity": 6,
            "dimensions_mm": {
                "length": _range(820.0, 838.0, "slide and joinery clearance are hidden"),
                "width": _range(160.0, 210.0, "box height is hidden behind the front"),
                "thickness": _range(12.0, 16.0, "drawer material is hidden"),
            },
        },
        {
            "role": "drawer_bottom",
            "quantity": 3,
            "dimensions_mm": {
                "length": _range(820.0, 850.0, "groove and box joint details are hidden"),
                "width": _range(380.0, 420.0, "runner setback and clearance are hidden"),
                "thickness": _range(3.0, 8.0, "bottom construction is hidden"),
            },
        },
    ]


def _f02_reference(public_hash: str) -> dict[str, Any]:
    scenarios = []
    for key, capped in (
        ("horizontal_panels_between_sides", False),
        ("horizontal_panels_cap_sides", True),
    ):
        scenarios.append(
            {
                "key": key,
                "necessary_piece_types": _f02_piece_types(capped=capped),
                "closure_constraints": [
                    "carcass outside width = 900",
                    "carcass outside height = 800",
                    "clear opening width = 900 - 2 * 18",
                    "three drawer fronts preserve the visible gaps",
                    "drawer box width includes an explicit selected slide clearance",
                    "back placement is stated as overlay or inset and closes its chosen envelope",
                ],
                "allowed_variation": (
                    "Drawer-box values inside the stated intervals are acceptable only with "
                    "a named slide-clearance and joinery premise."
                ),
            }
        )
    return _common_reference("F02", public_hash, scenarios)


def _f03_base_pieces() -> list[dict[str, Any]]:
    return [
        {
            "role": "side_panel",
            "quantity": 2,
            "dimensions_mm": {
                "length": _exact("observed", 1800.0),
                "width": _exact("observed", 300.0),
                "thickness": _exact("deduced", 18.0, "common panel span"),
            },
        },
        {
            "role": "top_bottom_panel",
            "quantity": 2,
            "dimensions_mm": {
                "length": _exact("deduced", 764.0, "overall_width - 2 * panel_thickness"),
                "width": _exact("observed", 300.0),
                "thickness": _exact("deduced", 18.0, "common panel span"),
            },
        },
        {
            "role": "internal_shelf",
            "quantity": 4,
            "dimensions_mm": {
                "length": _exact("deduced", 764.0, "overall_width - 2 * panel_thickness"),
                "width": _exact("observed", 300.0),
                "thickness": _exact("deduced", 18.0, "repeated visible shelf span"),
            },
        },
    ]


def _f03_reference(public_hash: str) -> dict[str, Any]:
    backed = _f03_base_pieces() + [
        {
            "role": "back_panel",
            "quantity": 1,
            "dimensions_mm": {
                "length": _exact("deduced", 1800.0, "outside envelope"),
                "width": _exact("deduced", 800.0, "outside envelope"),
                "thickness": _range(3.0, 6.0, "rear construction is absent from the views"),
            },
        }
    ]
    return _common_reference(
        "F03",
        public_hash,
        [
            {
                "key": "open_back_with_anchoring",
                "necessary_piece_types": _f03_base_pieces(),
                "closure_constraints": [
                    "outside width = 800",
                    "outside height = 1800",
                    "each horizontal panel spans 800 - 2 * 18",
                    "four internal shelf occurrences preserve the visible elevations",
                    "anti-racking wall anchoring or equivalent explicit bracing is required",
                ],
                "allowed_variation": "No back panel is acceptable only with an explicit anti-racking premise.",
            },
            {
                "key": "thin_structural_back",
                "necessary_piece_types": backed,
                "closure_constraints": [
                    "outside width = 800",
                    "outside height = 1800",
                    "each horizontal panel spans 800 - 2 * 18",
                    "four internal shelf occurrences preserve the visible elevations",
                    "the rear panel closes the outside envelope and supplies anti-racking action",
                ],
                "allowed_variation": "Back thickness may vary inside the estimated interval.",
            },
        ],
    )


def _write_json(path: Path, value: Any) -> bytes:
    encoded = (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    path.write_bytes(encoded)
    return encoded


def _write_bundle(path: Path, dxf_bytes: bytes, metadata: dict[str, Any]) -> None:
    case_bytes = (
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in (("input.dxf", dxf_bytes), ("case.json", case_bytes)):
            info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, raw)


def build_controls(
    public_dir: Path,
    private_dir: Path,
    *,
    case_ids: tuple[str, ...] = PUBLIC_CASE_IDS,
) -> dict[str, dict[str, str]]:
    """Build requested controls without ever embedding private references publicly."""

    unknown = set(case_ids) - set(PUBLIC_CASE_IDS)
    if unknown:
        raise ValueError(f"controls_not_implemented:{','.join(sorted(unknown))}")
    public_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, str]] = {}
    for case_id in case_ids:
        public_dxf = public_dir / f"{case_id}.dxf"
        dxf_bytes = {
            "F01": _build_f01,
            "F02": _build_f02,
            "F03": _build_f03,
        }[case_id](public_dxf)
        source_hash = sha256(dxf_bytes).hexdigest()
        metadata = {
            "id": case_id,
            "file": "input.dxf",
            "format": "dxf",
            "unit": "mm",
            "view_kind": "assembled_orthographic",
            "instruction": COMPLETION_INSTRUCTION,
            "sha256": source_hash,
        }
        bundle = public_dir / f"{case_id}.zip"
        _write_bundle(bundle, dxf_bytes, metadata)
        reference = private_dir / f"{case_id}.reference.json"
        reference_bytes = _write_json(
            reference,
            {
                "F01": _f01_reference,
                "F02": _f02_reference,
                "F03": _f03_reference,
            }[case_id](source_hash),
        )
        result[case_id] = {
            "public_bundle_sha256": sha256(bundle.read_bytes()).hexdigest(),
            "private_reference_sha256": sha256(reference_bytes).hexdigest(),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public-dir",
        type=Path,
        default=Path("data/cad_completion_controls/public"),
    )
    parser.add_argument(
        "--private-dir",
        type=Path,
        default=Path("evaluation/reference/cad_completion_controls"),
    )
    parser.add_argument("--case-id", action="append", choices=PUBLIC_CASE_IDS)
    args = parser.parse_args()
    case_ids = tuple(args.case_id) if args.case_id else PUBLIC_CASE_IDS
    result = build_controls(args.public_dir, args.private_dir, case_ids=case_ids)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
