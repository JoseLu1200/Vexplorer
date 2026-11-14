import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import ezdxf
import pytest

from tools.prepare_semantic_corpus import _write_dxf, prepare_semantic_corpus
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


def _tree_digest(root: Path) -> str:
    # Compare every payload byte, independently of the host's zlib encoder.
    entries = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        name = path.relative_to(root).as_posix()
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                for member in sorted(archive.namelist()):
                    entries[f"{name}/{member}"] = hashlib.sha256(archive.read(member)).hexdigest()
        else:
            entries[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    # The checksum index contains compressed ZIP hashes; validate it separately.
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    lines = "".join(f"{name}={digest}\n" for name, digest in sorted(entries.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


def test_generates_50_development_and_30_structurally_held_out_cases(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"

    result = prepare_semantic_corpus(public, reference)

    assert result["case_count"] == 80
    assert result["split_counts"] == {"development": 50, "reserved": 30}
    private_manifest = _json(reference / "manifest.json")
    scenarios = _json(reference / "references.json")["scenarios"]
    assert private_manifest["certification"] == "design_known_synthetic"
    assert len(scenarios) == 80
    assert {scenario["split"] for scenario in scenarios} == {"development", "reserved"}
    assert len({scenario["project_id"] for scenario in scenarios}) == 16
    assert len({scenario["structural_signature"] for scenario in scenarios}) == 16
    assert len({scenario["product_family"] for scenario in scenarios}) >= 6

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


def test_v1_remains_available_as_a_frozen_compatibility_generation(tmp_path: Path):
    public = tmp_path / "public-v1"
    reference = tmp_path / "reference-v1"

    result = prepare_semantic_corpus(public, reference, corpus_version="v1")

    assert result["case_count"] == 18
    assert result["split_counts"] == {"development": 12, "reserved": 6}
    assert _json(public / "manifest.json")["dataset_id"] == "semantic-furniture-synthetic-v1"


def test_v1_matches_the_original_generator_payload_snapshot(tmp_path: Path):
    public = tmp_path / "public-v1"
    reference = tmp_path / "reference-v1"
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = "0"

    completed = subprocess.run(
        [
            sys.executable, "-m", "tools.prepare_semantic_corpus",
            "--corpus-version", "v1",
            "--public-output", str(public),
            "--private-output", str(reference),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    # Captured from commit 48dac99, before portability changes, with hash seed 0.
    # zlib-ng (Windows) and zlib (Linux) may encode identical ZIP payloads differently.
    assert _tree_digest(public) == "a029d807e5c0bc5b6a6e489877d23f62532836444c95dd56293032cb92dfea85"
    assert _tree_digest(reference) == "3cd1a80acda3cfdd47a9ca358bcd78cc80167571ffcd2d1a23beff4dca9e1b7c"


def test_v2_reserved_topologies_exclude_every_previously_used_v1_holdout(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
    scenarios = _json(reference / "references.json")["scenarios"]

    reserved_projects = {
        item["project_id"] for item in scenarios if item["split"] == "reserved"
    }
    assert reserved_projects == {
        "hold-v2-armchair",
        "hold-v2-bar-stool",
        "hold-v2-console-frame",
        "hold-v2-corner-workstation",
        "hold-v2-drawer-chest",
        "hold-v2-wardrobe",
    }
    assert reserved_projects.isdisjoint({
        "hold-ladder", "hold-pedestal", "hold-wall-single"
    })


def test_public_bundles_match_strict_runner_and_do_not_leak_reference(tmp_path: Path):
    public = tmp_path / "opaque-public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)

    bundles = sorted(public.glob("*.zip"))
    assert len(bundles) == 80
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
    assert len(sources) == 80
    assert all(path.suffix == ".dxf" for path in sources)


def test_private_reference_has_occurrences_connected_mounting_and_valid_alternatives(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
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
            if relation["relation"] in {"fixed_to", "hinged_to"}:
                assert relation["required"] is False
        assert ref["valid_alternatives"]
        assert all(alternative["id"] for alternative in ref["valid_alternatives"])
        assert all(
            alternative.get("components") or alternative.get("assembly_relations")
            for alternative in ref["valid_alternatives"]
        )


def test_v2_fixing_alternative_preserves_required_support_and_adds_optional_fixing(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
    scenarios = _json(reference / "references.json")["scenarios"]

    for scenario in scenarios:
        base = scenario["reference"]["assembly_relations"]
        alternative = scenario["reference"]["valid_alternatives"][0]["assembly_relations"]
        base_rows = {
            (item["subject_role"], item["relation"], item["object_role"], item["required"])
            for item in base
        }
        alternative_rows = {
            (item["subject_role"], item["relation"], item["object_role"], item["required"])
            for item in alternative
        }
        required_support = {
            row for row in base_rows if row[1] == "supported_by" and row[3] is True
        }
        added = alternative_rows - base_rows
        assert required_support <= alternative_rows
        assert len(alternative_rows) == len(base_rows) + 1
        assert len(added) == 1
        added_row = added.pop()
        assert added_row[1] == "fixed_to"
        assert added_row[3] is False


def test_design_cuboids_have_positive_dimensions_without_positive_volume_overlap(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
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
    assert len(checked_projects) == 16


def test_controlled_poor_views_are_valid_unique_dxf_without_semantic_layers(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
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
    assert all(len(profiles) == 5 for profiles in view_profiles.values())
    assert any(scenario["view_profile"].startswith("missing_") for scenario in scenarios)


def test_v2_orthographic_view_layer_bounding_boxes_never_overlap(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)

    for bundle in sorted(public.glob("*.zip")):
        extracted = tmp_path / f"bbox-{bundle.stem}.dxf"
        with zipfile.ZipFile(bundle) as archive:
            extracted.write_bytes(archive.read("input.dxf"))
        document = ezdxf.readfile(extracted)
        boxes = []
        for layer in ("V0", "V1", "V2"):
            lines = [line for line in document.modelspace().query("LINE") if line.dxf.layer == layer]
            if not lines:
                continue
            points = [point for line in lines for point in (line.dxf.start, line.dxf.end)]
            boxes.append((layer, min(point.x for point in points), max(point.x for point in points)))
        for index, (left_layer, _, left_max) in enumerate(boxes):
            for right_layer, right_min, _ in boxes[index + 1:]:
                assert right_min - left_max >= 100.0, (
                    bundle.stem, left_layer, right_layer
                )


def test_v2_rectangular_800_by_320_fixture_keeps_side_view_after_top_view(tmp_path: Path):
    design = {
        "occurrences": ({
            "occurrence_id": "o1",
            "role": "rectangular_body",
            "bounds_mm": [0, 0, 0, 800, 320, 900],
        },),
    }
    target = tmp_path / "rectangular-v2.dxf"

    _write_dxf(target, design, "full_three_view", separate_views=True)

    document = ezdxf.readfile(target)
    boxes = {}
    for layer in ("V0", "V1", "V2"):
        lines = [line for line in document.modelspace().query("LINE") if line.dxf.layer == layer]
        points = [point for line in lines for point in (line.dxf.start, line.dxf.end)]
        boxes[layer] = (min(point.x for point in points), max(point.x for point in points))
    assert boxes == {"V0": (0.0, 800.0), "V1": (900.0, 1700.0), "V2": (1800.0, 2120.0)}


def test_private_annotations_express_difficulty_unknowns_and_projection_limits(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
    scenarios = _json(reference / "references.json")["scenarios"]

    assert {item["design_geometry"]["evaluation_annotations"]["difficulty"] for item in scenarios} == {
        "easy", "medium", "hard"
    }
    for scenario in scenarios:
        annotations = scenario["design_geometry"]["evaluation_annotations"]
        assert annotations["expected_unknowns"]
        assert "assembly_joint_method" in annotations["expected_unknowns"]
        assert annotations["evidence_scope"] == "orthographic_outlines_only"
        ambiguous_scopes = {item["scope"] for item in scenario["reference"]["ambiguity"]}
        for relation in scenario["reference"]["assembly_relations"]:
            if relation["relation"] in {"fixed_to", "hinged_to"}:
                pair = f"assembly_relation:{relation['subject_role']}:{relation['object_role']}"
                assert pair in ambiguous_scopes


def test_development_and_reserved_have_disjoint_normalized_visible_signatures(tmp_path: Path):
    public = tmp_path / "public"
    reference = tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
    scenarios = _json(reference / "references.json")["scenarios"]

    signatures: dict[str, set[str]] = {"development": set(), "reserved": set()}
    for scenario in scenarios:
        if scenario["view_profile"] != "full_three_view":
            continue
        bundle = public / f"{scenario['scenario_id']}.zip"
        extracted = tmp_path / f"visible-{scenario['scenario_id']}.dxf"
        with zipfile.ZipFile(bundle) as archive:
            extracted.write_bytes(archive.read("input.dxf"))
        document = ezdxf.readfile(extracted)
        normalized_layers = []
        for layer in ("V0", "V1", "V2"):
            lines = [line for line in document.modelspace().query("LINE") if line.dxf.layer == layer]
            points = [point for line in lines for point in (line.dxf.start, line.dxf.end)]
            xmin = min(point.x for point in points)
            ymin = min(point.y for point in points)
            scale = max(
                max(point.x for point in points) - xmin,
                max(point.y for point in points) - ymin,
            )
            segments = []
            for line in lines:
                ends = sorted((
                    (round((line.dxf.start.x - xmin) / scale, 6), round((line.dxf.start.y - ymin) / scale, 6)),
                    (round((line.dxf.end.x - xmin) / scale, 6), round((line.dxf.end.y - ymin) / scale, 6)),
                ))
                segments.append(ends)
            normalized_layers.append(sorted(segments))
        signature = hashlib.sha256(
            json.dumps(normalized_layers, separators=(",", ":")).encode()
        ).hexdigest()
        signatures[scenario["split"]].add(signature)

    assert len(signatures["development"]) == 10
    assert len(signatures["reserved"]) == 6
    assert signatures["development"].isdisjoint(signatures["reserved"])


def test_generation_is_reproducible_atomic_and_rejects_overlapping_destinations(tmp_path: Path):
    public_a, reference_a = tmp_path / "public-a", tmp_path / "reference-a"
    public_b, reference_b = tmp_path / "public-b", tmp_path / "reference-b"
    prepare_semantic_corpus(public_a, reference_a)
    prepare_semantic_corpus(public_b, reference_b)
    assert _tree_hash(public_a) == _tree_hash(public_b)
    assert _tree_hash(reference_a) == _tree_hash(reference_b)

    with pytest.raises(ValueError, match="separate"):
        prepare_semantic_corpus(tmp_path / "same", tmp_path / "same")
    with pytest.raises(ValueError, match="exists"):
        prepare_semantic_corpus(public_a, tmp_path / "unused-reference")


def test_v2_generation_is_byte_reproducible_across_python_hash_seeds(tmp_path: Path):
    outputs = []
    for seed in (1, 4):
        public = tmp_path / f"public-seed-{seed}"
        reference = tmp_path / f"reference-seed-{seed}"
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = str(seed)
        completed = subprocess.run(
            [
                sys.executable, "-m", "tools.prepare_semantic_corpus",
                "--public-output", str(public),
                "--private-output", str(reference),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert completed.returncode == 0, completed.stderr
        outputs.append((_tree_hash(public), _tree_hash(reference)))

    assert outputs[0] == outputs[1]


def test_seals_private_evaluation_envelope_only_against_frozen_complete_predictions(tmp_path: Path):
    public, reference = tmp_path / "public", tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
    reference_scenarios = _json(reference / "references.json")["scenarios"]
    scenario_ids = [item["scenario_id"] for item in reference_scenarios]
    input_hashes = {item["scenario_id"]: item["input_sha256"] for item in reference_scenarios}
    predictions = tmp_path / "frozen-predictions.json"
    selected_ids = scenario_ids[-6:]
    prediction_payload = {
        "schema_version": "semantic-evaluation/v1",
        "dataset_id": "semantic-furniture-synthetic-v2",
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
        "id": "semantic-furniture-synthetic-v2",
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


def test_prepare_cli_delegates_subset_sealing_to_the_canonical_sealer(tmp_path: Path):
    public, reference = tmp_path / "public", tmp_path / "reference"
    prepare_semantic_corpus(public, reference)
    scenario = _json(reference / "references.json")["scenarios"][0]
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps({
        "schema_version": "semantic-evaluation/v1",
        "dataset_id": "semantic-furniture-synthetic-v2",
        "cases": [{
            "scenario_id": scenario["scenario_id"],
            "input_sha256": scenario["input_sha256"],
            "prediction": {"components": [], "assembly_relations": [], "unknowns": []},
        }],
    }), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable, "-m", "tools.prepare_semantic_corpus",
            "--private-output", str(reference),
            "--seal-predictions", str(predictions),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    target = Path(json.loads(completed.stdout)["sealed_reference"])
    assert target.name.startswith("evaluation-reference-")
    assert [item["scenario_id"] for item in _json(target)["cases"]] == [
        scenario["scenario_id"]
    ]
