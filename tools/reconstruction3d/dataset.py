from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from backend.app.reconstruction3d.models import AssemblyProposal, Component
from backend.app.reconstruction3d.artifacts import export_package


def own_references():
    def part(id, size, origin):
        return Component(
            id=id,
            label=id,
            size_mm=size,
            origin_mm=origin,
            source_refs=["input"],
            assumptions=["Synthetic design reference; joinery and loads unspecified"],
        )

    table = [part("top", [1200, 700, 30], [0, 0, 720])]
    table += [
        part(f"leg-{i}", [60, 60, 720], [x, y, 0])
        for i, (x, y) in enumerate([(0, 0), (1140, 0), (0, 640), (1140, 640)])
    ]
    table += [
        part(f"apron-{i}", [1080, 20, 80], [60, y, 640])
        for i, y in enumerate([20, 660])
    ]
    table += [
        part(f"side-apron-{i}", [20, 580, 80], [x, 60, 640])
        for i, x in enumerate([20, 1160])
    ]
    shelf = [
        part("left", [18, 350, 1800], [0, 0, 0]),
        part("right", [18, 350, 1800], [882, 0, 0]),
        part("top", [864, 350, 18], [18, 0, 1782]),
        part("bottom", [864, 350, 18], [18, 0, 80]),
        part("back", [864, 18, 1684], [18, 332, 98]),
    ]
    shelf += [
        part(f"shelf-{i}", [864, 332, 18], [18, 0, z])
        for i, z in enumerate([600, 1200])
    ]
    bench = [
        part("left", [18, 400, 450], [0, 0, 0]),
        part("right", [18, 400, 450], [982, 0, 0]),
        part("top", [1000, 400, 30], [0, 0, 450]),
        part("bottom", [964, 400, 18], [18, 0, 70]),
        part("back", [964, 18, 362], [18, 382, 88]),
        part("divider", [18, 382, 362], [491, 0, 88]),
    ]
    return [
        AssemblyProposal(
            status="proposed",
            intended_use=use,
            unit="mm",
            components=parts,
            assumptions=["Own synthetic reference"],
            missing_information=["material", "joinery", "load capacity"],
            functional_notes=[
                "Visually reviewable intended use; no engineering certification"
            ],
        )
        for use, parts in [
            ("table", table),
            ("bookcase", shelf),
            ("storage bench", bench),
        ]
    ]


def visible_lines(proposal, axes, depth_axis, sign):
    bounds = np.array(
        [
            p.origin_mm + [p.origin_mm[k] + p.size_mm[k] for k in range(3)]
            for p in proposal.components
        ]
    )
    xs = np.unique(np.round(bounds[:, [axes[0], axes[0] + 3]], 3))
    ys = np.unique(np.round(bounds[:, [axes[1], axes[1] + 3]], 3))
    grid = np.full((len(ys) - 1, len(xs) - 1), np.nan)
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            x = (xs[i] + xs[i + 1]) / 2
            y = (ys[j] + ys[j + 1]) / 2
            hit = (
                (bounds[:, axes[0]] <= x + 0.0005)
                & (bounds[:, axes[0] + 3] >= x - 0.0005)
                & (bounds[:, axes[1]] <= y + 0.0005)
                & (bounds[:, axes[1] + 3] >= y - 0.0005)
            )
            if hit.any():
                grid[j, i] = np.max(
                    sign * bounds[hit, depth_axis + (3 if sign > 0 else 0)]
                )

    def changed(a, b):
        return np.isfinite(a) != np.isfinite(b) or (
            np.isfinite(a) and np.isfinite(b) and abs(a - b) > 0.1
        )

    lines = []
    for j, y in enumerate(ys):
        active = [
            changed(
                grid[j - 1, i] if j else np.nan,
                grid[j, i] if j < len(ys) - 1 else np.nan,
            )
            for i in range(len(xs) - 1)
        ]
        start = None
        for i, on in enumerate(active + [False]):
            if on and start is None:
                start = i
            elif not on and start is not None:
                lines.append((xs[start], y, xs[i], y))
                start = None
    for i, x in enumerate(xs):
        active = [
            changed(
                grid[j, i - 1] if i else np.nan,
                grid[j, i] if i < len(xs) - 1 else np.nan,
            )
            for j in range(len(ys) - 1)
        ]
        start = None
        for j, on in enumerate(active + [False]):
            if on and start is None:
                start = j
            elif not on and start is not None:
                lines.append((x, ys[start], x, ys[j]))
                start = None
    return lines, (xs[0], ys[0], xs[-1], ys[-1])


def drawing(proposal, path, *, scaled=True, single=False):
    views = [("FRONT", *visible_lines(proposal, (0, 2), 1, -1))]
    if not single:
        views.append(("SIDE", *visible_lines(proposal, (1, 2), 0, 1)))
    im = Image.new("RGB", (1280, 800), "white")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default(size=22)
    width = 1280 / len(views)
    span = max(max(b[2] - b[0], b[3] - b[1]) for _, _, b in views)
    s = min((width - 100) / span, 550 / span)
    for k, (name, lines, b) in enumerate(views):
        cx = (b[0] + b[2]) / 2
        cy = (b[1] + b[3]) / 2

        def pixel(x, y):
            return ((k + 0.5) * width + (x - cx) * s, 390 - (y - cy) * s)

        for x0, y0, x1, y1 in lines:
            d.line([pixel(x0, y0), pixel(x1, y1)], fill="black", width=2)
        d.text((k * width + 30, 30), name, font=font, fill="black")
    if scaled:
        b = views[0][2]
        a = 0.5 * width - (b[2] - b[0]) * s / 2
        c = 0.5 * width + (b[2] - b[0]) * s / 2
        d.line((a, 700, c, 700), fill="black", width=2)
        for x in [a, c]:
            d.line((x, 690, x, 710), fill="black", width=2)
        d.text(((a + c) / 2 - 50, 720), f"{b[2] - b[0]:g} mm", font=font, fill="black")
    im.save(path)


def prepare(root: Path, previous: Path):
    if root.exists():
        raise ValueError("destination_exists")
    root.mkdir(parents=True)
    public = root / "inputs"
    private = root / "references"
    public.mkdir()
    private.mkdir()
    refs = own_references()
    admissions = ["synthetic_functional_candidate"] * 3
    for p in sorted((previous / "evaluator_only").glob("*/reference.json")):
        source = json.loads(p.read_text())
        parts = []
        for n, item in enumerate(source["components"]):
            b = item["bounds_mm"]
            parts.append(
                Component(
                    id=f"p{n}",
                    label=f"p{n}",
                    origin_mm=b[:3],
                    size_mm=[b[k + 3] - b[k] for k in range(3)],
                    source_refs=["input"],
                    assumptions=["Publisher geometry; function not validated"],
                )
            )
        minz = min(p.origin_mm[2] for p in parts)
        for p in parts:
            p.origin_mm[2] -= minz
        refs.append(
            AssemblyProposal(
                status="proposed",
                intended_use="unknown",
                unit="mm",
                components=parts,
                assumptions=["Publisher geometry only"],
                missing_information=["intended use", "functional completion"],
                functional_notes=["Rejected as functional ground truth by user"],
            )
        )
        admissions.append("incomplete_ambiguous_control")
    cases = []
    for n, (ref, admission) in enumerate(zip(refs, admissions), 1):
        id = f"case-{n:02d}"
        dest = public / id
        dest.mkdir()
        export_package(ref, private / id)
        for filename, scaled, single in [
            ("drawing.png", True, False),
            ("front.png", True, True),
            ("unscaled.png", False, True),
        ]:
            drawing(ref, dest / filename, scaled=scaled, single=single)
        cases.append(
            {
                "id": id,
                "input": f"inputs/{id}/drawing.png",
                "unit": "mm",
                "source_sha256": hashlib.sha256(
                    (dest / "drawing.png").read_bytes()
                ).hexdigest(),
            }
        )
    manifest = {
        "protocol": "A image -> Idol; B image -> extended native harness -> parts; C B render -> Idol; D reference render -> Idol (privileged control)",
        "cases": cases,
        "steps": 50,
        "num_gaussians": 32768,
        "seeds": [42],
        "mode": "synthetic",
        "evaluation_status": "not_executed",
        "inference_may_read": ["inputs"],
        "reference_may_be_used_only_by": ["D_positive_control", "evaluator"],
        "selection": "diagnostic; three own synthetic fixtures then three previously inspected controls; no blind claim",
    }
    (root / "public-manifest.json").write_text(json.dumps(manifest, indent=2))
    (private / "admission.json").write_text(
        json.dumps(dict(zip([c["id"] for c in cases], admissions)), indent=2)
    )
    from .integrity import freeze_references

    freeze_references(root, stage="before_inference")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(prepare(a.output, a.previous), indent=2))
