"""Prepare NEW authorized DXFs and optionally run one cached local encoder.

The generated manifest contains observations, not a BOM or hidden reference.
Run publish_semantic_explorer afterwards to admit a checked immutable release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from tools.semantic_lab.features import extract_dxf


def prepare_drawings(
    paths: list[Path], output: Path, *, synthetic: bool = False
) -> Path:
    if output.exists():
        raise ValueError("output_exists_use_new_directory")
    if not 1 <= len(paths) <= 2000:
        raise ValueError("member_limit")
    output.mkdir(parents=True)
    (output / "renders").mkdir()
    samples, seen = [], set()
    for path in paths:
        if path.suffix.lower() != ".dxf" or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("unsupported_or_oversized_dxf")
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if source_hash in seen:
            continue
        seen.add(source_hash)
        member = "drawing-" + source_hash
        image = output / "renders" / f"{member}.png"
        extraction = extract_dxf(path, image_path=image, image_size=384)
        samples.append(
            {
                "id": member,
                "display_name": path.stem[:300],
                "text": extraction.text,
                "features": extraction.features,
                "image_path": f"renders/{member}.png",
                "group_id": extraction.geometry_signature,
            }
        )
    manifest = output / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metadata": {
                    "purpose": "new_drawing_exploration",
                    "synthetic": synthetic,
                    "feature_version": 1,
                    "render": {
                        "mode": "geometry_only_no_text_or_dimensions",
                        "size": 384,
                    },
                },
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--encode", action="store_true")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Identify generated/demo fixtures explicitly",
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--model",
        choices=("embeddinggemma2", "dinov3", "minilm"),
        default="embeddinggemma2",
    )
    parser.add_argument("--mode", choices=("mixed", "image", "text"), default="mixed")
    parser.add_argument("--dimensions", type=int)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args(argv)
    if args.encode and args.cache_dir is None:
        parser.error("--encode requires --cache-dir with existing local model weights")
    if (args.model == "dinov3" and args.mode != "image") or (
        args.model == "minilm" and args.mode != "text"
    ):
        parser.error("DINOv3 uses image; MiniLM uses text")
    manifest = prepare_drawings(
        args.inputs, args.output, synthetic=args.synthetic
    ).resolve()
    if args.encode:
        command = [
            args.python,
            "-m",
            "tools.semantic_lab.encode",
            "--manifest",
            str(manifest),
            "--model",
            args.model,
            "--mode",
            args.mode,
            "--output",
            str(manifest.parent / "embeddings.npz"),
            "--cache-dir",
            str(args.cache_dir.resolve()),
            "--local-files-only",
        ]
        if args.dimensions is not None:
            command += ["--truncate-dim", str(args.dimensions)]
        # No shell, no network downloads, no credentials on the command line.
        subprocess.run(
            command, cwd=Path(__file__).resolve().parents[1], check=True, timeout=900
        )
    print(json.dumps({"manifest": str(manifest), "encoded": args.encode}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
