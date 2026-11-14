import hashlib
import json
from pathlib import Path
import zipfile

import ezdxf
import pytest

from tools.audit_semantic_oracle_absence import audit_oracle_absence
from tools.prepare_semantic_corpus import prepare_semantic_corpus
from tools.seal_semantic_reference import seal_semantic_reference
from tools.run_general_benchmark import PUBLIC_METADATA_KEYS, load_public_sources


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _tree_hash(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _developer_private_spec(root: Path) -> Path:
    path = root / "developer-private-designs.json"
    if path.exists():
        return path
    designs = []
    for index, family in enumerate(("shelving", "table", "cabinetry"), 1):
        offset = index * 100
        designs.append({
            "project_id": f"test-private-project-{index}",
            "product_family": family,
            "split": "reserved",
            "variants": ["missing_side", "missing_top"],
            "occurrences": [
                {"occurrence_id": "a", "role": f"test_primary_{index}", "bounds_mm": [0, 0, 0, 40 + offset, 30, 20]},
                {"occurrence_id": "b", "role": f"test_support_{index}", "bounds_mm": [0, 0, 20, 40 + offset, 30, 40]},
            ],
            "relations": [[f"test_primary_{index}", "supported_by", f"test_support_{index}"]],
            "alternative_relation": [f"test_primary_{index}", "fixed_to", f"test_support_{index}"],
        })
    path.write_text(json.dumps({"schema_version": "semantic-private-design/v1", "designs": designs}))
    return path


def _prepare(public: Path, reference: Path):
    return prepare_semantic_corpus(
        public,
        reference,
        private_design_spec=_developer_private_spec(public.parent),
    )


def test_generates_12_development_and_6_structurally_held_out_cases(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"

    result = _prepare(public, reference)

    assert result["case_count"] == 18
    assert result["split_counts"] == {"development": 12, "reserved": 6}
    private_manifest = _json(reference / "manifest.json")
    scenarios = _json(reference / "references.json")["scenarios"]
    assert private_manifest["certification"] == "design_known_synthetic"
    assert len(scenarios) == 18
    assert {scenario["split"] for scenario in scenarios} == {"development", "reserved"}
    assert len({scenario["project_id"] for scenario in scenarios}) == 6
    assert len({scenario["product_family"] for scenario in scenarios}) == 3

    by_project: dict[str, set[str]] = {}
    by_structure: dict[str, set[str]] = {}
    for scenario in scenarios:
        by_project.setdefault(scenario["project_id"], set()).add(scenario["split"])
        by_structure.setdefault(scenario["structural_signature"], set()).add(scenario["split"])
    assert all(len(splits) == 1 for splits in by_project.values())
    assert all(len(splits) == 1 for splits in by_structure.values())
    development = {
        item["structural_signature"] for item in scenarios if item["split"] == "development"
    }
    reserved = {
        item["structural_signature"] for item in scenarios if item["split"] == "reserved"
    }
    assert development.isdisjoint(reserved)


def test_public_bundles_match_strict_runner_and_do_not_leak_reference(tmp_path: Path):
    public = tmp_path / "opaque-public"
    reference = tmp_path / "reference"
    _prepare(public, reference)

    bundles = sorted(public.glob("*.zip"))
    assert len(bundles) == 18
    forbidden = {
        "reserved", "development", "shelf", "cabinet", "door",
        "back_panel", "bottom_panel", "table_leg", "mount", "alternative",
    }
    for bundle in bundles:
        with zipfile.ZipFile(bundle) as archive:
            assert set(archive.namelist()) == {"input.dxf", "case.json"}
            assert archive.testzip() is None
            metadata = json.loads(archive.read("case.json"))
            assert set(metadata) == PUBLIC_METADATA_KEYS
            assert metadata["id"] == bundle.stem
            assert metadata["file"] == "input.dxf"
            assert metadata["format"] == "dxf"
            assert metadata["unit"] == "mm"
            raw = archive.read("input.dxf")
            assert hashlib.sha256(raw).hexdigest() == metadata["sha256"]
            lowered = (archive.read("case.json") + raw).decode("utf-8", errors="ignore").lower()
            assert not any(token in lowered for token in forbidden)

    staging = tmp_path / "strict-staging"
    sources = load_public_sources(public, staging, strict_bundles=True)
    assert len(sources) == 18
    assert all(path.suffix == ".dxf" for path in sources)


def test_private_reference_has_occurrences_connected_mounting_and_valid_alternatives(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    _prepare(public, reference)
    scenarios = _json(reference / "references.json")["scenarios"]

    for scenario in scenarios:
        ref = scenario["reference"]
        assert ref["certification"] == "design_known_synthetic"
        roles = {component["role"] for component in ref["components"]}
        assert sum(component["quantity"] for component in ref["components"]) == len(
            scenario["design_geometry"]["occurrences"]
        )
        assert roles == {item["role"] for item in scenario["design_geometry"]["occurrences"]}
        assert ref["assembly_relations"]
        for relation in ref["assembly_relations"]:
            assert relation["subject_role"] in roles
            assert relation["object_role"] in roles
            assert relation["relation"] in {"fixed_to", "supported_by", "hinged_to"}
        assert ref["valid_alternatives"]
        assert all(alternative["id"] for alternative in ref["valid_alternatives"])
        assert all(
            alternative.get("components") or alternative.get("assembly_relations")
            for alternative in ref["valid_alternatives"]
        )


def test_design_cuboids_have_positive_dimensions_without_positive_volume_overlap(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    _prepare(public, reference)
    scenarios = _json(reference / "references.json")["scenarios"]

    checked_projects = set()
    for scenario in scenarios:
        if scenario["project_id"] in checked_projects:
            continue
        checked_projects.add(scenario["project_id"])
        occurrences = scenario["design_geometry"]["occurrences"]
        for index, first in enumerate(occurrences):
            a = first["bounds_mm"]
            assert all(a[axis] < a[axis + 3] for axis in range(3))
            for second in occurrences[index + 1:]:
                b = second["bounds_mm"]
                positive_overlap = all(
                    min(a[axis + 3], b[axis + 3]) > max(a[axis], b[axis])
                    for axis in range(3)
                )
                assert not positive_overlap, (
                    scenario["project_id"], first["occurrence_id"], second["occurrence_id"]
                )
    assert len(checked_projects) == 6


def test_controlled_poor_views_are_valid_unique_dxf_without_semantic_layers(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    _prepare(public, reference)
    scenarios = _json(reference / "references.json")["scenarios"]

    view_profiles: dict[str, set[str]] = {}
    hashes = set()
    for scenario in scenarios:
        view_profiles.setdefault(scenario["project_id"], set()).add(scenario["view_profile"])
        bundle = public / f"{scenario['scenario_id']}.zip"
        with zipfile.ZipFile(bundle) as archive:
            raw = archive.read("input.dxf")
        digest = hashlib.sha256(raw).hexdigest()
        assert digest not in hashes
        hashes.add(digest)
        extracted = tmp_path / f"{scenario['scenario_id']}.dxf"
        extracted.write_bytes(raw)
        document = ezdxf.readfile(extracted)
        assert document.units == ezdxf.units.MM
        assert len(document.modelspace().query("LINE")) >= 8
        assert len(document.modelspace().query("TEXT MTEXT INSERT")) == 0
        custom_layers = {
            layer.dxf.name for layer in document.layers
            if layer.dxf.name not in {"0", "Defpoints"}
        }
        assert custom_layers <= {"V0", "V1", "V2", "N0"}
    scenario_by_project = {scenario["project_id"]: scenario for scenario in scenarios}
    assert all(
        len(profiles) == (4 if scenario_by_project[project]["split"] == "development" else 2)
        for project, profiles in view_profiles.items()
    )
    assert any(scenario["view_profile"].startswith("missing_") for scenario in scenarios)


def test_generation_is_reproducible_atomic_and_rejects_overlapping_destinations(tmp_path: Path):
    public_a, reference_a = tmp_path / "public-a", tmp_path / "reference-a"
    public_b, reference_b = tmp_path / "public-b", tmp_path / "reference-b"
    _prepare(public_a, reference_a)
    _prepare(public_b, reference_b)
    assert _tree_hash(public_a) == _tree_hash(public_b)
    assert _tree_hash(reference_a) == _tree_hash(reference_b)

    with pytest.raises(ValueError, match="separate"):
        _prepare(tmp_path / "same", tmp_path / "same")
    with pytest.raises(ValueError, match="exists"):
        _prepare(public_a, tmp_path / "unused-reference")


def test_seals_private_evaluation_envelope_only_against_frozen_complete_predictions(tmp_path: Path):
    public, reference = tmp_path / "public", tmp_path / "reference"
    _prepare(public, reference)
    reference_scenarios = _json(reference / "references.json")["scenarios"]
    scenario_ids = [item["scenario_id"] for item in reference_scenarios]
    input_hashes = {item["scenario_id"]: item["input_sha256"] for item in reference_scenarios}
    predictions = tmp_path / "frozen-predictions.json"
    selected_ids = scenario_ids[-6:]
    prediction_payload = {
        "schema_version": "semantic-evaluation/v1",
        "dataset_id": "semantic-furniture-synthetic-v1",
        "cases": [
            {
                "scenario_id": scenario_id,
                "input_sha256": input_hashes[scenario_id],
                "prediction": {"components": [], "assembly_relations": [], "unknowns": []},
            }
            for scenario_id in selected_ids
        ],
    }
    predictions.write_text(
        json.dumps(prediction_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    sealed = seal_semantic_reference(reference, predictions)

    envelope = _json(sealed)
    assert sealed.parent == reference
    assert sealed.name.startswith("evaluation-reference-")
    assert envelope["schema_version"] == "semantic-evaluation/v1"
    assert envelope["dataset"] == {
        "id": "semantic-furniture-synthetic-v1",
        "predictions_sha256": hashlib.sha256(predictions.read_bytes()).hexdigest(),
        "frozen_before_evaluation": True,
        "partition_policy": "project_and_family",
        "partition_unit": "project_id+structural_signature",
        "reference_visibility": "evaluator_only",
    }
    assert [item["scenario_id"] for item in envelope["cases"]] == selected_ids
    with pytest.raises(ValueError, match="already sealed"):
        seal_semantic_reference(reference, predictions)

    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps({
        **prediction_payload,
        "cases": [{
            "scenario_id": scenario_ids[0],
            "input_sha256": input_hashes[scenario_ids[0]],
            "prediction": {"components": [], "assembly_relations": [], "unknowns": []},
        }],
    }))
    smoke_seal = seal_semantic_reference(reference, smoke)
    assert [item["scenario_id"] for item in _json(smoke_seal)["cases"]] == [scenario_ids[0]]

    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({
        **prediction_payload,
        "cases": [{
            "scenario_id": "sx-999",
            "input_sha256": "f" * 64,
            "prediction": {"components": [], "assembly_relations": [], "unknowns": []},
        }],
    }))
    with pytest.raises(ValueError, match="case ids"):
        seal_semantic_reference(reference, unknown)

    wrong_hash = tmp_path / "wrong-hash.json"
    wrong_hash.write_text(json.dumps({
        **prediction_payload,
        "cases": [prediction_payload["cases"][0] | {"input_sha256": "0" * 64}],
    }))
    with pytest.raises(ValueError, match="input_sha256"):
        seal_semantic_reference(reference, wrong_hash)


def test_source_oracle_audit_detects_exact_private_recipe_without_embedding_it_in_tests(tmp_path: Path):
    spec = _developer_private_spec(tmp_path)
    clean = tmp_path / "clean.py"
    clean.write_text("def render_private_spec(path): return path.read_text()\n")
    assert audit_oracle_absence(spec, (clean,))["leaks"] == 0

    payload = _json(spec)
    design = payload["designs"][0]
    leaked = tmp_path / "leaked.py"
    leaked.write_text(
        "A = " + repr(design["occurrences"][0]["bounds_mm"]) + "\n"
        "B = " + repr(design["occurrences"][1]["bounds_mm"]) + "\n"
    )
    with pytest.raises(ValueError, match="private semantic oracle leaked"):
        audit_oracle_absence(spec, (leaked,))
