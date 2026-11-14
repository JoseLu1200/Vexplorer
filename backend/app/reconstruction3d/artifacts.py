from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from .models import AssemblyProposal
from .geometry import inspect_assembly

FACES = (
    (0, 2, 3, 1),
    (4, 5, 7, 6),
    (0, 1, 5, 4),
    (2, 6, 7, 3),
    (0, 4, 6, 2),
    (1, 3, 7, 5),
)
VIEWS = ((22, -55), (22, 35), (22, 125), (22, 215), (0, -90), (0, 0))


def vertices(part):
    return np.array(
        [
            [
                part.origin_mm[k] + (part.size_mm[k] if i & (1 << k) else 0)
                for k in range(3)
            ]
            for i in range(8)
        ],
        dtype=float,
    )


def camera_basis(elev, azim):
    e, a = math.radians(elev), math.radians(azim)
    direction = np.array(
        [math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)]
    )
    right = np.array([-math.sin(a), math.cos(a), 0.0])
    up = np.cross(direction, right)
    return np.array([right, up, direction])


def render_assembly(
    proposal: AssemblyProposal, *, resolution=384, elev=22, azim=-55, exploded=False
):
    """Deterministic triangle z-buffer. Reference and prediction use the same renderer."""
    if not 32 <= resolution <= 2048:
        raise ValueError("invalid_resolution")
    rgb = np.full((resolution, resolution, 3), 255, dtype=np.uint8)
    depth = np.full((resolution, resolution), -np.inf)
    if not proposal.components:
        return Image.fromarray(rgb), np.zeros(depth.shape, dtype=bool)
    world = [vertices(p) for p in proposal.components]
    allv = np.concatenate(world)
    mid = (allv.min(0) + allv.max(0)) / 2
    span = max(float(np.max(allv.max(0) - allv.min(0))), 1e-6)
    basis = camera_basis(elev, azim)
    scale = resolution / (span * (2.0 if exploded else 1.7))
    for index, v in enumerate(world):
        if exploded:
            delta = v.mean(0) - mid
            norm = np.linalg.norm(delta)
            if norm:
                v = v + delta / norm * span * 0.20
        q = (v - mid) @ basis.T
        q[:, :2] *= scale
        q[:, 0] += resolution / 2
        q[:, 1] = resolution / 2 - q[:, 1]
        for face in FACES:
            normal = np.cross(v[face[1]] - v[face[0]], v[face[2]] - v[face[0]])
            normal /= max(np.linalg.norm(normal), 1e-12)
            shade = 0.58 + 0.35 * abs(float(normal @ np.array([0.3, -0.4, 0.866])))
            color = np.array([160, 181, 195]) * shade
            if exploded:
                color = (
                    np.array(
                        [
                            (73 + index * 53) % 160 + 55,
                            (110 + index * 83) % 150 + 55,
                            (150 + index * 37) % 150 + 55,
                        ]
                    )
                    * shade
                )
            for ids in ((face[0], face[1], face[2]), (face[0], face[2], face[3])):
                t = q[list(ids)]
                lo = np.maximum(0, np.floor(t[:, :2].min(0)).astype(int))
                hi = np.minimum(resolution - 1, np.ceil(t[:, :2].max(0)).astype(int))
                if np.any(hi < lo):
                    continue
                xx, yy = np.meshgrid(
                    np.arange(lo[0], hi[0] + 1) + 0.5, np.arange(lo[1], hi[1] + 1) + 0.5
                )
                x0, y0 = t[0, :2]
                x1, y1 = t[1, :2]
                x2, y2 = t[2, :2]
                den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                if abs(den) < 1e-10:
                    continue
                w0 = ((y1 - y2) * (xx - x2) + (x2 - x1) * (yy - y2)) / den
                w1 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y2)) / den
                w2 = 1 - w0 - w1
                zz = w0 * t[0, 2] + w1 * t[1, 2] + w2 * t[2, 2]
                sub = depth[lo[1] : hi[1] + 1, lo[0] : hi[0] + 1]
                mask = (w0 >= -1e-8) & (w1 >= -1e-8) & (w2 >= -1e-8) & (zz > sub)
                sub[mask] = zz[mask]
                rgb[lo[1] : hi[1] + 1, lo[0] : hi[0] + 1][mask] = np.clip(
                    color, 0, 255
                ).astype("uint8")
    return Image.fromarray(rgb), np.isfinite(depth)


def write_glb(proposal, path):
    binary = bytearray()
    views = []
    access = []
    meshes = []
    nodes = []

    def data(array, target, kind, ctype):
        binary.extend(b"\0" * ((-len(binary)) % 4))
        offset = len(binary)
        raw = array.tobytes()
        binary.extend(raw)
        vi = len(views)
        views.append(
            {
                "buffer": 0,
                "byteOffset": offset,
                "byteLength": len(raw),
                "target": target,
            }
        )
        a = {
            "bufferView": vi,
            "componentType": ctype,
            "count": len(array),
            "type": kind,
        }
        if kind == "VEC3":
            a.update(min=array.min(0).tolist(), max=array.max(0).tolist())
        access.append(a)
        return len(access) - 1

    for j, p in enumerate(proposal.components):
        v = vertices(p)
        v = np.column_stack([v[:, 0], v[:, 2], -v[:, 1]]).astype("<f4") * 0.001
        triangles = np.array(
            [i for f in FACES for i in (f[0], f[1], f[2], f[0], f[2], f[3])],
            dtype="<u2",
        )
        pos = data(v, 34962, "VEC3", 5126)
        idx = data(triangles, 34963, "SCALAR", 5123)
        meshes.append(
            {
                "primitives": [
                    {"attributes": {"POSITION": pos}, "indices": idx, "material": 0}
                ]
            }
        )
        nodes.append(
            {
                "mesh": j,
                "name": p.id,
                "extras": {
                    "label": p.label,
                    "assumptions": p.assumptions,
                    "source_refs": p.source_refs,
                },
            }
        )
    g = {
        "asset": {
            "version": "2.0",
            "extras": {
                "provisional": True,
                "source_unit": "mm",
                "certified_for_manufacturing": False,
            },
        },
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [
            {
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.6, 0.7, 0.75, 1],
                    "metallicFactor": 0,
                    "roughnessFactor": 0.85,
                },
            }
        ],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": access,
    }
    jb = json.dumps(g, separators=(",", ":")).encode()
    jb += b" " * ((-len(jb)) % 4)
    binary.extend(b"\0" * ((-len(binary)) % 4))
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, 28 + len(jb) + len(binary))
        + struct.pack("<I4s", len(jb), b"JSON")
        + jb
        + struct.pack("<I4s", len(binary), b"BIN\0")
        + binary
    )


def export_package(proposal: AssemblyProposal, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    # A destination is immutable: do not leave stale artifacts from a previous proposal.
    if any(destination.iterdir()):
        raise ValueError("destination_not_empty")
    (destination / "proposal.json").write_text(
        proposal.model_dump_json(indent=2), encoding="utf8"
    )
    checks = inspect_assembly(proposal)
    (destination / "checks.json").write_text(
        json.dumps(checks, indent=2), encoding="utf8"
    )
    with (destination / "bom.csv").open("w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(
            ["component_id", "label", "x", "y", "z", "quantity", "unit", "status"]
        )
        for p in proposal.components:
            w.writerow(
                [
                    p.id,
                    "'" + p.label
                    if p.label.startswith(("=", "+", "-", "@"))
                    else p.label,
                    *p.size_mm,
                    1,
                    proposal.unit,
                    "design_hypothesis",
                ]
            )
    metric = proposal.unit == "mm" and bool(proposal.components)
    if metric:
        write_glb(proposal, destination / "assembly.glb")
    parts = destination / "parts"
    parts.mkdir()
    for p in proposal.components:
        dims = p.size_mm
        scale = 250 / max(dims)
        label = html.escape(p.label)
        text = html.escape(" x ".join(f"{v:g}" for v in dims) + " " + proposal.unit)
        views = [("Alzado", 0, 2), ("Planta", 0, 1), ("Lateral", 1, 2)]
        blocks = []
        for index, (name, u, v) in enumerate(views):
            x = 35 + index * 330
            y = 130
            w = dims[u] * scale
            h = dims[v] * scale
            blocks.append(
                f'<text x="{x}" y="100">{name}</text><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#d8e4e8" stroke="black"/><text x="{x}" y="{y + h + 22}">{dims[u]:g} × {dims[v]:g} {proposal.unit}</text>'
            )
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1020 460"><rect width="1020" height="460" fill="white"/><g font-family="sans-serif" font-size="14"><text x="20" y="30">{label} — PROPUESTA</text><text x="20" y="60">{text}</text>{"".join(blocks)}<text x="20" y="440">Geometría propuesta. Uniones y tolerancias pendientes.</text></g></svg>'
        (parts / f"{p.id}.svg").write_text(svg, encoding="utf8")
        if metric:
            import ezdxf

            doc = ezdxf.new("R2010")
            doc.units = 4
            msp = doc.modelspace()
            gap = max(dims) * 0.25
            offset = 0.0
            for name, u, v in views:
                w, h = dims[u], dims[v]
                msp.add_lwpolyline(
                    [(offset, 0), (offset + w, 0), (offset + w, h), (offset, h)],
                    close=True,
                )
                msp.add_text(
                    f"{name}: {w:g} x {h:g} mm (PROPUESTA)",
                    dxfattribs={
                        "height": max(dims) * 0.035,
                        "insert": (offset, -gap * 0.5),
                    },
                )
                offset += w + gap
            doc.saveas(parts / f"{p.id}.dxf")
    for n, (e, a) in enumerate(VIEWS):
        im, mask = render_assembly(proposal, elev=e, azim=a)
        im.save(destination / f"view-{n:02d}.png")
        Image.fromarray(mask.astype("uint8") * 255).save(
            destination / f"mask-{n:02d}.png"
        )
    render_assembly(proposal, exploded=True)[0].save(destination / "exploded.png")
    scene = {
        "state": "proposed" if proposal.components else "unavailable",
        "coordinate_system": "x-right_y-up_z-depth",
        "warnings": ["Diseño hipotético; no certificado para fabricación."],
        "assumptions": proposal.assumptions,
        "objects": [
            {
                "piece_id": p.id,
                "label": p.label,
                "position_mm": [
                    p.origin_mm[0],
                    p.origin_mm[2],
                    -p.origin_mm[1] - p.size_mm[1],
                ],
                "dimensions_mm": [p.size_mm[0], p.size_mm[2], p.size_mm[1]],
                "placement_status": "design_hypothesis",
                "evidence_ids": p.source_refs,
            }
            for p in proposal.components
        ]
        if metric
        else [],
    }
    (destination / "scene.json").write_text(
        json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf8"
    )
    # Prepared for retrieval consumers; importing these records must preserve their hypothesis status.
    records = [
        {
            "id": "assembly",
            "entity": "assembly",
            "provenance": "generated_design_hypothesis",
            "is_observed_evidence": False,
            "text": proposal.intended_use,
            "assumptions": proposal.assumptions,
            "missing_information": proposal.missing_information,
            "images": [f"view-{n:02d}.png" for n in range(len(VIEWS))],
            "unit": proposal.unit,
            "component_ids": [p.id for p in proposal.components],
        }
    ]
    records.extend(
        {
            "id": p.id,
            "entity": "component",
            "provenance": "generated_design_hypothesis",
            "is_observed_evidence": False,
            "text": p.label,
            "dimensions": p.size_mm,
            "unit": proposal.unit,
            "assumptions": p.assumptions,
            "source_refs": p.source_refs,
            "drawing": f"parts/{p.id}.svg",
        }
        for p in proposal.components
    )
    (destination / "retrieval-context.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf8",
    )
    return {
        "component_count": len(proposal.components),
        "metric_export_available": metric,
        "checks": checks,
    }
