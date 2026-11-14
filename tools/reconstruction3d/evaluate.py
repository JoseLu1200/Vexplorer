"""Evaluator-only geometry diagnostics; never imported by the inference service."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment
from scipy.ndimage import binary_erosion, distance_transform_edt
from backend.app.reconstruction3d.artifacts import vertices, render_assembly, VIEWS
from backend.app.reconstruction3d.models import AssemblyProposal


def iou(a, b):
    return float(np.logical_and(a, b).sum() / max(1, np.logical_or(a, b).sum()))


def boundary_error(a, b):
    """Symmetric mean silhouette-boundary distance, normalized by image width."""
    ae = a & ~binary_erosion(a)
    be = b & ~binary_erosion(b)
    if not ae.any() or not be.any():
        return None
    return float(
        (
            distance_transform_edt(~be)[ae].mean()
            + distance_transform_edt(~ae)[be].mean()
        )
        / (2 * a.shape[1])
    )


def material_iou(prediction, reference):
    """Exact cuboid union IoU when each assembly has disjoint interiors.

    Translation aligns minimum bounds; there is no fitted scaling or rotation.
    """
    if prediction.unit != "mm" or not prediction.components or not reference.components:
        return None
    boxes = []
    for assembly in (prediction, reference):
        lo = np.array([p.origin_mm for p in assembly.components])
        size = np.array([p.size_mm for p in assembly.components])
        lo = lo - lo.min(0)
        hi = lo + size
        for i in range(len(lo)):
            for j in range(i + 1, len(lo)):
                if np.all(np.minimum(hi[i], hi[j]) - np.maximum(lo[i], lo[j]) > 1e-6):
                    return None
        boxes.append((lo, hi, float(np.prod(size, axis=1).sum())))
    pl, ph, pv = boxes[0]
    rl, rh, rv = boxes[1]
    intersection = np.prod(
        np.maximum(
            0,
            np.minimum(ph[:, None], rh[None, :]) - np.maximum(pl[:, None], rl[None, :]),
        ),
        axis=2,
    ).sum()
    return float(intersection / (pv + rv - intersection))


def geometry_metrics(prediction, reference):
    if not prediction.components:
        return {"not_evaluated": "no_components"}
    pv = np.concatenate([vertices(p) for p in prediction.components])
    rv = np.concatenate([vertices(p) for p in reference.components])
    pspan = np.ptp(pv, axis=0)
    rspan = np.ptp(rv, axis=0)
    scores = []
    edges = []
    for e, a in VIEWS:
        pm = render_assembly(prediction, elev=e, azim=a)[1]
        rm = render_assembly(reference, elev=e, azim=a)[1]
        edges.append(boundary_error(pm, rm))
        scores.append(
            iou(
                render_assembly(prediction, elev=e, azim=a)[1],
                render_assembly(reference, elev=e, azim=a)[1],
            )
        )
    # Matching by sorted dimensions ignores labels and position: explicitly only dimensional matching.
    pd = np.array([sorted(p.size_mm) for p in prediction.components])
    rd = np.array([sorted(p.size_mm) for p in reference.components])
    cost = np.abs(pd[:, None, :] - rd[None, :, :]).mean(2)
    pi, ri = linear_sum_assignment(cost)
    return {
        "reference_component_count": len(rd),
        "predicted_component_count": len(pd),
        "absolute_count_difference": abs(len(pd) - len(rd)),
        "bounds_mm_predicted": pspan.tolist(),
        "bounds_mm_reference": rspan.tolist(),
        "bounds_absolute_error_mm": np.abs(pspan - rspan).tolist()
        if prediction.unit == "mm"
        else None,
        "matched_dimensions_mae_mm": float(cost[pi, ri].mean())
        if prediction.unit == "mm"
        else None,
        "unmatched_occurrences": abs(len(pd) - len(rd)),
        "material_volume_iou_translation_only": material_iou(prediction, reference),
        "normalized_silhouette_iou_per_view": scores,
        "input_view_silhouette_iou": float(np.mean(scores[4:])),
        "reserved_view_silhouette_iou": float(np.mean(scores[:4])),
        "normalized_boundary_error_per_view": edges,
        "reserved_view_boundary_error": float(np.mean(edges[:4]))
        if all(x is not None for x in edges[:4])
        else None,
        "scale_alignment": "each_shape_bbox_normalized_for_silhouettes_only; no metric scaling fit",
        "part_matching": "minimum dimension error, orientation invariant, no semantic or joint scoring",
    }


def splat_metrics(folder, reference):
    views = folder / "diagnostic-views"
    if not (views / "mask-05.png").exists():
        return {"not_evaluated": "diagnostic_views_missing"}
    pred = [np.asarray(Image.open(views / f"mask-{n:02d}.png")) > 0 for n in range(6)]
    ref = [
        render_assembly(reference, elev=e, azim=a, resolution=256)[1] for e, a in VIEWS
    ]
    front, side = pred[4:]
    candidates = [
        (front, side),
        (np.fliplr(side), front),
        (np.fliplr(front), np.fliplr(side)),
        (side, np.fliplr(front)),
    ]
    observed = [
        float(np.mean([iou(a, b) for a, b in zip(pair, ref[4:])]))
        for pair in candidates
    ]
    quarter = int(np.argmax(observed))
    edges = [boundary_error(pred[(i - quarter) % 4], ref[i]) for i in range(4)]
    return {
        "unaligned_reserved_view_iou": float(
            np.mean([iou(a, b) for a, b in zip(pred[:4], ref[:4])])
        ),
        "source_view_iou_after_alignment": observed[quarter],
        "reserved_view_iou_after_alignment": float(
            np.mean([iou(pred[(i - quarter) % 4], ref[i]) for i in range(4)])
        ),
        "alignment_degrees": quarter * 90,
        "reserved_view_boundary_error": float(np.mean(edges))
        if all(x is not None for x in edges)
        else None,
        "alignment_uses": "only two source-view reference silhouettes; 4 z rotations; evaluator-only",
        "scale": "independent robust bbox normalization; not physical scale",
        "alpha_threshold": 0.5,
        "limitations": "silhouette proxy and diagnostic renderer; does not evaluate surface accuracy, dimensions or engineering topology",
    }


def evaluate(root):
    from .integrity import validate_references

    integrity = validate_references(root)
    manifest = json.loads((root / "public-manifest.json").read_text())
    admission = json.loads((root / "references" / "admission.json").read_text())
    report = {
        "reference_integrity": integrity,
        "scope": "six diagnostic cases, not industrial validation",
        "B": [],
        "idol": [],
        "limitations": [
            "The evaluator sees references only after B predictions are frozen.",
            "Input-view score compares reference silhouette projections, not text or full observed drawing edges.",
            "B boxes imply no verified joints, hardware, material, load capacity or manufacturing tolerance.",
            "Sparse drawings admit multiple valid assemblies; completing an ambiguous reference can lower similarity.",
            "Splats have no component/BOM score and no legitimate absolute scale.",
        ],
        "admission": admission,
    }
    for case in manifest["cases"]:
        cid = case["id"]
        ref = AssemblyProposal.model_validate_json(
            (root / "references" / cid / "proposal.json").read_text(encoding="utf8")
        )
        bp = root / "results" / "B" / cid
        if (bp / "outcome.json").exists():
            outcome = json.loads((bp / "outcome.json").read_text(encoding="utf8"))
            p = AssemblyProposal.model_validate(outcome["proposal"])
            baseline = AssemblyProposal.model_validate(outcome["baseline"])
            report["B"].append(
                {
                    "case_id": cid,
                    "status": outcome["status"],
                    "duration_s": outcome["duration_s"],
                    "metrics": geometry_metrics(p, ref),
                    "baseline_metrics": geometry_metrics(baseline, ref),
                    "checks": outcome["checks"],
                    "reference_is_functional_candidate": cid
                    in ("case-01", "case-02", "case-03"),
                }
            )
        for variant in ("A", "C", "D"):
            for seed in manifest["seeds"]:
                folder = root / "results" / variant / cid / f"seed-{seed}"
                info = {
                    "variant": variant,
                    "case_id": cid,
                    "seed": seed,
                    "bom_score": None,
                    "metric_dimensions": None,
                    "privileged_reference_input": variant == "D",
                }
                if (folder / "run.json").exists():
                    info.update(
                        status="generated",
                        run=json.loads((folder / "run.json").read_text()),
                    )
                    info["reference_silhouette_metrics"] = splat_metrics(folder, ref)
                    if variant == "C" and (bp / "outcome.json").exists():
                        info["B_silhouette_metrics"] = splat_metrics(folder, p)
                elif (folder / "failure.json").exists():
                    info.update(
                        status="failed",
                        failure=json.loads((folder / "failure.json").read_text()),
                    )
                else:
                    info.update(status="not_executed")
                report["idol"].append(info)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf8") as f:
        json.dump(evaluate(args.root), f, indent=2, ensure_ascii=False)
