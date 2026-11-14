"""Copy a checked legacy lab corpus into a new portable import directory.

Absolute render paths are accepted ONLY inside the original manifest directory.
Original files and vectors remain unchanged; all copied renders use relative paths.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from backend.app.semantic_explorer.models import MAX_IMAGE_BYTES, MAX_MEMBERS
from tools.publish_semantic_explorer import build_bundle, sha


def stage_corpus(
    manifest_path: Path, npz_path: Path, output: Path
) -> tuple[Path, Path]:
    if output.exists():
        raise ValueError("output_exists_use_new_directory")
    if (
        manifest_path.stat().st_size > 32 * 1024 * 1024
        or npz_path.stat().st_size > 64 * 1024 * 1024
    ):
        raise ValueError("artifact_too_large")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    meta = json.loads(
        npz_path.with_suffix(npz_path.suffix + ".json").read_text(encoding="utf-8")
    )
    if meta.get("manifest_sha256") != sha(manifest_path) or meta.get(
        "npz_sha256"
    ) != sha(npz_path):
        raise ValueError("artifact_hash_mismatch")
    if not 1 <= len(manifest["samples"]) <= MAX_MEMBERS:
        raise ValueError("member_limit")
    base = manifest_path.parent.resolve()
    copies = []
    for i, sample in enumerate(manifest["samples"]):
        if sample.get("image_path"):
            path = Path(sample["image_path"])
            path = (path if path.is_absolute() else base / path).resolve()
            if not path.is_relative_to(base):
                raise ValueError("image_path_outside_corpus")
            if path.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError("image_too_large")
            relative = f"renders/{i}.png"
            copies.append((path, relative))
            sample["image_path"] = relative
    output.mkdir(parents=True)
    (output / "renders").mkdir()
    for path, relative in copies:
        shutil.copyfile(path, output / relative)
    manifest.setdefault("metadata", {})["portable_source_manifest_sha256"] = sha(
        manifest_path
    )
    destination = output / "manifest.json"
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    vectors = output / "embeddings.npz"
    shutil.copyfile(npz_path, vectors)
    meta["manifest_sha256"] = sha(destination)
    meta["config_identity"]["manifest_sha256"] = sha(destination)
    vectors.with_suffix(".npz.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    build_bundle(
        destination, vectors
    )  # Revalidate IDs, shapes and original input hashes.
    return destination, vectors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest, vectors = stage_corpus(args.manifest, args.embeddings, args.output)
    print(json.dumps({"manifest": str(manifest), "embeddings": str(vectors)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
