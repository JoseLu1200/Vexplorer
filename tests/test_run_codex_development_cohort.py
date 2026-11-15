from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


FAKE_HARNESS = r'''from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path

def sha(data): return hashlib.sha256(data).hexdigest()
def tree(root):
    h=hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
        h.update(p.relative_to(root).as_posix().encode()); h.update(b"\0"); h.update(p.read_bytes()); h.update(b"\0")
    return h.hexdigest()

p=argparse.ArgumentParser()
for name in ("manifest","runtime-dir","output","relay-dir"): p.add_argument("--"+name, type=Path, required=True)
p.add_argument("--workers", required=True); p.add_argument("--test-job-timeout-s", required=True); p.add_argument("--execute", action="store_true")
a=p.parse_args(); case=json.loads(a.manifest.read_text(encoding="utf-8"))["cases"][0]; cid=case["case_id"]
a.output.mkdir(parents=True); a.relay_dir.mkdir(parents=True, exist_ok=True)
marker=a.output.parent/(cid+".started"); marker.write_text("started", encoding="ascii")
if cid == "hang":
    heartbeat=a.output.parent/"hang.heartbeat"; heartbeat.write_text(str(time.monotonic()), encoding="ascii"); (a.output.parent/"hang.pid").write_text(str(__import__('os').getpid()), encoding="ascii")
deadline=time.monotonic()+3
while len(list(a.output.parent.glob("*.started"))) < 2 and time.monotonic() < deadline: time.sleep(0.01)
if len(list(a.output.parent.glob("*.started"))) != 2: raise SystemExit("children did not overlap")
print("ruta-Á-漢字", flush=True)
if cid == "fail-fast": raise SystemExit(7)
if cid == "hang":
    hang_deadline=time.monotonic()+5
    while time.monotonic() < hang_deadline:
        heartbeat.write_text(str(time.monotonic()), encoding="ascii"); time.sleep(0.05)
    raise SystemExit(0)
runtime_hash=tree(a.runtime_dir.resolve()); harness_hash=sha(Path(__file__).resolve().read_bytes()); bridge_hash=sha(Path("tools/codex_test_bridge.py").resolve().read_bytes())
runtime_config={"execution_transport":"codex_agent_relay","test_profile":"interactive_codex_1800_v1","api_key_loaded":False,"interactive_total_timeout_s":1800,"interactive_stage_timeout_s":900,"config_evidence":{"job_timeout_s":1800,"review_attempt_timeout_s":900,"reviewer_model":"gpt-6-astra"}}
bundle={"evaluation_phase":"development","execution_transport":"codex_agent_relay","runtime_config":runtime_config,"case_order":[cid],"cases":[{"case_id":cid,"split":"development","public_dxf_sha256":sha(Path(case["dxf_path"]).read_bytes()),"prediction":{"job_state":"failed" if cid.endswith("b") else "succeeded","failure_code":"fixture_failure" if cid.endswith("b") else None}}]}
provenance={"runtime_sha256_before":runtime_hash,"runtime_sha256_after":runtime_hash,"runtime_unchanged":True,"bridge_sha256_before":bridge_hash,"bridge_sha256_after":bridge_hash,"harness_sha256_before":harness_hash,"harness_sha256_after":harness_hash,"relay_code_unchanged":True,"api_key_loaded":cid=="bad-provenance","execution_transport":"codex_agent_relay","test_profile":"interactive_codex_1800_v1"}
(a.output/"prediction-bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
(a.output/"runtime-provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
print(json.dumps({"event":"codex_relay_request_ready","case_id":cid,"request_path":str(a.relay_dir/cid/"request.json")}), flush=True)
'''


def _fixture(tmp_path: Path, case_ids=("case-a", "case-b")) -> tuple[Path, Path, Path]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    cases = []
    for case_id in case_ids:
        source = inputs / f"{case_id}.dxf"
        source.write_text(f"DXF {case_id}", encoding="ascii")
        cases.append({"case_id": case_id, "split": "development", "dxf_path": source.name})
    manifest = inputs / "development.json"
    manifest.write_text(json.dumps({"evaluation_phase": "development", "cases": cases}), encoding="utf-8")
    runtime = tmp_path / "runtime"
    (runtime / "backend" / "app").mkdir(parents=True)
    (runtime / "backend" / "app" / "main.py").write_text("# frozen\n", encoding="ascii")
    harness = tmp_path / "fake_harness.py"
    harness.write_text(FAKE_HARNESS, encoding="utf-8")
    return manifest, runtime, harness


def _command(tmp_path: Path, manifest: Path, runtime: Path, harness: Path) -> list[str]:
    return [
        sys.executable, "-m", "tools.run_codex_development_cohort",
        "--manifest", str(manifest), "--runtime-dir", str(runtime),
        "--output", str(tmp_path / "output"), "--relay-dir", str(tmp_path / "relay"),
        "--harness", str(harness),
    ]


def _replace_argument(command: list[str], name: str, value: Path) -> list[str]:
    result = list(command)
    result[result.index(name) + 1] = str(value)
    return result


def test_dry_run_prints_plan_without_creating_output(tmp_path: Path) -> None:
    manifest, runtime, harness = _fixture(tmp_path)
    completed = subprocess.run(_command(tmp_path, manifest, runtime, harness), cwd=ROOT, capture_output=True, encoding="utf-8", check=False)
    assert completed.returncode == 0, completed.stderr
    plan = json.loads(completed.stdout)
    assert plan["dry_run"] is True
    assert plan["case_order"] == ["case-a", "case-b"]
    assert all(isinstance(argument, str) for command in plan["commands"] for argument in command)
    assert not (tmp_path / "output").exists()
    assert not (tmp_path / "relay").exists()


def test_execute_runs_fresh_cases_in_parallel_and_combines_without_selection(tmp_path: Path) -> None:
    manifest, runtime, harness = _fixture(tmp_path)
    completed = subprocess.run([*_command(tmp_path, manifest, runtime, harness), "--execute"], cwd=ROOT, capture_output=True, encoding="utf-8", check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count("ruta-Á-漢字") == 2
    ready = [json.loads(line) for line in completed.stdout.splitlines() if '"event"' in line]
    assert {item["case_id"] for item in ready} == {"case-a", "case-b"}
    bundle = json.loads((tmp_path / "output" / "prediction-bundle.json").read_text(encoding="utf-8"))
    assert bundle["case_order"] == ["case-a", "case-b"]
    assert [item["prediction"]["job_state"] for item in bundle["cases"]] == ["succeeded", "failed"]
    assert bundle["runtime_config"]["cohort_execution"] == "parallel_fresh_generation_v1"
    for case_id in ("case-a", "case-b"):
        child_manifest = json.loads((tmp_path / "output" / "manifests" / f"{case_id}.json").read_text(encoding="utf-8"))
        assert Path(child_manifest["cases"][0]["dxf_path"]).is_absolute()
        assert (tmp_path / "output" / "children" / case_id / "runtime-provenance.json").is_file()
    provenance = json.loads((tmp_path / "output" / "cohort-provenance.json").read_text(encoding="utf-8"))
    assert provenance["publisher_unchanged"] is True
    assert provenance["harness_unchanged"] is True
    assert provenance["runtime_unchanged"] is True


def test_rejects_more_than_two_or_unsafe_case_ids(tmp_path: Path) -> None:
    for index, (case_ids, expected) in enumerate([(("a", "b", "c"), "at most two"), (("safe", "../escape"), "case_id")]):
        case_root = tmp_path / str(index)
        case_root.mkdir()
        manifest, runtime, harness = _fixture(case_root, case_ids=case_ids)
        completed = subprocess.run(_command(case_root, manifest, runtime, harness), cwd=ROOT, capture_output=True, encoding="utf-8", check=False)
        assert completed.returncode != 0
        assert expected in completed.stderr


def test_rejects_absolute_or_parent_traversing_dxf_paths(tmp_path: Path) -> None:
    manifest, runtime, harness = _fixture(tmp_path)
    private = tmp_path / "private.dxf"
    private.write_text("PRIVATE", encoding="ascii")
    for dxf_path in (str(private.resolve()), "../private.dxf"):
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["cases"][0]["dxf_path"] = dxf_path
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        completed = subprocess.run(
            _command(tmp_path, manifest, runtime, harness),
            cwd=ROOT, capture_output=True, encoding="utf-8", check=False,
        )
        assert completed.returncode != 0
        assert "relative path inside the manifest directory" in completed.stderr


def test_rejects_same_or_nested_output_and_relay_paths(tmp_path: Path) -> None:
    manifest, runtime, harness = _fixture(tmp_path)
    base = _command(tmp_path, manifest, runtime, harness)
    output = tmp_path / "output"
    for relay in (output, output / "relay", tmp_path):
        command = _replace_argument(base, "--relay-dir", relay)
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", check=False)
        assert completed.returncode != 0
        assert "separate non-nested paths" in completed.stderr


def test_rejects_child_provenance_that_contradicts_no_api_profile(tmp_path: Path) -> None:
    manifest, runtime, harness = _fixture(tmp_path, case_ids=("case-a", "bad-provenance"))
    completed = subprocess.run(
        [*_command(tmp_path, manifest, runtime, harness), "--execute"],
        cwd=ROOT, capture_output=True, encoding="utf-8", check=False,
    )
    assert completed.returncode != 0
    assert "child_provenance_invalid:bad-provenance" in completed.stderr
    assert not (tmp_path / "output" / "prediction-bundle.json").exists()


def test_child_failure_terminates_owned_sibling_without_orphan(tmp_path: Path) -> None:
    manifest, runtime, harness = _fixture(tmp_path, case_ids=("fail-fast", "hang"))
    started = time.monotonic()
    completed = subprocess.run(
        [*_command(tmp_path, manifest, runtime, harness), "--execute"],
        cwd=ROOT, capture_output=True, encoding="utf-8", check=False,
        timeout=12,
    )
    elapsed = time.monotonic() - started
    heartbeat = tmp_path / "output" / "children" / "hang.heartbeat"
    assert completed.returncode != 0
    assert elapsed < 3
    assert heartbeat.is_file()
    last_write = heartbeat.read_text(encoding="ascii")
    time.sleep(0.25)
    assert heartbeat.read_text(encoding="ascii") == last_write
