"""Tests for the A/B/C/D comparison harness.  No paid call is ever made."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest

from evaluation.comparativa import (
    AdapterRequest,
    AdapterResponse,
    Clock,
    ComparisonError,
    DevelopmentManifestReader,
    ModelVariantsDisabled,
    PlankAssemblyManifestReader,
    PrecedentIndex,
    ReferenceNotFrozen,
    RunLimits,
    build_methods,
    execute_run,
    render_markdown,
    score_run,
    verify_freeze,
)
from evaluation.comparativa.model import (
    CaseMeta,
    Component,
    RefComponent,
    RefField,
    canonical_json,
)
from evaluation.comparativa.scoring import match_components
from tools.comparativa_metodos import main as cli_main
from tools.prepare_plankassembly import prepare_plankassembly

REPO = Path(__file__).resolve().parents[1]
SOURCE_NAME = "revealing-source-name"


def fixed_clock() -> Clock:
    ticks = iter(range(10_000))
    return Clock(perf=lambda: next(ticks) * 0.5, now_iso=lambda: "2026-01-01T00:00:00+00:00")


def _write_plank_source(root: Path) -> None:
    model_dir = root / "extracted" / "data" / "model"
    split_dir = root / "extracted" / "data" / "splits"
    model_dir.mkdir(parents=True)
    split_dir.mkdir(parents=True)
    common = {
        "planks": [
            [0, 0, 0, 1000, 500, 700],  # envelope
            [0, 0, 0, 20, 500, 700],
            [980, 0, 0, 1000, 500, 700],
            [20, 0, 680, 980, 500, 700],
        ],
        "attach": [[-1] * 6, [0, 1, 2, -1, 4, 5], [-1, -1, 2, -1, 4, 5], [9, -1, -1, 12, 4, 5]],
    }
    for name in ("a.json", "b.json"):
        (model_dir / name).write_text(json.dumps({"name": SOURCE_NAME, "id": "source-x", **common}), encoding="utf-8")
    (split_dir / "valid.txt").write_text("a.json\nb.json\n", encoding="utf-8")


@pytest.fixture()
def plank_dirs(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    _write_plank_source(source)
    public, private = tmp_path / "public", tmp_path / "private"
    prepare_plankassembly(source, public, private, split="valid", limit=2)
    return public, private


def plank_reader(tmp_path: Path, dirs: tuple[Path, Path]) -> PlankAssemblyManifestReader:
    return PlankAssemblyManifestReader(dirs[0], dirs[1], tmp_path / "staging")


def dev_reader(staging: Path | None = None, demo_dir: Path | None = None) -> DevelopmentManifestReader:
    return DevelopmentManifestReader(
        demo_dir or REPO / "data" / "planos_demo", REPO / "evaluation" / "reference",
        staging or Path(tempfile.mkdtemp(prefix="comparativa-staging-")),
    )


class SpyReader(DevelopmentManifestReader):
    private_reads = 0

    def _read_private(self):
        type(self).private_reads += 1
        return super()._read_private()


def perfect_dev_adapter(request: AdapterRequest) -> AdapterResponse:
    """Double that returns the exact piezas_completo bill of materials."""
    return AdapterResponse(
        components=[
            {"key": "x1", "dimensions_mm": {"length": 1200, "width": 300, "thickness": 18}, "quantity": 2},
            {"key": "x2", "dimensions_mm": {"length": 864, "width": 300, "thickness": 18}, "quantity": 2},
            {"key": "x3", "dimensions_mm": {"length": 864, "width": 300, "thickness": 18}, "quantity": 2},
        ],
        usage={"model_calls": 2, "tool_calls": 1 if request.tools_enabled else 0, "input_tokens": 100, "output_tokens": 20},
        versions={"model": "double-model", "prompt_sha256": "0" * 64},
    )


# ---------------------------------------------------------------- freeze gate

def test_reference_is_not_opened_before_the_run_is_frozen(tmp_path: Path) -> None:
    SpyReader.private_reads = 0
    reader = SpyReader(REPO / "data" / "planos_demo", REPO / "evaluation" / "reference", tmp_path / "stage")
    run_dir = tmp_path / "run"
    methods = build_methods(("A",))

    with pytest.raises(ReferenceNotFrozen):
        score_run(reader, run_dir)  # nothing frozen yet
    run_dir.mkdir()
    with pytest.raises(ReferenceNotFrozen):
        reader.load_references(object())  # type: ignore[arg-type]

    execute_run(reader, methods, run_dir, clock=fixed_clock())
    assert SpyReader.private_reads == 0  # running and freezing never touched the reference

    victim = next((run_dir / "outputs").rglob("*.json"))
    original = victim.read_bytes()
    victim.write_bytes(original.replace(b'"ok"', b'"failed"'))
    with pytest.raises(ReferenceNotFrozen):
        score_run(reader, run_dir)
    assert SpyReader.private_reads == 0  # tampering is caught before the private read

    victim.write_bytes(original)
    score_run(reader, run_dir)
    assert SpyReader.private_reads == 1


def test_extra_output_file_after_freezing_blocks_the_reference(tmp_path: Path) -> None:
    SpyReader.private_reads = 0
    reader = SpyReader(REPO / "data" / "planos_demo", REPO / "evaluation" / "reference", tmp_path / "stage")
    execute_run(reader, build_methods(("A",)), tmp_path / "run", clock=fixed_clock())
    (tmp_path / "run" / "outputs" / "A" / "late.rep1.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ReferenceNotFrozen):
        score_run(reader, tmp_path / "run")
    assert SpyReader.private_reads == 0


def test_forged_token_is_rejected(tmp_path: Path) -> None:
    from evaluation.comparativa.freeze import FreezeToken

    reader = dev_reader()
    execute_run(reader, build_methods(("A",)), tmp_path / "run", clock=fixed_clock())
    real = verify_freeze(tmp_path / "run")
    forged = FreezeToken(real.run_dir, real.outputs_digest)  # no seal
    with pytest.raises(ReferenceNotFrozen):
        reader.load_references(forged)


def test_frozen_run_cannot_receive_more_outputs(tmp_path: Path) -> None:
    from evaluation.comparativa.freeze import write_output

    reader = dev_reader()
    execute_run(reader, build_methods(("A",)), tmp_path / "run", clock=fixed_clock())
    with pytest.raises(ComparisonError):
        write_output(tmp_path / "run", {"variant": "A", "case_id": "z", "repetition": 1})
    with pytest.raises(ComparisonError):
        execute_run(reader, build_methods(("A",)), tmp_path / "run", clock=fixed_clock())


# ------------------------------------------------------------------ variant A

def test_variant_a_runs_for_real_on_separated_part_cases(tmp_path: Path) -> None:
    reader = dev_reader()
    execute_run(reader, build_methods(("A",)), tmp_path / "run", clock=fixed_clock())
    report = score_run(reader, tmp_path / "run")
    family = report["variants"]["A"]["families"]["development:separated_part_views"]["development_case"]

    assert family["sample"]["cases"] == 5
    assert family["sample"]["cases_with_reference"] == 3
    assert family["sample"]["cases_without_reference"] == 2  # sin referencia, not scored
    assert family["identity"]["matched"] == 9
    assert family["identity"]["false_positives"] == 0
    assert family["dimensions"]["mae_mm"] == 0.0
    # piezas_qty_desconocida / piezas_espesor_desconocido: correct abstention, nothing invented
    assert family["abstention"]["unidentifiable_fields"] == 2
    assert family["abstention"]["correct_abstentions"] == 2
    assert family["abstention"]["asserted_unidentifiable"] == 0
    assert family["identity"]["quantity"]["exact_rate"] == 1.0
    assert report["freeze"]["methods"]["A"]["rules_version"]
    assert set(report["freeze"]["methods"]["A"]["extractor_sha256"]) == {
        "backend/app/geometria/extraction.py", "backend/app/geometria/parts.py"
    }


def test_variant_a_on_plank_fixture_reports_what_the_engine_actually_returns(tmp_path: Path, plank_dirs) -> None:
    reader = plank_reader(tmp_path, plank_dirs)
    execute_run(reader, build_methods(("A",)), tmp_path / "run", clock=fixed_clock())
    outputs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((tmp_path / "run" / "outputs" / "A").glob("*.json"))]
    assert [o["status"] for o in outputs] == ["ok", "ok"]
    for output in outputs:
        # touching plank outlines merge into one line component: at most one rectangle survives,
        # thickness and quantity stay unknown.
        assert len(output["components"]) <= 1
        for component in output["components"]:
            assert component["dimensions_mm"]["thickness"] is None
            assert component["quantity"] is None
    report = score_run(reader, tmp_path / "run")
    (family,) = [s for fam in report["variants"]["A"]["families"].values() for s in fam.values()][:1]
    assert family["identity"]["reference_types"] == 4  # 2 cases x (20x500x700 twice-counted type, 960x500x20)
    assert family["identity"]["omissions"] >= 1
    assert family["dimensions"]["coverage"] is not None and family["dimensions"]["coverage"] < 1.0


# --------------------------------------------------------- B / C / D with doubles

def test_model_variants_refuse_to_exist_without_the_flag() -> None:
    with pytest.raises(ModelVariantsDisabled):
        build_methods(("B",), adapter=perfect_dev_adapter)
    with pytest.raises(ModelVariantsDisabled):
        build_methods(("C",), enable_model_variants=True)  # flag but no adapter


def test_model_variants_run_with_doubles_and_record_versions(tmp_path: Path) -> None:
    reader = dev_reader()
    index = PrecedentIndex(
        index_id="idx-test", admitted=True, annotated=True, sha256="a" * 64,
        entries=({"entry_id": "h1", "partition_id": "other", "summary": "armario"},
                 {"entry_id": "h2", "partition_id": "piezas", "summary": "same family"}),
    )
    seen: list[AdapterRequest] = []

    def adapter(request: AdapterRequest) -> AdapterResponse:
        seen.append(request)
        return perfect_dev_adapter(request)

    methods = build_methods(("A", "B", "C", "D"), enable_model_variants=True, adapter=adapter, precedent_index=index)
    limits = RunLimits(repetitions_stochastic=2)
    execute_run(reader, methods, tmp_path / "run", clock=fixed_clock(), limits=limits)
    report = score_run(reader, tmp_path / "run")

    assert {r.repetition for r in seen} == {1, 2}
    assert {r.tools_enabled for r in seen if r.variant == "B"} == {False}
    assert {r.tools_enabled for r in seen if r.variant in {"C", "D"}} == {True}
    for request in seen:
        if request.variant == "D":
            assert [p["entry_id"] for p in request.precedents] == ["h1"]  # same-family entry excluded
            assert all("partition_id" not in p for p in request.precedents)
        else:
            assert request.precedents == ()
    b = report["variants"]["B"]["families"]["development:separated_part_views"]["development_case"]
    assert b["sample"]["observations"] == 10  # 5 cases x 2 repetitions
    assert b["identity"]["recall"] == 1.0 and b["identity"]["precision"] == 1.0
    # piezas_qty_desconocida: the double asserts the quantity the views do not establish
    assert b["abstention"]["asserted_unidentifiable"] == 4
    assert b["resources"]["model_calls"] == 20 and b["resources"]["cost_eur_reported_total"] is None
    assert report["freeze"]["methods"]["B"]["adapter"]["name"] == "adapter"
    first = json.loads(next((tmp_path / "run" / "outputs" / "B").glob("dev-001.rep1.json")).read_text(encoding="utf-8"))
    assert first["versions"]["run"]["model"] == "double-model"
    assert first["limits"]["max_model_calls"] == 15 and first["input_sha256"]


def test_d_without_admitted_index_is_not_evaluated_never_zero(tmp_path: Path) -> None:
    calls: list[AdapterRequest] = []

    def adapter(request: AdapterRequest) -> AdapterResponse:
        calls.append(request)
        return perfect_dev_adapter(request)

    for index in (None, PrecedentIndex("i", False, True, "b" * 64, ({"entry_id": "h"},)),
                  PrecedentIndex("i", True, False, "b" * 64, ({"entry_id": "h"},)),
                  PrecedentIndex("i", True, True, "b" * 64, ({"entry_id": "h", "partition_id": "piezas"},))):
        run_dir = tmp_path / f"run-{len(list(tmp_path.iterdir()))}"
        reader = dev_reader()
        execute_run(reader, build_methods(("D",), enable_model_variants=True, adapter=adapter, precedent_index=index),
                    run_dir, clock=fixed_clock())
        report = score_run(reader, run_dir)
        d = report["variants"]["D"]["families"]["development:separated_part_views"]["development_case"]
        assert d["sample"]["status_counts"] == {"not_evaluated": 15}
        assert d["sample"]["observations_scored"] == 0
        assert d["identity"]["precision"] is None and d["identity"]["recall"] is None
        assert d["dimensions"]["coverage"] is None and d["dimensions"]["mae_mm"] is None
    assert calls == []  # the adapter (and so any paid call) was never reached


def test_adapter_failure_and_invalid_output_are_recorded_not_scored(tmp_path: Path) -> None:
    def broken(request: AdapterRequest) -> AdapterResponse:
        if request.case.case_id == "dev-001":
            raise RuntimeError("provider down")
        return AdapterResponse(components=[{"key": "k", "dimensions_mm": {"length": -4}}])

    reader = dev_reader()
    execute_run(reader, build_methods(("B",), enable_model_variants=True, adapter=broken),
                tmp_path / "run", clock=fixed_clock(), limits=RunLimits(repetitions_stochastic=1))
    report = score_run(reader, tmp_path / "run")
    b = report["variants"]["B"]["families"]["development:separated_part_views"]["development_case"]
    assert b["sample"]["status_counts"] == {"failed": 5}
    assert b["sample"]["reason_counts"] == {"failed:invalid_output": 4, "failed:method_raised": 1}
    assert b["sample"]["observations_scored"] == 0
    # failures stay in the denominator: nothing was found, so recall is 0 (not undefined)
    assert b["identity"]["recall"] == 0.0 and b["identity"]["precision"] is None
    assert b["identity"]["recall_conditioned_on_ok"] is None


def test_timeout_exceeded_discards_the_output(tmp_path: Path) -> None:
    ticks = iter(range(0, 10_000, 1000))
    clock = Clock(perf=lambda: float(next(ticks)), now_iso=lambda: "t")
    execute_run(dev_reader(), build_methods(("A",)), tmp_path / "run", clock=clock)
    report = score_run(dev_reader(), tmp_path / "run")
    a = report["variants"]["A"]["families"]["development:separated_part_views"]["development_case"]
    assert a["sample"]["reason_counts"] == {"failed:timeout_exceeded": 5}


# ------------------------------------------------------------------- matching

def _ref(key: str, length: float, width: float, thickness: float, quantity: float | None = 1) -> RefComponent:
    return RefComponent(
        key, {"length": RefField(length, True), "width": RefField(width, True), "thickness": RefField(thickness, True)},
        RefField(quantity, True),
    )


def _pred(key: str, length=None, width=None, thickness=None, quantity=None) -> Component:
    dims = {"length": length, "width": width, "thickness": thickness}
    return Component(key, dims, {k: ("observed" if v is not None else "unknown") for k, v in dims.items()},
                     quantity, "observed" if quantity else "unknown")


def test_matching_is_label_independent_and_one_to_one() -> None:
    reference = (_ref("R1", 700, 500, 20), _ref("R2", 960, 500, 20))
    # a front-view rectangle of a side panel shows length x thickness, labelled (length, width)
    pairs = match_components([_pred("P1", length=700, width=20), _pred("P2", length=961, width=500)], reference, 5.0)
    assert {(p.key, r.key) for p, r, _ in pairs} == {("P1", "R1"), ("P2", "R2")}
    assert dict(next(m for p, r, m in pairs if p.key == "P1")) == {"length": "length", "width": "thickness"}


def test_matching_ignores_keys_and_never_reuses_a_reference() -> None:
    reference = (_ref("A", 864, 300, 18, 2), _ref("B", 864, 300, 18, 2))
    predicted = [_pred("zzz", 864, 300, 18, 2), _pred("aaa", 864, 300, 18, 2), _pred("mmm", 864, 300, 18, 2)]
    pairs = match_components(predicted, reference, 1.0)
    assert len(pairs) == 2
    assert len({r.key for _, r, _ in pairs}) == 2
    # identical content: which rows pair is irrelevant, keys never decide
    assert {p.key for p, _, _ in pairs} <= {"zzz", "aaa", "mmm"}


def test_matching_needs_two_known_dimensions_and_respects_tolerance() -> None:
    reference = (_ref("R1", 700, 500, 20),)
    assert match_components([_pred("P", length=700)], reference, 5.0) == []
    assert match_components([_pred("P", length=720, width=500)], reference, 5.0) == []
    assert len(match_components([_pred("P", length=703, width=498)], reference, 5.0)) == 1


def test_quantities_are_compared_only_after_matching(tmp_path: Path) -> None:
    def adapter(request: AdapterRequest) -> AdapterResponse:
        return AdapterResponse(components=[
            {"key": "a", "dimensions_mm": {"length": 1200, "width": 300, "thickness": 18}, "quantity": 5},
            {"key": "ghost", "dimensions_mm": {"length": 77, "width": 66, "thickness": 5}, "quantity": 9},
        ])

    reader = dev_reader()
    execute_run(reader, build_methods(("B",), enable_model_variants=True, adapter=adapter),
                tmp_path / "run", clock=fixed_clock(), limits=RunLimits(repetitions_stochastic=1))
    b = score_run(reader, tmp_path / "run")["variants"]["B"]["families"]["development:separated_part_views"]["development_case"]
    quantity = b["identity"]["quantity"]
    # per scored case: only the matched pair is compared; the unmatched ghost row is a false positive
    assert quantity["compared_components"] == 3 and quantity["exact_matches"] == 0
    assert quantity["true_positive"] == 6  # min(5, 2) x 3 cases
    assert b["identity"]["false_positives"] == 3 and b["identity"]["omissions"] == 6


# ------------------------------------------------------ determinism and leaks

def test_report_is_deterministic_for_equal_inputs(tmp_path: Path, plank_dirs) -> None:
    outputs = []
    for name in ("one", "two"):
        reader = PlankAssemblyManifestReader(plank_dirs[0], plank_dirs[1], tmp_path / name / "staging")
        run_dir = tmp_path / name / "run"
        execute_run(reader, build_methods(("A",)), run_dir, clock=fixed_clock())
        report = score_run(reader, run_dir)
        outputs.append((canonical_json(report), render_markdown(report)))
        assert score_run(reader, run_dir) == report  # re-scoring the same freeze is stable
    assert outputs[0] == outputs[1]
    assert str(tmp_path).encode() not in outputs[0][0]  # no absolute paths in the report


def test_methods_only_receive_the_public_whitelist(tmp_path: Path, plank_dirs) -> None:
    reader = plank_reader(tmp_path, plank_dirs)
    received: list[tuple[AdapterRequest, bytes]] = []

    def spy(request: AdapterRequest) -> AdapterResponse:
        received.append((request, request.case.path.read_bytes()))
        return AdapterResponse(components=[])

    execute_run(reader, build_methods(("C",), enable_model_variants=True, adapter=spy), tmp_path / "run",
                clock=fixed_clock(), limits=RunLimits(repetitions_stochastic=1))
    private = (plank_dirs[1] / "references.json").read_text(encoding="utf-8")
    meta = reader.case_meta()
    assert len(received) == 2
    for request, dxf in received:
        payload = request.case.payload
        assert set(payload) == {"id", "file", "format", "unit", "view_kind", "instruction", "sha256"}
        blob = json.dumps(payload) + repr(request)
        assert SOURCE_NAME not in blob and SOURCE_NAME.encode() not in dxf
        assert meta[request.case.case_id].partition_id not in blob  # family hash stays harness-side
        assert "holdout" not in blob and "development" not in blob.replace("development_", "")
        assert "bounds_mm" not in blob and "source_file" not in blob
        assert str(plank_dirs[1]) not in blob and request.case.path.is_relative_to(tmp_path / "staging")
    assert "bounds_mm" in private  # sanity: the private side does hold the reference


def test_plank_reader_checks_public_private_consistency(tmp_path: Path, plank_dirs) -> None:
    public, private = plank_dirs
    with pytest.raises(ComparisonError):
        PlankAssemblyManifestReader(public, public, tmp_path / "s")
    cases = json.loads((public / "cases.json").read_text(encoding="utf-8"))
    cases[0]["sha256"] = "0" * 64
    (public / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    with pytest.raises(ComparisonError):
        PlankAssemblyManifestReader(public, private, tmp_path / "s").public_cases()


def test_precedent_index_excludes_same_case_and_partition() -> None:
    index = PrecedentIndex("i", True, True, "c" * 64, (
        {"entry_id": "same-case", "case_id": "c1"},
        {"entry_id": "same-family", "partition_id": "fam"},
        {"entry_id": "ok", "partition_id": "other", "case_id": "z"},
    ))
    from evaluation.comparativa.model import PublicCase

    case = PublicCase("c1", Path("x.dxf"), "0" * 64, "dxf", "mm", "k", "i")
    kept, excluded = index.usable_for(case, CaseMeta("c1", "f", "s", "fam", True))
    assert [e["entry_id"] for e in kept] == ["ok"] and excluded == 2


# ----------------------------------------------------------------------- CLI

def test_cli_runs_variant_a_and_refuses_models_without_the_flag(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    assert cli_main(["run", "--run-dir", str(run_dir)]) == 0
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert list(report["variants"]) == ["A"]
    assert (run_dir / "report.md").read_text(encoding="utf-8").startswith("# Comparativa")

    assert cli_main(["freeze", "--run-dir", str(tmp_path / "run2"), "--variants", "A,B"]) == 2
    assert not (tmp_path / "run2" / "freeze.json").exists()


def test_cli_freeze_then_score_are_separate_stages(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    assert cli_main(["score", "--run-dir", str(run_dir)]) == 2  # nothing frozen
    assert cli_main(["freeze", "--run-dir", str(run_dir)]) == 0
    assert not (run_dir / "report.json").exists()
    assert cli_main(["score", "--run-dir", str(run_dir)]) == 0
    assert (run_dir / "report.json").exists()


# ------------------------------------------------- review fixes: scoring (1, 2, 3, 8)

def _ref_case(thickness_k3_identifiable: bool = False, quantity_identifiable: bool = True):
    from evaluation.comparativa.model import ReferenceCase

    def comp(key, length, width, thickness, quantity, thickness_id=True):
        return RefComponent(
            key,
            {"length": RefField(length, True), "width": RefField(width, True), "thickness": RefField(thickness, thickness_id)},
            RefField(quantity, quantity_identifiable),
        )

    return ReferenceCase("c1", (
        comp("K1", 1200, 300, 18, 2),
        comp("K2", 864, 300, 18, 2),
        comp("K3", 864, 300, 18, 2, thickness_k3_identifiable),
    ))


def _out(components: list[dict], *, status: str = "ok", repetition: int = 1, variant: str = "B") -> dict:
    return {
        "variant": variant, "case_id": "c1", "repetition": repetition, "status": status,
        "reason": None if status == "ok" else "provider_down", "components": components,
        "timing": {"duration_s": 1.0}, "usage": {},
    }


def _c(key, length, width, thickness, quantity=2) -> dict:
    return {"key": key, "dimensions_mm": {"length": length, "width": width, "thickness": thickness}, "quantity": quantity}


def _score(outputs: list[dict], reference) -> dict:
    from evaluation.comparativa.scoring import score_outputs

    metas = {"c1": CaseMeta("c1", "fam", "dev", "p", True)}
    result = score_outputs(outputs, metas, {"c1": reference}, tolerance_mm=1.0, match_tolerance_mm=5.0)
    return result["B"]["fam"]["dev"]


@pytest.mark.parametrize("keys", [("K2", "K3"), ("b", "a"), ("a", "b"), ("K3", "K2")])
def test_abstention_score_does_not_depend_on_component_keys(keys: tuple[str, str]) -> None:
    # K2 and K3 share dimensions; K3's thickness cannot be identified and the answer leaves it unknown.
    answer = [
        _c("K1", 1200, 300, 18),
        _c(keys[0], 864, 300, 18),
        _c(keys[1], 864, 300, None),
    ]
    m = _score([_out(answer)], _ref_case())
    assert m["abstention"]["unidentifiable_fields"] == 1
    assert m["abstention"]["correct_abstentions"] == 1
    assert m["abstention"]["asserted_unidentifiable"] == 0
    assert m["abstention"]["resolvable_left_unknown"] == 0
    assert m["identity"]["matched"] == 3


def test_invented_value_in_an_unidentifiable_field_still_matches_and_is_reported() -> None:
    answer = [_c("K1", 1200, 300, 18), _c("K2", 864, 300, 18), _c("K3", 864, 300, 40)]
    m = _score([_out(answer)], _ref_case())
    assert m["identity"]["matched"] == 3 and m["identity"]["false_positives"] == 0
    assert m["abstention"]["asserted_unidentifiable"] == 1
    assert m["abstention"]["asserted_matching_reference_value"] == 0
    assert m["abstention"]["correct_abstentions"] == 0


def test_two_known_dimensions_do_not_outscore_three_with_one_wrong() -> None:
    wrong_three = _score([_out([_c("K1", 1200, 300, 18), _c("K2", 864, 300, 18), _c("K3", 864, 300, 40)])], _ref_case())
    abstain = _score([_out([_c("K1", 1200, 300, 18), _c("K2", 864, 300, 18), _c("K3", 864, 300, None)])], _ref_case())
    assert abstain["abstention"]["correct_abstention_rate"] == 1.0
    assert wrong_three["abstention"]["correct_abstention_rate"] == 0.0
    assert wrong_three["identity"]["matched"] == abstain["identity"]["matched"]


def test_wrong_value_in_an_identifiable_field_is_an_error_not_a_lost_component() -> None:
    answer = [_c("K1", 1200, 300, 40), _c("K2", 864, 300, 18), _c("K3", 864, 300, 18)]
    m = _score([_out(answer)], _ref_case(thickness_k3_identifiable=True))
    assert m["identity"]["matched"] == 3
    assert m["dimensions"]["eligible_fields"] == 9 and m["dimensions"]["predicted_fields"] == 9
    assert m["dimensions"]["within_tolerance"] == 8


def test_failed_observations_stay_in_the_coverage_and_recall_denominators() -> None:
    good = [_c("K1", 1200, 300, 18), _c("K2", 864, 300, 18), _c("K3", 864, 300, 18)]
    outputs = [_out(good, repetition=1)] + [_out([], status="failed", repetition=n) for n in range(2, 6)]
    m = _score(outputs, _ref_case(thickness_k3_identifiable=True))
    assert m["sample"]["status_counts"] == {"failed": 4, "ok": 1}
    assert m["identity"]["reference_types"] == 15 and m["identity"]["recall"] == pytest.approx(3 / 15)
    assert m["dimensions"]["eligible_fields"] == 45 and m["dimensions"]["coverage"] == pytest.approx(9 / 45)
    # the conditioned view is published separately and labelled
    assert m["identity"]["recall_conditioned_on_ok"] == 1.0
    assert m["dimensions"]["coverage_conditioned_on_ok"] == 1.0
    only_failed = _score([_out([], status="failed")], _ref_case())
    assert only_failed["identity"]["recall"] == 0.0 and only_failed["dimensions"]["coverage"] == 0.0
    assert only_failed["identity"]["recall_conditioned_on_ok"] is None


def test_not_evaluated_and_not_applicable_stay_out_of_the_denominators() -> None:
    outputs = [_out([], status="not_evaluated"), _out([], status="not_applicable", repetition=2)]
    m = _score(outputs, _ref_case())
    assert m["identity"]["reference_types"] == 0 and m["identity"]["recall"] is None
    assert m["dimensions"]["coverage"] is None


def test_quantity_precision_and_recall_only_cover_identifiable_quantities() -> None:
    reference = _ref_case(thickness_k3_identifiable=True, quantity_identifiable=False)
    abstain = _score([_out([_c(k, *d, None) for k, d in (("K1", (1200, 300, 18)), ("K2", (864, 300, 18)), ("K3", (864, 300, 18)))])], reference)
    invent = _score([_out([_c(k, *d, 2) for k, d in (("K1", (1200, 300, 18)), ("K2", (864, 300, 18)), ("K3", (864, 300, 18)))])], reference)
    for m in (abstain, invent):
        q = m["identity"]["quantity"]
        assert q["reference_total"] == 0 and q["recall"] is None and q["precision"] is None
    assert abstain["abstention"]["correct_abstentions"] == 3 and abstain["abstention"]["asserted_unidentifiable"] == 0
    assert invent["abstention"]["asserted_unidentifiable"] == 3 and invent["abstention"]["asserted_matching_reference_value"] == 3


# ----------------------------------- review fixes: opaque ids, seal checks, freeze (4, 6, 7)

def test_development_corpus_hands_out_opaque_ids_and_staged_paths(tmp_path: Path) -> None:
    reader = dev_reader(tmp_path / "stage")
    cases = reader.public_cases()
    assert [c.case_id for c in cases] == [f"dev-{n:03d}" for n in range(1, 6)]
    for case in cases:
        blob = json.dumps(case.payload) + str(case.path)
        for revealing in ("piezas", "qty", "espesor", "planos_demo", "evaluation", "reference", "desconocid"):
            assert revealing not in blob
        assert case.path.is_relative_to(tmp_path / "stage") and case.path.is_file()
        assert set(case.payload) == {"id", "file", "format", "unit", "view_kind", "instruction", "sha256"}
    assert reader.id_map["dev-001"] == "piezas_completo"  # the mapping stays harness-side
    assert reader.corpus_info()["id_map"] == reader.id_map


def test_variant_a_is_unchanged_by_staging_the_dev_inputs(tmp_path: Path) -> None:
    from evaluation.comparativa.methods import RulesMethod
    from evaluation.comparativa.model import PublicCase

    staged = dev_reader(tmp_path / "stage").public_cases()
    assert "planos_demo" not in str(staged[0].path)
    for case in staged:
        original = REPO / "data" / "planos_demo" / f"{dev_reader(tmp_path / 's2').id_map[case.case_id]}.dxf"
        twin = PublicCase(case.case_id, original, case.sha256, case.format, case.unit, case.view_kind, case.instruction)
        method = RulesMethod()
        limits = RunLimits()
        assert (
            [c.to_json() for c in method.run(case, repetition=1, limits=limits, context={}).components]
            == [c.to_json() for c in method.run(twin, repetition=1, limits=limits, context={}).components]
        )


def _copy_demo(tmp_path: Path) -> Path:
    import shutil

    demo = tmp_path / "demo"
    demo.mkdir()
    for source in (REPO / "data" / "planos_demo").glob("piezas_*.dxf"):
        shutil.copyfile(source, demo / source.name)
    return demo


def test_score_run_rejects_inputs_that_changed_after_freezing(tmp_path: Path) -> None:
    demo = _copy_demo(tmp_path)
    reader = dev_reader(tmp_path / "s1", demo)
    execute_run(reader, build_methods(("A",)), tmp_path / "run", clock=fixed_clock())
    (demo / "piezas_completo.dxf").write_bytes((demo / "piezas_completo.dxf").read_bytes() + b"\n")
    SpyReader.private_reads = 0
    spy = SpyReader(demo, REPO / "evaluation" / "reference", tmp_path / "s2")
    with pytest.raises(ComparisonError, match="inputs"):
        score_run(spy, tmp_path / "run")
    assert SpyReader.private_reads == 0


def test_score_run_rejects_a_missing_case_with_a_controlled_error(tmp_path: Path) -> None:
    demo = _copy_demo(tmp_path)
    execute_run(dev_reader(tmp_path / "s1", demo), build_methods(("A",)), tmp_path / "run", clock=fixed_clock())
    (demo / "piezas_espesor_36.dxf").unlink()
    with pytest.raises(ComparisonError):
        score_run(dev_reader(tmp_path / "s2", demo), tmp_path / "run")


def test_score_run_rejects_a_different_corpus_description(tmp_path: Path) -> None:
    reader = dev_reader(tmp_path / "s1")
    execute_run(reader, build_methods(("A",)), tmp_path / "run", clock=fixed_clock())

    class Renamed(DevelopmentManifestReader):
        def corpus_info(self):
            return {**super().corpus_info(), "kind": "something_else"}

    other = Renamed(REPO / "data" / "planos_demo", REPO / "evaluation" / "reference", tmp_path / "s2")
    with pytest.raises(ComparisonError, match="corpus"):
        score_run(other, tmp_path / "run")


def test_scoring_an_output_for_an_unknown_case_is_a_controlled_error() -> None:
    from evaluation.comparativa.scoring import score_outputs

    with pytest.raises(ComparisonError):
        score_outputs([_out([])], {}, {}, tolerance_mm=1.0, match_tolerance_mm=5.0)


def test_freeze_record_with_duplicate_output_paths_is_rejected(tmp_path: Path) -> None:
    from evaluation.comparativa.freeze import _outputs_digest

    execute_run(dev_reader(tmp_path / "s"), build_methods(("A",)), tmp_path / "run", clock=fixed_clock())
    path = tmp_path / "run" / "freeze.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["outputs"].append({**record["outputs"][0], "repetition": 99})  # same path, valid digest
    record["outputs_digest"] = _outputs_digest(sorted(
        record["outputs"], key=lambda e: (e["variant"], e["case_id"], e["repetition"])
    ))
    record["outputs"].sort(key=lambda e: (e["variant"], e["case_id"], e["repetition"]))
    record["outputs_digest"] = _outputs_digest(record["outputs"])
    path.write_bytes(canonical_json(record))
    with pytest.raises(ReferenceNotFrozen, match="duplicate"):
        verify_freeze(tmp_path / "run")
