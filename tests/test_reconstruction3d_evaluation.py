from backend.app.reconstruction3d.models import AssemblyProposal
from tools.reconstruction3d.evaluate import material_iou
from test_reconstruction3d_service import payload


def test_private_reference_hashes_reject_tampering(tmp_path):
    import pytest
    from tools.reconstruction3d.integrity import freeze_references, validate_references

    refs = tmp_path / "references"
    refs.mkdir()
    (refs / "proposal.json").write_text("{}")
    freeze_references(tmp_path, stage="before_inference")
    assert validate_references(tmp_path)["capture_stage"] == "before_inference"
    (refs / "proposal.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="reference_hash_mismatch"):
        validate_references(tmp_path)


def test_boundary_distance_is_zero_for_identity_and_positive_for_translation():
    import numpy as np
    from tools.reconstruction3d.evaluate import boundary_error

    a = np.zeros((64, 64), bool)
    a[10:30, 10:30] = True
    assert boundary_error(a, a) == 0
    assert boundary_error(a, np.roll(a, 3, axis=1)) > 0
    assert boundary_error(a, np.zeros_like(a)) is None


def test_material_volume_detects_hollow_shape_change_and_ignores_translation():
    p = AssemblyProposal.model_validate(payload())
    q = p.model_copy(deep=True)
    q.components[0].origin_mm = [100, 200, 300]
    assert material_iou(p, q) == 1
    q.components[0].size_mm = [100, 40, 200]
    assert material_iou(p, q) == 0.5


def test_overlapping_parts_cannot_receive_exact_union_volume_score():
    p = AssemblyProposal.model_validate(payload())
    q = p.model_copy(deep=True)
    q.components.append(q.components[0].model_copy(update={"id": "duplicate"}))
    assert material_iou(p, q) is None
