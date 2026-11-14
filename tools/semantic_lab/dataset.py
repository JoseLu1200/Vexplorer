from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence

from .features import UnsupportedGeometry, extract_dxf


DEFAULT_CATEGORIES = ("sofas", "simple-tables", "buffets", "beds")
OPTIONAL_CATEGORIES = ("living-room", "dining-sets")
CATEGORY_DEFINITIONS = {
    "sofas": "CADBlock sofas library; includes sofas, armchairs, chaise longues, ottomans, and a few side tables.",
    "simple-tables": "CADBlock simple-tables library; mostly table/desk layouts with chairs, plus some office furniture.",
    "buffets": "CADBlock buffets library; commercial serving counters, food-service carts, refrigeration, and kitchen-line equipment, not domestic sideboards.",
    "beds": "CADBlock beds library; beds and bed groups, sometimes with nightstands.",
    "living-room": "CADBlock living-room library; mixed living-room objects and overlapping seating/table types.",
    "dining-sets": "CADBlock dining-sets library; multi-object dining arrangements rather than isolated furniture instances.",
}

_VARIANT_STOPWORDS = {
    "metric",
    "plan",
    "elevation",
    "front",
    "side",
    "rear",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "single",
    "twin",
    "full",
    "queen",
    "king",
    "small",
    "large",
    "narrow",
    "wide",
    "compact",
    "long",
    "short",
    "oversized",
    "seat",
    "seater",
    "sofa",
    "armchair",
    "loveseat",
}
_SINGULAR = {"arms": "arm", "backs": "back", "pillows": "pillow", "cushions": "cushion"}


class _UnionFind:
    def __init__(self, items: Iterable[int]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def discover_candidates(source: Path | str, categories: Sequence[str]) -> list[tuple[str, Path]]:
    root = Path(source)
    found: list[tuple[str, Path]] = []
    for category in categories:
        locations = (
            root / "dxf_metric" / category,
            root / "revisar_no_planos" / "dxf_metric" / category,
        )
        for location in locations:
            if location.is_dir():
                found.extend((category, path) for path in sorted(location.glob("*.dxf")))
    return sorted(found, key=lambda item: (item[0], str(item[1]).casefold()))


def _variant_signature(label: str, path: Path) -> str | None:
    tokens = []
    for raw in path.stem.lower().split("-"):
        token = _SINGULAR.get(raw, raw)
        if token and token not in _VARIANT_STOPWORDS:
            tokens.append(token)
    if len(tokens) < 3:
        return None
    return f"{label}:" + "-".join(tokens)


def _group_records(records: list[dict[str, object]]) -> None:
    union = _UnionFind(range(len(records)))
    owners: dict[tuple[str, str], int] = {}
    for index, record in enumerate(records):
        for field in ("source_sha256", "geometry_signature", "render_sha256", "variant_signature"):
            if not record.get(field):
                continue
            key = (field, str(record[field]))
            if key in owners:
                union.union(index, owners[key])
            else:
                owners[key] = index
    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        components[union.find(index)].append(index)
    for indexes in components.values():
        digest = hashlib.sha256(
            "|".join(sorted(str(records[index]["render_sha256"]) for index in indexes)).encode("ascii")
        ).hexdigest()[:20]
        for index in indexes:
            records[index]["group_id"] = f"grp_{digest}"


def _split_groups(records: list[dict[str, object]], seed: int) -> None:
    assignments: dict[str, str] = {}
    split_order = ("train", "validation", "test")
    for label in sorted({str(record["label"]) for record in records}):
        groups = sorted(
            {str(record["group_id"]) for record in records if record["label"] == label},
            key=lambda group: hashlib.sha256(f"{seed}:{label}:{group}".encode()).hexdigest(),
        )
        targets = {
            "train": round(len(groups) * 0.70),
            "validation": round(len(groups) * 0.15),
        }
        targets["test"] = len(groups) - targets["train"] - targets["validation"]
        counts = Counter(assignments[group] for group in groups if group in assignments)
        for group in groups:
            if group in assignments:
                continue
            split = max(
                split_order,
                key=lambda name: (targets[name] - counts[name], -split_order.index(name)),
            )
            assignments[group] = split
            counts[split] += 1
    for record in records:
        record["split"] = assignments[str(record["group_id"])]


def _public_sample(record: dict[str, object]) -> dict[str, object]:
    return {
        key: record[key]
        for key in (
            "id",
            "source_path",
            "image_path",
            "label",
            "label_source",
            "group_id",
            "split",
            "features",
            "text",
        )
    }


def prepare_dataset(
    source: Path | str,
    output_dir: Path | str,
    *,
    categories: Sequence[str] = DEFAULT_CATEGORIES,
    seed: int = 20261114,
    image_size: int = 384,
) -> dict[str, object]:
    source_root = Path(source).resolve()
    destination = Path(output_dir).resolve()
    render_dir = destination / "renders"
    destination.mkdir(parents=True, exist_ok=True)
    candidates = discover_candidates(source_root, categories)
    records: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    for label, path in candidates:
        relative = path.resolve().relative_to(source_root).as_posix()
        sample_id = "cad_" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:20]
        image_path = render_dir / f"{sample_id}.png"
        try:
            extraction = extract_dxf(path, image_path=image_path, image_size=image_size)
        except UnsupportedGeometry as exc:
            excluded.append({"source_path": str(path.resolve()), "reason": exc.reason})
            continue
        records.append(
            {
                "id": sample_id,
                "source_path": str(path.resolve()),
                "image_path": str(image_path),
                "label": label,
                "label_source": "cadblock_library_proxy",
                "features": extraction.features,
                "text": extraction.text,
                "source_sha256": extraction.source_sha256,
                "geometry_signature": extraction.geometry_signature,
                "render_sha256": extraction.render_sha256,
                "variant_signature": _variant_signature(label, path),
            }
        )
    _group_records(records)
    _split_groups(records, seed)
    samples = [_public_sample(record) for record in records]
    split_counts = Counter(str(sample["split"]) for sample in samples)
    label_counts = Counter(str(sample["label"]) for sample in samples)
    label_split_counts: dict[str, dict[str, int]] = {}
    for label in sorted(label_counts):
        label_split_counts[label] = dict(
            Counter(str(sample["split"]) for sample in samples if sample["label"] == label)
        )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "metadata": {
            "corpus": "CADBlock local 2D metric drawings",
            "categories": list(categories),
            "label_policy": "directory names are editorial evaluation proxies, not human ground truth",
            "label_source": "cadblock_library_proxy",
            "category_definitions": {
                category: CATEGORY_DEFINITIONS.get(category, "Unreviewed CADBlock library proxy.")
                for category in categories
            },
            "candidate_count": len(candidates),
            "sample_count": len(samples),
            "excluded_count": len(excluded),
            "excluded": excluded,
            "split_seed": seed,
            "split_policy": "70/15/15 by duplicate group before model fitting",
            "group_policy": "union of exact source hash, translation/scale-normalized geometry signature, and canonical render hash",
            "variant_group_policy": "filename-derived metadata only; conservative token normalization used only to keep obvious design variants in one split, never as a feature",
            "split_counts": dict(split_counts),
            "label_counts": dict(label_counts),
            "label_split_counts": label_split_counts,
            "feature_version": 1,
            "render": {"mode": "geometry_only_no_text_or_dimensions", "size": image_size},
            "leakage_policy": "label, paths, filenames, drawing text, and group ids are excluded from text and numeric features",
            "license": {
                "source": "https://cadblock.org/",
                "terms": "https://cadblock.org/terms-and-conditions/",
                "note": "Local experimental use must remain subject to source terms; no relicensing is claimed.",
            },
        },
        "samples": samples,
    }
    manifest_path = destination / "manifest.json"
    content = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    manifest_path.write_bytes(content)
    (destination / "manifest.sha256").write_text(
        f"{hashlib.sha256(content).hexdigest()}  manifest.json\n", encoding="ascii"
    )
    return manifest


def _parse_categories(raw: str) -> tuple[str, ...]:
    categories = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not categories:
        raise argparse.ArgumentTypeError("at least one category is required")
    return categories


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the local semantic furniture benchmark")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--categories", type=_parse_categories, default=DEFAULT_CATEGORIES)
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--image-size", type=int, default=384)
    args = parser.parse_args(argv)
    manifest = prepare_dataset(
        args.source,
        args.output_dir,
        categories=args.categories,
        seed=args.seed,
        image_size=args.image_size,
    )
    print(json.dumps(manifest["metadata"], indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
