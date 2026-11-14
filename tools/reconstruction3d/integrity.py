"""Private evaluator inventory, separate from the public inference manifest."""

from hashlib import sha256
import json


def freeze_references(root, *, stage):
    if stage not in ("before_inference", "post_execution_review"):
        raise ValueError("invalid_capture_stage")
    refs = root / "references"
    files = {
        p.relative_to(refs).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in sorted(refs.rglob("*"))
        if p.is_file() and p.name != "SHA256SUMS.json"
    }
    with (refs / "SHA256SUMS.json").open("x", encoding="utf8") as f:
        json.dump({"capture_stage": stage, "files": files}, f, indent=2)


def validate_references(root):
    refs = (root / "references").resolve()
    manifest = json.loads((refs / "SHA256SUMS.json").read_text(encoding="utf8"))
    actual = {
        p.relative_to(refs).as_posix()
        for p in refs.rglob("*")
        if p.is_file() and p.name != "SHA256SUMS.json"
    }
    if actual != set(manifest["files"]):
        raise ValueError("reference_inventory_mismatch")
    for name, expected in manifest["files"].items():
        path = (refs / name).resolve()
        if (
            not path.is_relative_to(refs)
            or sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("reference_hash_mismatch")
    return {
        "capture_stage": manifest["capture_stage"],
        "verified_files": len(actual),
        "inventory_sha256": sha256((refs / "SHA256SUMS.json").read_bytes()).hexdigest(),
    }
