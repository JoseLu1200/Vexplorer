import numpy as np
from tools.reconstruction3d.splats import gaussian_arrays, render


def test_anisotropic_gaussian_renders_covariance_and_opacity():
    # PLY y-up represents a z-up cloud after the documented SDK rotation.
    values = {
        k: np.zeros(2)
        for k in [
            "x",
            "y",
            "z",
            "opacity",
            *[f"f_dc_{i}" for i in range(3)],
            *[f"scale_{i}" for i in range(3)],
            *[f"rot_{i}" for i in range(4)],
        ]
    }
    values["x"] = np.array([-0.2, 0.2])
    values["rot_0"][:] = 1
    values["opacity"][:] = 5
    for i in range(3):
        values[f"scale_{i}"][:] = np.log(0.02 if i else 0.08)
    arrays = gaussian_arrays(values)
    image, mask = render(arrays, elev=0, azim=-90, resolution=128)
    ys, xs = np.where(mask)
    assert len(xs) > 100 and np.ptp(xs) > np.ptp(ys) * 2
    assert np.asarray(image)[mask].mean() < 250
