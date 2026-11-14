from __future__ import annotations

import builtins
import io
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import ezdxf
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


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


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(create_app(data_dir=tmp_path))


def _start_table(
    client: TestClient, filename: str, template: str = "side_supports_v1"
) -> tuple[str, dict]:
    with (PUBLIC_DIR / filename).open("rb") as stream:
        uploaded = client.post(
            "/api/v1/documents",
            files={"file": ("source.dxf", stream, "application/dxf")},
        )
    assert uploaded.status_code == 201, uploaded.text
    response = client.post(
        "/api/v1/runs",
        json={
            "document_id": uploaded.json()["data"]["document_id"],
            "mode": "geometry_only",
            "input_kind": "mounted_orthographic_views",
            "table_profile": "rectangular_table_v1",
            "proposal_mode": "catalog_baseline",
            "table_template_id": template,
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    return payload["run"]["id"], payload["result"]


def _accept_all(program: dict) -> list[dict]:
    return [
        {
            "target_kind": "program",
            "target_id": program["id"],
            "action": "accept",
            "reason": "Selección explícita de la hipótesis para evaluación",
        },
        *(
            {
                "target_kind": "component",
                "target_id": item["id"],
                "action": "accept",
                "reason": "Componente aceptado por la persona revisora",
            }
            for item in program["components"]
        ),
        *(
            {
                "target_kind": "premise",
                "target_id": item["id"],
                "action": "accept",
                "reason": "Premisa aceptada por la persona revisora",
            }
            for item in program["premises"]
        ),
    ]


def _review_table(client: TestClient, run_id: str, program: dict) -> dict:
    response = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Evaluación independiente de mesa",
            "table_program_id": program["id"],
            "table_decisions": _accept_all(program),
            "notes": "Aceptación versionada; no certifica fabricación",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


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


def test_table_http_audit_cli_is_public_only() -> None:
    source_path = ROOT / "tools" / "audit_table.py"
    assert source_path.is_file()
    source = source_path.read_text(encoding="utf-8").casefold()
    assert "mesa_reference" not in source
    assert "evaluation/reference" not in source
    result = subprocess.run(
        [sys.executable, str(source_path), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--base-url" in result.stdout
    assert "--output" in result.stdout


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


def test_table_pipeline_freezes_public_outputs_before_private_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    frozen: dict
    with _deny_table_reference_reads():
        run_id, initial = _start_table(client, "mesa_demo_001.dxf")
        snapshot_response = client.get(
            f"/api/v1/runs/{run_id}/table", params={"result_revision": 1}
        )
        assert snapshot_response.status_code == 200, snapshot_response.text
        snapshot = snapshot_response.json()["data"]
        measures = {
            item["semantic"]: item
            for item in snapshot["table_analysis"]["measures"]
            if item["semantic"] in {"overall_width", "overall_height", "overall_depth"}
        }
        assert {
            key: (item["state"], item["value_mm"])
            for key, item in measures.items()
        } == {
            "overall_width": ("observed", 1200.0),
            "overall_height": ("observed", 750.0),
            "overall_depth": ("observed", 700.0),
        }
        assert all(
            item["measurement_ids"] and item["view_ids"] and item["evidence_ids"]
            for item in measures.values()
        )
        assert initial["state"] == "needs_review"
        assert len(snapshot["table_programs"]) == 1
        program = snapshot["table_programs"][0]
        assert program["proposal_origin"] == "catalog_baseline"
        assert program["table_template_id"] == "side_supports_v1"
        assert all(
            set(binding) == {"id", "operation", "operand_refs"}
            and all(set(ref) == {"ref_type", "ref_id"} for ref in binding["operand_refs"])
            for binding in program["bindings"]
        )
        assert len(snapshot["evaluated_table_program"]["occurrences"]) == 3

        reviewed = _review_table(client, run_id, program)
        evaluated = reviewed["evaluated_table_program"]
        assert reviewed["state"] == "completed"
        assert evaluated["state"] == "completed"
        assert evaluated["overall_dimensions"] == {
            "width_mm": 1200.0,
            "depth_mm": 700.0,
            "height_mm": 750.0,
        }
        assert len(evaluated["occurrences"]) == 3

        scene_response = client.get(
            f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2}
        )
        assert scene_response.status_code == 200, scene_response.text
        scene = scene_response.json()["data"]
        assert scene["state"] == "ready"
        assert len(scene["objects"]) == 3

        drawings_response = client.post(
            f"/api/v1/runs/{run_id}/table-drawings", json={"result_revision": 2}
        )
        assert drawings_response.status_code == 201, drawings_response.text
        drawings = drawings_response.json()["data"]
        assert drawings["result_revision"] == 2
        assert drawings["program_hash"] == evaluated["program_hash"]
        assert {sheet["kind"] for sheet in drawings["sheets"]} == {
            "general",
            "component",
            "cut_sheet",
        }
        assert all(sheet["status"] == "ready" for sheet in drawings["sheets"])
        for sheet in drawings["sheets"]:
            assert {item["format"] for item in sheet["formats"]} == {"svg", "dxf"}
            for artifact_link in sheet["formats"]:
                artifact = client.get(artifact_link["url"])
                assert artifact.status_code == 200, artifact.text
                assert artifact.headers["content-type"].split(";")[0] == artifact_link["media_type"]
                if artifact_link["format"] == "svg":
                    assert "<svg" in artifact.text and "data-state=" in artifact.text
                else:
                    derived = ezdxf.read(io.StringIO(artifact.text))
                    assert derived.header["$INSUNITS"] == 4
                    assert len(derived.modelspace()) > 0

        cost_response = client.post(
            f"/api/v1/runs/{run_id}/table-costs",
            json={
                "result_revision": 2,
                "scope": {
                    "material_tariff_id": "demo_board_area_v1",
                    "edge_scope": "none",
                    "operation_tariff_ids": [],
                },
            },
        )
        assert cost_response.status_code == 201, cost_response.text
        cost = cost_response.json()["data"]
        concepts = {item["id"]: item for item in cost["concepts"]}
        assert concepts["fixed:preparation"]["amount_eur"] == 25.0
        assert concepts["fixed:preparation"]["quantity"] == 1.0
        assert concepts["material:component-tabletop"]["quantity"] == 0.84
        assert concepts["material:component-tabletop"]["amount_eur"] == 35.28
        assert concepts["material:component-side-support"]["quantity"] == 1.008
        assert concepts["material:component-side-support"]["amount_eur"] == 42.34
        assert len(concepts["material:component-side-support"]["occurrence_ids"]) == 2
        assert cost["known_subtotal_eur"] == 102.62
        assert cost["total_state"] == "partial" and cost["grand_total_eur"] is None

        exported = client.get(
            f"/api/v1/runs/{run_id}/exports", params={"format": "json"}
        )
        assert exported.status_code == 200, exported.text
        bundle = exported.json()
        assert bundle["schema_version"] == "0.5.0"
        assert bundle["table_drawings"] == drawings
        assert bundle["estimate"] == cost
        assert bundle["scene"] == scene
        assert bundle["descriptor"]["descriptor_version"] == "furniture-v3"

        # Freeze a JSON-only copy before evaluator-only data is opened below.
        frozen = json.loads(
            json.dumps(
                {
                    "components": evaluated["components"],
                    "program_hash": evaluated["program_hash"],
                    "drawings": drawings,
                    "cost": cost,
                }
            )
        )

    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    expected = sorted(
        reference["cases"]["mesa_demo_001.dxf"]["reviewed_components"],
        key=lambda item: item["role"],
    )
    observed = sorted(
        (
            {
                "role": item["role"],
                "quantity": item["quantity"],
                "length_mm": item["length"]["value_mm"],
                "width_mm": item["width"]["value_mm"],
                "thickness_mm": item["thickness"]["value_mm"],
            }
            for item in frozen["components"]
        ),
        key=lambda item: item["role"],
    )
    assert observed == expected


def test_table_catalog_templates_change_physical_count_without_claiming_observed_bom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    with _deny_table_reference_reads():
        side_run, side_result = _start_table(
            client, "mesa_demo_001.dxf", "side_supports_v1"
        )
        corner_run, corner_result = _start_table(
            client, "mesa_demo_001.dxf", "corner_supports_v1"
        )
        assert side_run != corner_run
        side_program = side_result["table_programs"][0]
        corner_program = corner_result["table_programs"][0]
        assert side_program["proposal_origin"] == "catalog_baseline"
        assert corner_program["proposal_origin"] == "catalog_baseline"
        assert {item["quantity_rule_id"] for item in side_program["components"]} == {
            "top_one",
            "two_side_supports",
        }
        assert {item["quantity_rule_id"] for item in corner_program["components"]} == {
            "top_one",
            "four_corner_supports",
        }
        assert len(side_result["evaluated_table_program"]["occurrences"]) == 3
        assert len(corner_result["evaluated_table_program"]["occurrences"]) == 5
        assert side_result["state"] == corner_result["state"] == "needs_review"
        assert side_result["evaluated_table_program"]["state"] == "hypothesis"
        assert corner_result["evaluated_table_program"]["state"] == "hypothesis"


def test_table_variants_preserve_dimensions_missing_view_and_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    with _deny_table_reference_reads():
        _, dimensional = _start_table(client, "mesa_demo_002.dxf")
        assert dimensional["evaluated_table_program"]["overall_dimensions"] == {
            "width_mm": 1400.0,
            "depth_mm": 800.0,
            "height_mm": 760.0,
        }

        incomplete_run, incomplete = _start_table(client, "mesa_demo_003.dxf")
        assert "missing_required_view:SIDE" in incomplete["table_analysis"]["warnings"]
        incomplete_program = incomplete["table_programs"][0]
        incomplete_review = _review_table(client, incomplete_run, incomplete_program)
        assert incomplete_review["state"] == "needs_review"
        assert any(
            item["code"] == "missing_required_view"
            and item["severity"] == "error"
            for item in incomplete_review["evaluated_table_program"]["issues"]
        )
        incomplete_scene = client.get(
            f"/api/v1/runs/{incomplete_run}/scene", params={"result_revision": 2}
        ).json()["data"]
        assert incomplete_scene["state"] == "incomplete"
        assert incomplete_scene["objects"] == []
        incomplete_drawings = client.post(
            f"/api/v1/runs/{incomplete_run}/table-drawings",
            json={"result_revision": 2},
        )
        assert incomplete_drawings.status_code == 201, incomplete_drawings.text
        incomplete_sheets = incomplete_drawings.json()["data"]["sheets"]
        assert any(sheet["status"] == "incomplete" for sheet in incomplete_sheets)

        _, conflict = _start_table(client, "mesa_demo_004.dxf")
        width = next(
            item
            for item in conflict["table_analysis"]["measures"]
            if item["semantic"] == "overall_width"
        )
        assert width["state"] == "conflict" and width["value_mm"] is None
        assert len(width["evidence_ids"]) >= 2
        assert "table_measure_conflict" in conflict["table_analysis"]["warnings"]
