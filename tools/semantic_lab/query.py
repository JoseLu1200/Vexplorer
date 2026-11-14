"""Query a persisted semantic-lab index by sample id."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np


def _unit_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix, dtype=float), where=norms != 0)


def query_index(
    npz_path: Path,
    metadata_path: Path,
    sample_id: str,
    k: int = 5,
    frozen_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be positive")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with np.load(npz_path, allow_pickle=False) as archive:
        ids = [str(value) for value in archive["ids"].tolist()]
        vectors = _unit_rows(np.asarray(archive["vectors"], dtype=float))
        modality_vectors = {
            name.removeprefix("modality_"): _unit_rows(np.asarray(archive[name], dtype=float))
            for name in archive.files
            if name.startswith("modality_")
        }
    if len(ids) != vectors.shape[0] or len(set(ids)) != len(ids):
        raise ValueError("incompatible index ids and vector rows")
    if sample_id not in ids:
        raise KeyError(f"unknown sample id: {sample_id}")
    samples = metadata.get("samples", [])
    by_id = {str(sample["id"]): sample for sample in samples}
    if set(ids) != set(by_id):
        raise ValueError("index metadata ids do not match NPZ ids")
    query_position = ids.index(sample_id)
    reference_split = metadata.get("reference_split", "train")
    candidates = [
        index
        for index, candidate_id in enumerate(ids)
        if candidate_id != sample_id and by_id[candidate_id].get("split") == reference_split
    ]
    similarities = vectors @ vectors[query_position]
    ranked = sorted(candidates, key=lambda index: (-similarities[index], ids[index]))[:k]
    neighbors = []
    for index in ranked:
        explanations = {
            name: float(matrix[query_position] @ matrix[index])
            for name, matrix in sorted(modality_vectors.items())
        }
        neighbors.append(
            {
                "id": ids[index],
                "proxy_label": by_id[ids[index]].get("proxy_label"),
                "cosine_similarity": float(similarities[index]),
                "modality_cosine": explanations,
            }
        )
    result = {
        "sample_id": sample_id,
        "proxy_label": by_id[sample_id].get("proxy_label"),
        "reference_split": reference_split,
        "neighbors": neighbors,
        "explanation": "cosine similarity by representation modality; labels are evaluation proxies",
    }
    if frozen_config is not None:
        from tools.semantic_lab.evaluate import _classifier

        train_positions = [index for index, value in enumerate(ids) if by_id[value].get("split") == "train"]
        if not train_positions:
            raise ValueError("classification requires train references in the index")
        classifier = _classifier(
            str(frozen_config["classifier"]),
            neighbors=min(int(frozen_config["neighbors"]), len(train_positions)),
            seed=int(frozen_config["seed"]),
        )
        classifier.fit(
            vectors[train_positions],
            [str(by_id[ids[index]]["proxy_label"]) for index in train_positions],
        )
        result["predicted_label"] = str(classifier.predict(vectors[[query_position]])[0])
        result["classifier"] = str(frozen_config["classifier"])
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-npz", type=Path, required=True)
    parser.add_argument("--index-json", type=Path, required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--frozen-config", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    frozen = json.loads(args.frozen_config.read_text(encoding="utf-8")) if args.frozen_config else None
    result = query_index(args.index_npz, args.index_json, args.sample_id, args.k, frozen)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
