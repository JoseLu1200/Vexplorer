from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import ezdxf
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


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


def _is_private_path(value: object) -> bool:
    try:
        candidate = Path(os.fspath(value)).resolve()
    except (TypeError, ValueError, OSError):
        return False
    private_dir = REFERENCE_PATH.parent.resolve()
    return candidate == private_dir or private_dir in candidate.parents


@contextmanager
def _deny_runtime_reference_reads():
    original_builtin_open = builtins.open
    original_path_open = Path.open

    def guarded_open(file, *args, **kwargs):
        assert not _is_private_path(file), f"runtime attempted private read: {file}"
        return original_builtin_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args, **kwargs):
        assert not _is_private_path(path), f"runtime attempted private read: {path}"
        return original_path_open(path, *args, **kwargs)

    with patch("builtins.open", guarded_open), patch.object(Path, "open", guarded_path_open):
        yield


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(create_app(data_dir=tmp_path))


def _upload(client: TestClient, filename: str) -> str:
    with (PUBLIC_DIR / filename).open("rb") as stream:
        response = client.post(
            "/api/v1/documents",
            files={"file": (filename, stream, "application/dxf")},
        )
    assert response.status_code == 201, response.text
    return response.json()["data"]["document_id"]


def _start_parts(client: TestClient, document_id: str) -> tuple[str, dict]:
    response = client.post(
        "/api/v1/runs",
        json={
            "document_id": document_id,
            "mode": "geometry_only",
            "input_kind": "separated_part_views",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    return payload["run"]["id"], payload["result"]


def _parts(client: TestClient, run_id: str, revision: int = 1) -> dict:
    response = client.get(
        f"/api/v1/runs/{run_id}/parts", params={"result_revision": revision}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _candidate_for_public_premises(snapshot: dict) -> dict:
    observations = {
        item["part_key"]: item["id"] for item in snapshot["part_analysis"]["observations"]
    }
    for candidate in snapshot["assembly_candidates"]:
        roles = {item["part_observation_id"]: item["role"] for item in candidate["uses"]}
        if (
            candidate["layout"] == "between_sides"
            and roles.get(observations["K1"]) == "side_panel"
            and roles.get(observations["K2"]) in {"top_panel", "base_panel"}
            and roles.get(observations["K3"]) == "shelf"
        ):
            return candidate
    raise AssertionError("no candidate matches the public audit premises")


def _review_candidate(client: TestClient, run_id: str, candidate_id: str) -> dict:
    response = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Evaluación parts-only",
            "assembly_candidate_id": candidate_id,
            "material": "tablero sintético",
            "finish": "melamina sintética",
            "notes": "Selección controlada de hipótesis para aceptación independiente",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


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
    assert {item["purpose"] for item in manifest["cases"].values()} == {
        "separate_part_views_development_case"
    }
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


def test_parts_api_exposes_only_keyed_local_observations_and_hypotheses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        document_id = _upload(client, "piezas_completo.dxf")
        run_id, result = _start_parts(client, document_id)
        snapshot = _parts(client, run_id)

    assert result["input_semantics"] == "separated_part_views"
    assert result["part_analysis"] == snapshot["part_analysis"]
    assert result["assembly_candidates"] == snapshot["assembly_candidates"]
    assert snapshot["selected_assembly_candidate_id"] is None
    analysis = snapshot["part_analysis"]
    assert analysis["schema_version"] == "0.4.0"
    assert analysis["input_kind"] == "separated_part_views"

    observations = {item["part_key"]: item for item in analysis["observations"]}
    assert set(observations) == {"K1", "K2", "K3"}
    expected_dimensions = {
        "K1": (1200.0, 300.0, 18.0),
        "K2": (864.0, 300.0, 18.0),
        "K3": (864.0, 300.0, 18.0),
    }
    for key, observation in observations.items():
        assert observation["association_basis"] == "explicit_key"
        assert observation["status"] == "complete"
        assert {view["role"] for view in observation["views"]} == {"FRONT", "TOP", "SIDE"}
        assert len(observation["views"]) == 3
        assert observation["quantity"]["value"] == 2
        assert observation["quantity"]["state"] == "observed"
        assert observation["quantity"]["value"] != len(observation["views"])
        values = tuple(
            observation["dimensions"][axis]["value_mm"]
            for axis in ("length", "width", "thickness")
        )
        assert values == expected_dimensions[key]
        assert all(
            observation["dimensions"][axis]["state"] == "observed"
            and observation["dimensions"][axis]["view_ids"]
            and observation["dimensions"][axis]["evidence_ids"]
            for axis in ("length", "width", "thickness")
        )
        assert observation["source_entity_ids"]
        assert observation["evidence_ids"]
        assert all(view["contour_ids"] for view in observation["views"])

    observation_ids = {item["id"] for item in observations.values()}
    assert len(snapshot["assembly_candidates"]) >= 2
    assert {item["layout"] for item in snapshot["assembly_candidates"]} >= {
        "between_sides",
        "cap_sides",
    }
    for candidate in snapshot["assembly_candidates"]:
        used = {item["part_observation_id"] for item in candidate["uses"]}
        unassigned = set(candidate["unassigned_part_observation_ids"])
        assert used.isdisjoint(unassigned)
        assert used | unassigned == observation_ids
        assert candidate["state"] == "hypothesis"
        assert candidate["needs_review"] is True
        assert candidate["family_status"] == "hypothesis"
        assert candidate["layout_status"] == "hypothesis"
        assert all(item["role_status"] == "hypothesis" for item in candidate["uses"])


def test_unknown_and_unkeyed_parts_stay_unknown_and_do_not_create_solids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        cases = {}
        for key, filename in {
            "qty": "piezas_qty_desconocida.dxf",
            "thickness": "piezas_espesor_desconocido.dxf",
        }.items():
            document_id = _upload(client, filename)
            run_id, _ = _start_parts(client, document_id)
            revision_one = _parts(client, run_id)
            candidate = _candidate_for_public_premises(revision_one)
            reviewed = _review_candidate(client, run_id, candidate["id"])
            revision_two = _parts(client, run_id, 2)
            scene_response = client.get(
                f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2}
            )
            assert scene_response.status_code == 200, scene_response.text
            cases[key] = (revision_one, reviewed, revision_two, scene_response.json()["data"])

        ambiguous_id = _upload(client, "piezas_ambigua_sin_id.dxf")
        ambiguous_run_id, _ = _start_parts(client, ambiguous_id)
        ambiguous = _parts(client, ambiguous_run_id)

    qty_initial, qty_reviewed, qty_latest, qty_scene = cases["qty"]
    qty_observation = next(
        item for item in qty_initial["part_analysis"]["observations"] if item["part_key"] == "K3"
    )
    assert qty_observation["quantity"] == {
        "value": None,
        "state": "unknown",
        "evidence_ids": [],
    }
    assert qty_reviewed["state"] == "needs_review"
    assert qty_latest["selected_assembly_candidate_id"] is not None
    assert qty_scene["state"] == "incomplete"
    assert qty_observation["id"] not in {
        item["part_observation_id"] for item in qty_scene["objects"]
    }

    thickness_initial, thickness_reviewed, _, thickness_scene = cases["thickness"]
    thickness_observation = next(
        item
        for item in thickness_initial["part_analysis"]["observations"]
        if item["part_key"] == "K3"
    )
    assert thickness_observation["dimensions"]["thickness"]["value_mm"] is None
    assert thickness_observation["dimensions"]["thickness"]["state"] == "unknown"
    assert thickness_reviewed["state"] == "needs_review"
    assert thickness_scene["state"] == "incomplete"
    assert thickness_observation["id"] not in {
        item["part_observation_id"] for item in thickness_scene["objects"]
    }

    ambiguous_observations = ambiguous["part_analysis"]["observations"]
    assert len(ambiguous_observations) == 3
    assert all(item["part_key"] is None for item in ambiguous_observations)
    assert all(item["association_basis"] == "unassociated" for item in ambiguous_observations)
    assert all(item["status"] == "ambiguous" for item in ambiguous_observations)
    assert all(len(item["views"]) == 1 for item in ambiguous_observations)
    assert all(
        item["quantity"]["value"] is None and item["quantity"]["state"] == "unknown"
        for item in ambiguous_observations
    )
    assert all(
        any(warning.startswith("missing_part_key:") for warning in item["warnings"])
        for item in ambiguous_observations
    )
    assert any(
        warning.startswith("unassociated_quantity_annotation:")
        for warning in ambiguous["part_analysis"]["warnings"]
    )
    ambiguous_ids = {item["id"] for item in ambiguous_observations}
    assert all(
        not ({item["part_observation_id"] for item in candidate["uses"]} & ambiguous_ids)
        for candidate in ambiguous["assembly_candidates"]
    )


def test_parts_v2_descriptor_ignores_keys_translation_and_public_case_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filenames = {
        "base": "piezas_completo.dxf",
        "translated": "piezas_ids_trasladados.dxf",
        "dimensions": "piezas_dimensiones_variante.dxf",
        "thickness": "piezas_espesor_36.dxf",
    }
    runs: dict[str, str] = {}
    saved: dict[str, dict] = {}
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        for key, filename in filenames.items():
            document_id = _upload(client, filename)
            run_id, _ = _start_parts(client, document_id)
            response = client.post(
                f"/api/v1/runs/{run_id}/library",
                json={
                    "result_revision": 1,
                    "label": f"parts-eval-{key}",
                    "embedding_mode": "offline",
                },
            )
            assert response.status_code == 201, response.text
            runs[key] = run_id
            saved[key] = response.json()["data"]

        similarity_response = client.post(
            f"/api/v1/runs/{runs['base']}/similarity",
            json={"result_revision": 1, "mode": "geometric", "limit": 10},
        )
        groups_response = client.post(
            "/api/v1/library/groups",
            json={"mode": "geometric", "threshold": 0.999999},
        )

    base = saved["base"]
    translated = saved["translated"]
    assert base["descriptor"]["descriptor_version"] == "furniture-v2"
    assert base["descriptor"]["classification_status"] == "hypothesis"
    assert base["descriptor"] == translated["descriptor"]
    assert base["descriptor_fingerprint"] == translated["descriptor_fingerprint"]
    assert base["descriptor_fingerprint"] != saved["dimensions"]["descriptor_fingerprint"]
    assert base["descriptor_fingerprint"] != saved["thickness"]["descriptor_fingerprint"]
    assert base["descriptor"]["thicknesses_mm"] == [18.0]
    assert saved["thickness"]["descriptor"]["thicknesses_mm"] == [36.0]

    descriptor_surface = json.dumps(
        [item["descriptor"] for item in saved.values()], ensure_ascii=False
    ).casefold()
    manifest_purposes = {
        "complete_visible_evidence",
        "one_missing_qty_annotation",
        "changed_local_dimensions",
        "changed_keys_and_global_translation",
    }
    assert all(
        token not in descriptor_surface
        for token in (
            "k1",
            "k2",
            "k3",
            "r7",
            "r8",
            "r9",
            "piezas_",
            "doc-",
            "run-",
            *manifest_purposes,
        )
    )

    assert similarity_response.status_code == 200, similarity_response.text
    matches = similarity_response.json()["data"]
    translated_match = next(item for item in matches if item["run_id"] == runs["translated"])
    assert translated_match["score"] == pytest.approx(1.0)
    assert groups_response.status_code == 200, groups_response.text
    groups = groups_response.json()["data"]
    paired = next(
        item
        for item in groups
        if {base["id"], translated["id"]} <= set(item["member_ids"])
    )
    assert saved["dimensions"]["id"] not in paired["member_ids"]
    assert saved["thickness"]["id"] not in paired["member_ids"]


def test_reviewed_parts_scene_export_and_cost_use_frozen_public_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        document_id = _upload(client, "piezas_completo.dxf")
        run_id, _ = _start_parts(client, document_id)
        initial = _parts(client, run_id)
        candidate = _candidate_for_public_premises(initial)
        reviewed = _review_candidate(client, run_id, candidate["id"])
        latest = _parts(client, run_id, 2)
        revisions_response = client.get(f"/api/v1/runs/{run_id}/revisions")
        scene_response = client.get(
            f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2}
        )
        comparables_response = client.get(f"/api/v1/runs/{run_id}/comparables")
        estimate_response = client.post(
            f"/api/v1/runs/{run_id}/estimate", json={"result_revision": 2}
        )
        library_response = client.post(
            f"/api/v1/runs/{run_id}/library",
            json={
                "result_revision": 2,
                "label": "parts-eval-reviewed",
                "embedding_mode": "offline",
            },
        )
        export_response = client.get(
            f"/api/v1/runs/{run_id}/exports", params={"format": "json"}
        )

    assert reviewed["result_revision"] == 2
    assert reviewed["state"] == "completed"
    assert reviewed["selected_assembly_candidate_id"] == candidate["id"]
    assert latest["selected_assembly_candidate_id"] == candidate["id"]
    assert revisions_response.status_code == 200, revisions_response.text
    assert [item["result_revision"] for item in revisions_response.json()["data"]] == [1, 2]

    observations = {
        item["part_key"]: item for item in initial["part_analysis"]["observations"]
    }
    assert len(reviewed["pieces"]) == 3
    assert all(len(item["source_part_observation_ids"]) == 1 for item in reviewed["pieces"])
    assert {item["source_part_observation_ids"][0] for item in reviewed["pieces"]} == {
        item["id"] for item in observations.values()
    }
    assert sum(item["quantity"] for item in reviewed["pieces"]) == 6

    assert scene_response.status_code == 200, scene_response.text
    scene = scene_response.json()["data"]
    assert scene["state"] == "ready"
    assert len(scene["objects"]) == 6
    assert Counter(item["part_observation_id"] for item in scene["objects"]) == {
        observations["K1"]["id"]: 2,
        observations["K2"]["id"]: 2,
        observations["K3"]["id"]: 2,
    }
    assert all(item["placement_status"] == "human_selected" for item in scene["objects"])
    assert all(item["placement_constraint_ids"] for item in scene["objects"])

    assert comparables_response.status_code == 200, comparables_response.text
    assert all(item["synthetic"] is True for item in comparables_response.json()["data"])
    assert estimate_response.status_code == 201, estimate_response.text
    estimate = estimate_response.json()["data"]
    concept_ids = [item["id"] for item in estimate["concepts"]]
    assert concept_ids.count("setup") == 1
    assert concept_ids.count("material") == 1
    assert len(concept_ids) == len(set(concept_ids))
    assert sum(item["amount"] for item in estimate["concepts"]) == pytest.approx(estimate["total"])
    assert estimate["total"] == pytest.approx(127.84)

    assert library_response.status_code == 201, library_response.text
    library_item = library_response.json()["data"]
    assert library_item["descriptor"]["descriptor_version"] == "furniture-v2"
    assert library_item["descriptor"]["classification_status"] == "confirmed"
    assert export_response.status_code == 200, export_response.text
    frozen = json.loads(json.dumps(export_response.json(), sort_keys=True))
    assert frozen["result"] == reviewed
    assert frozen["scene"] == scene
    assert frozen["estimate"] == estimate
    assert frozen["descriptor"] == library_item["descriptor"]
    assert frozen["library_item"]["id"] == library_item["id"]

    # Solo el evaluador abre el oráculo, después de congelar todas las salidas.
    private_reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    oracle = private_reference["reviewed_reference"]
    assert oracle["economic_oracle"]["panel_area_mm2"] == 1_756_800.0
    assert oracle["economic_oracle"]["total_eur"] == estimate["total"]
    assert sum(item["quantity"] for item in oracle["pieces"]) == len(scene["objects"])
