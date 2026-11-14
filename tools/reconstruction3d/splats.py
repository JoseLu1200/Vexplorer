"""CPU orthographic diagnostic renderer for standard degree-zero 3DGS PLY.

Projects full anisotropic covariances and composites alpha back to front.
This is a diagnostic renderer, not mesh extraction or a physical measurement.
"""

from pathlib import Path
import json
import numpy as np
from PIL import Image
from backend.app.reconstruction3d.artifacts import camera_basis, VIEWS


def read_ply(path):
    with Path(path).open("rb") as f:
        header = []
        for _ in range(100):
            line = f.readline().decode("ascii").strip()
            header.append(line)
            if line == "end_header":
                break
        else:
            raise ValueError("invalid_ply_header")
        if "format binary_little_endian 1.0" not in header:
            raise ValueError("expected_binary_little_endian")
        n = int(next(v.split()[-1] for v in header if v.startswith("element vertex ")))
        props = [v.split()[-1] for v in header if v.startswith("property float ")]
        if len(props) != 17 or not 1 <= n <= 1_048_576:
            raise ValueError("unsupported_ply_layout")
        a = np.frombuffer(f.read(n * 17 * 4), dtype="<f4").reshape(n, 17).astype(float)
    if not np.isfinite(a).all():
        raise ValueError("nonfinite_ply")
    values = {k: a[:, i] for i, k in enumerate(props)}
    return values


def gaussian_arrays(values):
    xyz = np.column_stack([values[k] for k in ("x", "y", "z")])
    q = np.column_stack([values[f"rot_{i}"] for i in range(4)])
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    w, x, y, z = q.T
    rot = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    ).transpose(2, 0, 1)
    undo = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    xyz = xyz @ undo.T
    rot = np.einsum("ij,njk->nik", undo, rot)
    scales = np.exp(
        np.clip(np.column_stack([values[f"scale_{i}"] for i in range(3)]), -15, 2)
    )
    covariance = np.einsum("nij,nj,nkj->nik", rot, scales**2, rot)
    alpha = 1 / (1 + np.exp(-np.clip(values["opacity"], -50, 50)))
    colors = np.clip(
        np.column_stack([values[f"f_dc_{i}"] for i in range(3)]) * 0.28209479177387814
        + 0.5,
        0,
        1,
    )
    keep = alpha >= 0.01
    xyz, covariance, alpha, colors = (
        xyz[keep],
        covariance[keep],
        alpha[keep],
        colors[keep],
    )
    if not len(xyz):
        raise ValueError("empty_visible_splat")
    core = xyz[alpha >= 0.1] if np.any(alpha >= 0.1) else xyz
    lo, hi = np.quantile(core, [0.005, 0.995], axis=0)
    mid = (lo + hi) / 2
    span = max(float(np.max(hi - lo)), 1e-6)
    return xyz - mid, covariance, alpha, colors, span


def render(arrays, *, elev=22, azim=-55, resolution=256):
    xyz, covariance, opacity, colors, span = arrays
    basis = camera_basis(elev, azim)
    scale = resolution / (span * 1.7)
    q = xyz @ basis.T
    screen = q[:, :2] * scale
    screen[:, 0] += resolution / 2
    screen[:, 1] = resolution / 2 - screen[:, 1]
    projection = basis[:2].copy() * scale
    projection[1] *= -1
    cov = (
        np.einsum("ij,njk,lk->nil", projection, covariance, projection)
        + np.eye(2)[None] * 0.3
    )
    rgb = np.ones((resolution, resolution, 3))
    coverage = np.zeros((resolution, resolution))
    for i in np.argsort(q[:, 2]):
        radius = np.minimum(96, 3 * np.sqrt(np.diag(cov[i])))
        lo = np.maximum(0, np.floor(screen[i] - radius).astype(int))
        hi = np.minimum(resolution - 1, np.ceil(screen[i] + radius).astype(int))
        if np.any(hi < lo):
            continue
        xx, yy = np.meshgrid(
            np.arange(lo[0], hi[0] + 1) + 0.5 - screen[i, 0],
            np.arange(lo[1], hi[1] + 1) + 0.5 - screen[i, 1],
        )
        c = cov[i]
        det = c[0, 0] * c[1, 1] - c[0, 1] * c[1, 0]
        if det <= 0:
            continue
        distance = (c[1, 1] * xx * xx - 2 * c[0, 1] * xx * yy + c[0, 0] * yy * yy) / det
        alpha = np.minimum(0.99, opacity[i] * np.exp(-0.5 * distance))
        alpha[distance > 9] = 0
        region = np.s_[lo[1] : hi[1] + 1, lo[0] : hi[0] + 1]
        rgb[region] = colors[i] * alpha[..., None] + rgb[region] * (
            1 - alpha[..., None]
        )
        coverage[region] = alpha + coverage[region] * (1 - alpha)
    return Image.fromarray(np.clip(rgb * 255, 0, 255).astype("uint8")), coverage > 0.5


def render_folder(folder):
    arrays = gaussian_arrays(read_ply(folder / "model.ply"))
    destination = folder / "diagnostic-views"
    if (destination / "renderer.json").exists():
        return
    destination.mkdir(exist_ok=True)
    for n, (e, a) in enumerate(VIEWS):
        image, mask = render(arrays, elev=e, azim=a)
        image.save(destination / f"view-{n:02d}.png")
        Image.fromarray(mask.astype("uint8") * 255).save(
            destination / f"mask-{n:02d}.png"
        )
    (destination / "renderer.json").write_text(
        json.dumps(
            {
                "method": "orthographic anisotropic Gaussian alpha compositing",
                "resolution": 256,
                "alpha_threshold": 0.5,
                "min_opacity": 0.01,
                "center_bounds_quantiles": [0.005, 0.995],
                "max_footprint_radius_px": 96,
                "frame": "SDK z-up restored from PLY",
                "physical_scale": False,
                "limitations": "independent robust bbox fit; no camera-pose alignment; orthographic approximation; no surfaces or components",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    a = p.parse_args()
    for path in sorted(a.root.glob("results/*/*/seed-*/model.ply")):
        print(path.parent, flush=True)
        render_folder(path.parent)
