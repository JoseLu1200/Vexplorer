from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf
import pytest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data" / "planos_demo"
REFERENCE_PATH = ROOT / "evaluation" / "reference" / "piezas_reference.json"
PUBLIC_CASES = (
    "piezas_completo.dxf",
    "piezas_qty_desconocida.dxf",
    "piezas_espesor_desconocido.dxf",
    "piezas_dimensiones_variante.dxf",
    "piezas_espesor_36.dxf",
    "piezas_ids_trasladados.dxf",
    "piezas_ambigua_sin_id.dxf",
)


def _read(filename: str):
    return ezdxf.readfile(PUBLIC_DIR / filename)


def _texts(filename: str) -> list[str]:
    return [
        entity.dxf.text.strip()
        for entity in _read(filename).modelspace().query("TEXT")
    ]


def _rectangles(filename: str) -> list[tuple[float, float, float, float]]:
    values = []
    for entity in _read(filename).modelspace().query("LWPOLYLINE[layer=='PART_GEOMETRY']"):
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


@pytest.mark.parametrize("filename", PUBLIC_CASES)
def test_parts_only_dxf_has_public_layers_and_no_assembly_answer(filename: str) -> None:
    doc = _read(filename)
    texts = _texts(filename)

    assert doc.header["$INSUNITS"] == 4
    assert set(entity.dxf.layer for entity in doc.modelspace()) <= {
        "0",
        "Defpoints",
        "PART_GEOMETRY",
        "DIMENSIONS",
        "LABELS",
    }
    public_surface = " ".join(texts).casefold()
    forbidden = (
        "shelf",
        "side panel",
        "top panel",
        "base panel",
        "balda",
        "lateral",
        "estanteria",
        "assembly",
        "montaje",
        "bom",
        "family",
    )
    assert all(token not in public_surface for token in forbidden)
    assert all(not text.startswith(("WIDTH ", "HEIGHT ", "DEPTH ")) for text in texts)


def test_complete_fixture_has_three_local_views_but_quantity_comes_from_qty_text() -> None:
    texts = _texts("piezas_completo.dxf")
    views: dict[str, set[str]] = defaultdict(set)
    quantities: dict[str, int] = {}
    for text in texts:
        fields = text.split()
        if fields[:1] == ["PART"] and len(fields) == 3:
            views[fields[1]].add(fields[2])
        if fields[:1] == ["QTY"] and len(fields) == 3:
            quantities[fields[1]] = int(fields[2])

    assert views == {
        "K1": {"FRONT", "TOP", "SIDE"},
        "K2": {"FRONT", "TOP", "SIDE"},
        "K3": {"FRONT", "TOP", "SIDE"},
    }
    assert quantities == {"K1": 2, "K2": 2, "K3": 2}
    assert all(len(item_views) == 3 for item_views in views.values())
    assert sum(quantities.values()) == 6
    assert sum(quantities.values()) != sum(len(item_views) for item_views in views.values())


def test_complete_rectangles_encode_only_local_lw_lt_tw_axes() -> None:
    rectangles = _rectangles("piezas_completo.dxf")
    sizes = Counter((width, height) for _, _, width, height in rectangles)

    # Independently authored expectations for FRONT=(L,W), TOP=(L,T), SIDE=(T,W).
    assert sizes == {
        (1200.0, 300.0): 1,
        (1200.0, 18.0): 1,
        (864.0, 300.0): 2,
        (864.0, 18.0): 2,
        (18.0, 300.0): 3,
    }


def test_unknown_variants_remove_only_the_public_evidence_they_claim() -> None:
    qty_texts = _texts("piezas_qty_desconocida.dxf")
    thickness_texts = _texts("piezas_espesor_desconocido.dxf")

    assert "QTY K1 2" in qty_texts
    assert "QTY K2 2" in qty_texts
    assert all(not text.startswith("QTY K3 ") for text in qty_texts)
    assert sum(text.startswith("PART K3 ") for text in qty_texts) == 3

    assert "PART K3 FRONT" in thickness_texts
    assert "PART K3 TOP" not in thickness_texts
    assert "PART K3 SIDE" not in thickness_texts
    assert "QTY K3 2" in thickness_texts
    assert len(_rectangles("piezas_espesor_desconocido.dxf")) == 7


def test_dimension_and_translation_controls_change_only_intended_public_signals() -> None:
    base_rectangles = _rectangles("piezas_completo.dxf")
    translated_rectangles = _rectangles("piezas_ids_trasladados.dxf")
    variant_rectangles = _rectangles("piezas_dimensiones_variante.dxf")
    thick_rectangles = _rectangles("piezas_espesor_36.dxf")

    base_sizes = sorted((width, height) for _, _, width, height in base_rectangles)
    translated_sizes = sorted((width, height) for _, _, width, height in translated_rectangles)
    assert translated_sizes == base_sizes
    assert min(x for x, _, _, _ in translated_rectangles) >= 5000.0
    assert min(y for _, y, _, _ in translated_rectangles) >= 2500.0
    assert {text.split()[1] for text in _texts("piezas_ids_trasladados.dxf") if text.startswith("PART ")} == {
        "R7",
        "R8",
        "R9",
    }
    assert sorted((width, height) for _, _, width, height in variant_rectangles) != base_sizes
    assert Counter((width, height) for _, _, width, height in thick_rectangles) == {
        (1200.0, 300.0): 1,
        (1200.0, 36.0): 1,
        (864.0, 300.0): 2,
        (864.0, 36.0): 2,
        (36.0, 300.0): 3,
    }


def test_ambiguous_fixture_has_no_grouping_key_and_loose_qty_is_not_associated() -> None:
    texts = _texts("piezas_ambigua_sin_id.dxf")

    assert {"FRONT", "TOP", "SIDE", "QTY 2"} <= set(texts)
    assert all(not text.startswith("PART ") for text in texts)
    assert all(len(text.split()) != 3 for text in texts if text.startswith("QTY"))
    assert len(_rectangles("piezas_ambigua_sin_id.dxf")) == 3


def test_parts_manifest_is_public_and_contains_no_private_construction() -> None:
    manifest = json.loads(
        (PUBLIC_DIR / "piezas_manifest.json").read_text(encoding="utf-8")
    )
    serialized = json.dumps(manifest, ensure_ascii=False).casefold()

    assert manifest["input_contract"]["semantics"] == "separate_local_part_views"
    assert set(manifest["cases"]) == set(PUBLIC_CASES)
    assert all(
        token not in serialized
        for token in ("role", "assembly", "montaje", "bom", "side_panel", "shelf")
    )


def test_parts_fixture_generation_is_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    command = [sys.executable, "-m", "tools.build_parts_fixture"]

    subprocess.run(command + ["--output-dir", str(first)], cwd=ROOT, check=True)
    subprocess.run(command + ["--output-dir", str(second)], cwd=ROOT, check=True)

    for filename in (*PUBLIC_CASES, "piezas_manifest.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_private_reference_is_separate_and_read_only_after_public_output_is_frozen() -> None:
    frozen_public = {
        filename: (PUBLIC_DIR / filename).read_bytes() for filename in PUBLIC_CASES
    }
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))

    assert reference["evaluation_policy"]["runtime_must_not_read_this_file"] is True
    assert reference["evaluation_policy"]["compare_only_after_outputs_are_frozen"] is True
    assert reference["reviewed_reference"]["assembly_hypothesis"] == "between_sides"
    assert sum(item["quantity"] for item in reference["reviewed_reference"]["pieces"]) == 6
    assert frozen_public == {
        filename: (PUBLIC_DIR / filename).read_bytes() for filename in PUBLIC_CASES
    }
