"""Frozen small-gallery retrieval diagnostic with the repository's real encoder.

Encoder inputs contain images only. Case identities and reserved images are
used exclusively here, by the evaluator, after reconstructions are frozen.
"""

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import numpy as np


def run(root, output, cache, device):
    from tools.semantic_lab.encode import SentenceTransformerEncoder
    import torch

    torch.set_num_threads(2)
    manifest = json.loads((root / "public-manifest.json").read_text())
    cases = [x["id"] for x in manifest["cases"]]
    inputs = {}
    for case in manifest["cases"]:
        cid = case["id"]
        inputs["source:" + cid] = root / case["input"]
        inputs["gallery:" + cid] = root / "references" / cid / "view-01.png"
        for n in range(6):
            inputs[f"B:{cid}:{n}"] = (
                root / "results" / "B" / cid / "artifacts" / f"view-{n:02d}.png"
            )
        for variant in ("A", "C", "D"):
            for n in range(6):
                path = (
                    root
                    / "results"
                    / variant
                    / cid
                    / "seed-42"
                    / "diagnostic-views"
                    / f"view-{n:02d}.png"
                )
                if path.exists():
                    inputs[f"{variant}:{cid}:{n}"] = path
    encoder = SentenceTransformerEncoder(
        model_name="embeddinggemma2",
        mode="image",
        cache_dir=cache,
        device=device,
        precision="auto",
        local_files_only=True,
    )
    encoder._batch_size = 1
    vectors = {}
    output.mkdir(parents=True, exist_ok=False)
    vector_cache = root / "retrieval-vector-cache"
    vector_cache.mkdir(exist_ok=True)
    encoder_identity = json.dumps(asdict(encoder.info), sort_keys=True).encode()
    for key, path in inputs.items():
        print("encode", key, flush=True)
        content = path.read_bytes()
        cached = vector_cache / (
            sha256(encoder_identity + b"\0" + content).hexdigest() + ".npy"
        )
        if cached.exists():
            vectors[key] = np.load(cached, allow_pickle=False)
        else:
            vectors[key] = encoder.encode([content], mode="image", truncate_dim=768)[0]
            np.save(cached, vectors[key], allow_pickle=False)
    gallery = np.stack([vectors["gallery:" + cid] for cid in cases])
    scores = {}
    for condition in ("source", "B", "A", "C", "D"):
        ranks = []
        details = []
        for index, cid in enumerate(cases):
            keys = (
                [condition + ":" + cid]
                if condition == "source"
                else [f"{condition}:{cid}:{n}" for n in range(6)]
            )
            if not all(k in vectors for k in keys):
                continue
            query = np.stack([vectors[k] for k in keys]).mean(0)
            query /= max(np.linalg.norm(query), 1e-12)
            similarities = gallery @ query
            rank = int(np.where(np.argsort(-similarities) == index)[0][0]) + 1
            ranks.append(rank)
            details.append(
                {"case_id": cid, "rank": rank, "scores": similarities.tolist()}
            )
        scores[condition] = {
            "coverage": len(ranks),
            "gallery_size": len(cases),
            "hit_at_1": float(np.mean(np.array(ranks) == 1)) if ranks else None,
            "mrr": float(np.mean(1 / np.array(ranks))) if ranks else None,
            "details": details,
            "privileged": condition == "D",
        }
    np.savez_compressed(output / "vectors.npz", **vectors)
    single = {}
    for condition in ("B", "A", "C", "D"):
        ranks = []
        for index, cid in enumerate(cases):
            key = f"{condition}:{cid}:0"
            if key in vectors:
                ranks.append(
                    int(np.where(np.argsort(-(gallery @ vectors[key])) == index)[0][0])
                    + 1
                )
        single[condition] = {
            "coverage": len(ranks),
            "ranks": ranks,
            "hit_at_1": float(np.mean(np.array(ranks) == 1)) if ranks else None,
            "mrr": float(np.mean(1 / np.array(ranks))) if ranks else None,
        }
    (output / "single-view-control.json").write_text(json.dumps(single, indent=2))
    report = {
        "encoder": asdict(encoder.info),
        "scores": scores,
        "inputs_sha256": {
            k: sha256(p.read_bytes()).hexdigest() for k, p in inputs.items()
        },
        "protocol": "image-only cosine; six private reference views form fixed gallery; source has one image, generated arms average six normalized image embeddings; no training",
        "limitations": [
            "Six synthetic/ambiguous cases only; no significance or industrial generalization.",
            "Gallery contains a novel reserved view of each same object; not similarity to priced historical furniture.",
            "Number of query views differs; improvement cannot isolate geometry from multi-view augmentation.",
            "Jev is a separate classifier and is not tested by this embedding benchmark.",
        ],
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--device", default="cpu")
    a = p.parse_args()
    run(a.root, a.output, a.cache, a.device)
