from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import ezdxf


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data" / "planos_demo"
REFERENCE_PATH = ROOT / "evaluation" / "reference" / "mesa_reference.json"
PUBLIC_CASES = (
    "mesa_demo_001.dxf",
    "mesa_demo_002.dxf",
    "mesa_demo_003.dxf",
    "mesa_demo_004.dxf",
)


def _is_private_path(value: object) -> bool:
    try:
        candidate = Path(os.fspath(value)).resolve()
    except (TypeError, ValueError, OSError):
        return False
    private_dir = REFERENCE_PATH.parent.resolve()
    return candidate == private_dir or private_dir in candidate.parents


@contextmanager
def _deny_table_reference_reads():
    original_builtin_open = builtins.open
    original_path_open = Path.open

    def guarded_open(file, *args, **kwargs):
        assert not _is_private_path(file), f"private reference read attempted: {file}"
        return original_builtin_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args, **kwargs):
        assert not _is_private_path(path), f"private reference read attempted: {path}"
        return original_path_open(path, *args, **kwargs)

    with patch("builtins.open", guarded_open), patch.object(Path, "open", guarded_path_open):
        yield


def _read(filename: str):
    path = PUBLIC_DIR / filename
    assert path.is_file(), f"missing public table fixture: {filename}"
    return ezdxf.readfile(path)


def _texts(filename: str) -> list[str]:
    return [
        entity.dxf.text.strip()
        for entity in _read(filename).modelspace().query("TEXT")
    ]


def _envelopes(filename: str) -> list[tuple[float, float, float, float]]:
    values = []
    for entity in _read(filename).modelspace().query(
        "LWPOLYLINE[layer=='VIEW_GEOMETRY']"
    ):
        points = [(point[0], point[1]) for point in entity.get_points("xy")]
        values.append(
            (
                round(min(x for x, _ in points), 6),
                round(min(y for _, y in points), 6),
                round(max(x for x, _ in points) - min(x for x, _ in points), 6),
                round(max(y for _, y in points) - min(y for _, y in points), 6),
            )
        )
    return values


def _segments(filename: str) -> set[tuple[float, float, float, float]]:
    return {
        tuple(
            round(value, 6)
            for value in (
                entity.dxf.start.x,
                entity.dxf.start.y,
                entity.dxf.end.x,
                entity.dxf.end.y,
            )
        )
        for entity in _read(filename).modelspace().query("LINE[layer=='VIEW_GEOMETRY']")
    }


def _dimensions(filename: str) -> list[tuple[float, str]]:
    return [
        (round(entity.get_measurement(), 6), entity.dxf.text)
        for entity in _read(filename).modelspace().query("DIMENSION")
    ]


def test_public_table_fixture_collection_exists() -> None:
    assert all((PUBLIC_DIR / filename).is_file() for filename in PUBLIC_CASES)
    assert (PUBLIC_DIR / "mesa_manifest.json").is_file()


def test_table_inputs_are_mounted_views_without_piece_or_bom_labels() -> None:
    forbidden = (
        "part",
        "qty",
        "piece",
        "component",
        "support",
        "leg",
        "top panel",
        "tablero",
        "soporte",
        "bom",
        "role",
    )
    for filename in PUBLIC_CASES:
        doc = _read(filename)
        surface = " ".join(_texts(filename)).casefold()
        assert doc.header["$INSUNITS"] == 4
        assert set(entity.dxf.layer for entity in doc.modelspace()) <= {
            "0",
            "Defpoints",
            "VIEW_GEOMETRY",
            "DIMENSIONS",
            "LABELS",
        }
        assert all(token not in surface for token in forbidden)
        assert all(not text.startswith(("PART ", "QTY ")) for text in _texts(filename))


def test_complete_table_encodes_three_assembled_view_regions() -> None:
    assert {"FRONT", "TOP", "SIDE"} <= set(_texts("mesa_demo_001.dxf"))
    assert _envelopes("mesa_demo_001.dxf") == [
        (0.0, 0.0, 1200.0, 750.0),
        (0.0, -1000.0, 1200.0, 700.0),
        (1500.0, 0.0, 700.0, 750.0),
    ]
    assert _segments("mesa_demo_001.dxf") == {
        (0.0, 720.0, 1200.0, 720.0),
        (18.0, 0.0, 18.0, 720.0),
        (1182.0, 0.0, 1182.0, 720.0),
        (1500.0, 720.0, 2200.0, 720.0),
    }
    assert _dimensions("mesa_demo_001.dxf") == [
        (1200.0, "<>"),
        (750.0, "<>"),
        (700.0, "<>"),
    ]


def test_dimension_variant_changes_geometry_and_general_dimensions() -> None:
    assert _envelopes("mesa_demo_002.dxf") == [
        (0.0, 0.0, 1400.0, 760.0),
        (0.0, -1100.0, 1400.0, 800.0),
        (1700.0, 0.0, 800.0, 760.0),
    ]
    assert _dimensions("mesa_demo_002.dxf") == [
        (1400.0, "<>"),
        (760.0, "<>"),
        (800.0, "<>"),
    ]


def test_incomplete_variant_omits_profile_without_inventing_an_answer() -> None:
    texts = _texts("mesa_demo_003.dxf")
    assert "FRONT" in texts and "TOP" in texts
    assert "SIDE" not in texts
    assert _envelopes("mesa_demo_003.dxf") == [
        (0.0, 0.0, 1200.0, 750.0),
        (0.0, -1000.0, 1200.0, 700.0),
    ]
    assert _segments("mesa_demo_003.dxf") == {
        (0.0, 720.0, 1200.0, 720.0),
        (18.0, 0.0, 18.0, 720.0),
        (1182.0, 0.0, 1182.0, 720.0),
    }


def test_conflict_control_keeps_geometry_and_visible_dimension_disagreement() -> None:
    dimensions = _dimensions("mesa_demo_004.dxf")
    assert dimensions[0] == (1200.0, "1190")
    assert _envelopes("mesa_demo_004.dxf")[0] == (0.0, 0.0, 1200.0, 750.0)


def test_public_manifest_is_uniform_and_non_diagnostic() -> None:
    manifest_path = PUBLIC_DIR / "mesa_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provenance"] == "authored_for_development_not_derived_from_a_corpus"
    assert manifest["license_audit"] == "no_third_party_source_assets"
    assert manifest["input_contract"] == {
        "format": "DXF R2010",
        "units": "mm",
        "semantics": "mounted_orthographic_views",
        "views": ["FRONT", "TOP", "SIDE"],
        "local_axes": ["FRONT=(W,H)", "TOP=(W,D)", "SIDE=(D,H)"],
    }
    assert set(manifest["cases"]) == set(PUBLIC_CASES)
    assert {item["purpose"] for item in manifest["cases"].values()} == {
        "mounted_orthographic_views_development_case"
    }
    public_surface = manifest_path.read_text(encoding="utf-8").casefold()
    assert all(
        token not in public_surface
        for token in ("missing", "incomplete", "conflict", "answer", "component", "bom")
    )


def test_table_fixture_generation_is_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for output in (first, second):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.build_table_fixture",
                "--output-dir",
                str(output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in first.iterdir()) == sorted(
        path.name for path in second.iterdir()
    )
    for first_path in first.iterdir():
        assert first_path.read_bytes() == (second / first_path.name).read_bytes()


def test_public_generator_cannot_read_the_private_table_reference(tmp_path: Path) -> None:
    from tools.build_table_fixture import build_all

    source = (ROOT / "tools" / "build_table_fixture.py").read_text(encoding="utf-8")
    assert "mesa_reference" not in source
    assert "evaluation" not in source
    with _deny_table_reference_reads():
        build_all(tmp_path / "public")
    assert sorted(path.name for path in (tmp_path / "public").iterdir()) == [
        *PUBLIC_CASES,
        "mesa_manifest.json",
    ]


def test_private_table_reference_is_evaluator_only_and_arithmetically_independent() -> None:
    assert REFERENCE_PATH.is_file()
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    assert reference["access_policy"] == {
        "evaluator_only": True,
        "runtime_allowed": False,
        "prompt_allowed": False,
        "tool_allowed": False,
    }
    complete = reference["cases"]["mesa_demo_001.dxf"]
    assert complete["reviewed_components"] == [
        {
            "role": "tabletop",
            "quantity": 1,
            "length_mm": 1200.0,
            "width_mm": 700.0,
            "thickness_mm": 30.0,
        },
        {
            "role": "side_support",
            "quantity": 2,
            "length_mm": 720.0,
            "width_mm": 700.0,
            "thickness_mm": 18.0,
        },
    ]
    economy = complete["independent_economy"]
    assert economy == {
        "currency": "EUR",
        "synthetic": True,
        "area_rate_eur_m2": 50.0,
        "setup_eur": 40.0,
        "piece_area_mm2": [840000.0, 504000.0, 504000.0],
        "piece_material_eur": [42.0, 25.2, 25.2],
        "total_area_mm2": 1848000.0,
        "material_eur": 92.4,
        "total_eur": 132.4,
    }
    assert sum(economy["piece_area_mm2"]) == 1848000.0
    assert sum(economy["piece_material_eur"]) + economy["setup_eur"] == 132.4


def test_private_reference_marks_incomplete_and_conflicting_evidence_before_review() -> None:
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    incomplete = reference["cases"]["mesa_demo_003.dxf"]
    conflict = reference["cases"]["mesa_demo_004.dxf"]
    assert incomplete["pre_review_unknowns"] == ["side_support.width_mm"]
    assert incomplete["reviewed_components"] is None
    assert conflict["pre_review_conflicts"] == {
        "overall_width_mm": {"geometry": 1200.0, "dimension_text": 1190.0}
    }
    assert conflict["reviewed_components"] is None
