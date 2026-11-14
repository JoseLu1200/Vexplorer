"""Image-only information comparison using the existing validated Jev client."""

import argparse
from hashlib import sha256
import json
import io
from PIL import Image, ImageOps
from pathlib import Path
from tools.semantic_lab.jev_comparison import (
    JevClient,
    load_api_key,
    build_payload,
    build_questions,
    AttemptBudget,
)


def run(root, credential, normalized=False):
    destination = root / ("jev-normalized" if normalized else "jev")
    destination.mkdir(exist_ok=True)
    client = JevClient(
        load_api_key(None, credential), destination / "cache", budget=AttemptBudget(60)
    )
    questions = build_questions(
        {
            "table": "A table or desk with a working top and open space underneath.",
            "shelving": "An open shelving unit or bookcase with multiple horizontal storage levels.",
            "low_cabinet": "A low storage cabinet with compartments, optionally also used as a bench.",
            "frame": "An open frame or enclosure whose furniture function is not determined.",
        }
    )
    manifest = json.loads((root / "public-manifest.json").read_text())
    for case in manifest["cases"]:
        cid = case["id"]
        sources = {
            "source": root / case["input"],
            "B": root / "results/B" / cid / "artifacts/view-00.png",
        }
        sources.update(
            {
                v: root / "results" / v / cid / "seed-42/diagnostic-views/view-00.png"
                for v in ("A", "C", "D")
            }
        )
        for variant, path in sources.items():
            target = destination / f"{variant}-{cid}.json"
            if target.exists() or not path.exists():
                continue
            image = path.read_bytes()
            source_hash = sha256(image).hexdigest()
            if normalized:
                with Image.open(io.BytesIO(image)) as original:
                    canvas = ImageOps.pad(
                        original.convert("RGB"),
                        (512, 512),
                        color="white",
                        method=Image.Resampling.LANCZOS,
                    )
                    buffer = io.BytesIO()
                    canvas.save(buffer, format="PNG")
                    image = buffer.getvalue()
            print("Jev", variant, cid, flush=True)
            payload = build_payload(
                {
                    "text": "Furniture-related visual input. Classify only what the image supports; missing details remain unknown."
                },
                "mixed",
                questions=questions,
                image_bytes=image,
            )
            try:
                result = client.evaluate(payload)
            except Exception as exc:
                result = {"error_type": type(exc).__name__, "error": str(exc)[:120]}
            target.write_text(
                json.dumps(
                    {
                        "variant": variant,
                        "case_id": cid,
                        "source_sha256": sha256(image).hexdigest(),
                        "original_sha256": source_hash,
                        "preprocess": "aspect-preserving 512 square padding"
                        if normalized
                        else "original",
                        "privileged": variant == "D",
                        "result": result,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf8",
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--credential-file", type=Path, required=True)
    p.add_argument("--normalized", action="store_true")
    a = p.parse_args()
    run(a.root, a.credential_file, a.normalized)
