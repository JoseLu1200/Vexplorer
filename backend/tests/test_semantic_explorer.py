from io import BytesIO

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from backend.app.semantic_explorer.core import make_snapshot, search
from backend.app.semantic_explorer.models import Bundle, Entry, Space
from backend.app.semantic_explorer.store import ExplorerStore


def bundle(vectors=((1, 0, 0), (0.8, 0.6, 0), (0, 1, 0)), **kwargs):
    return Bundle(
        space=Space(
            provider="test",
            model="fixture",
            revision="v1",
            mode="text",
            dimensions=3,
            preprocessing="fixture-v1",
        ),
        entries=tuple(
            Entry(id=f"p{i}", label=f"Pieza {i}", vector=v)
            for i, v in enumerate(vectors)
        ),
        **kwargs,
    )


def png():
    output = BytesIO()
    Image.new("RGB", (12, 12), "white").save(output, format="PNG")
    return output.getvalue()


def test_neighbors_use_original_cosine_not_projection_and_stable_ties():
    value = bundle(((1, 0, 0), (0.8, 0.6, 0), (0.8, -0.6, 0), (0, 1, 0)))
    result = search(value, "p0", 3)
    assert [r["id"] for r in result] == ["p1", "p2", "p3"]
    assert [r["cosine"] for r in result] == pytest.approx([0.8, 0.8, 0])


@pytest.mark.parametrize(
    "vectors", [(), ((1, 0, 0),), ((1, 0, 0), (1, 0, 0)), ((1, 0, 0), (-1, 0, 0))]
)
def test_projection_handles_empty_small_and_degenerate_without_jitter(vectors):
    snapshot = make_snapshot(bundle(vectors), "fixture")
    assert len(snapshot["points"]) == len(vectors)
    assert all(np.isfinite([p["x"], p["y"]]).all() for p in snapshot["points"])
    if len(vectors) < 2 or len(set(vectors)) == 1:
        assert all(p["x"] == p["y"] == 0 for p in snapshot["points"])
    assert "vector" not in str(snapshot["points"])


@pytest.mark.parametrize("vectors", [((0, 0, 0),), ((float("nan"), 1, 0),), ((1, 0),)])
def test_invalid_vectors_rejected(vectors):
    with pytest.raises(ValidationError):
        bundle(vectors)


def test_duplicate_ids_rejected_and_space_revision_changes_snapshot():
    value = bundle()
    with pytest.raises(ValidationError):
        Bundle(space=value.space, entries=(value.entries[0], value.entries[0]))
    changed = value.model_copy(
        update={"space": value.space.model_copy(update={"revision": "v2"})}
    )
    assert (
        make_snapshot(value, "x")["snapshot_id"]
        != make_snapshot(changed, "x")["snapshot_id"]
    )
    assert (
        make_snapshot(value, "x")["snapshot_id"]
        != make_snapshot(value, "y")["snapshot_id"]
    )


def test_atomic_activation_retirement_and_rollback_do_not_restore_member(tmp_path):
    store = ExplorerStore(tmp_path / "explorer.sqlite3")
    first = store.publish("test", bundle(), {})
    second = store.publish("test", bundle(((1, 0, 0), (0, 1, 0))), {})
    store.activate("test", first)
    assert len(store.load("test")[1].entries) == 3
    store.retire("test", "p0")
    store.activate("test", second)
    store.activate("test", first)
    assert [e.id for e in store.load("test")[1].entries] == ["p1", "p2"]
    with pytest.raises(KeyError):
        store.activate("test", "missing")
    assert store.load("test")[0] == first


def test_corrupt_release_fails_closed_and_png_is_verified(tmp_path):
    store = ExplorerStore(tmp_path / "explorer.sqlite3")
    value = bundle()
    with pytest.raises(ValueError, match="image"):
        store.publish("bad", value, {"p0": b"<svg onload='alert(1)'/>"})
    release = store.publish("test", value, {"p0": png()})
    store.activate("test", release)
    assert store.image("test", "p0") == png()
    store.retire("test", "p0")
    with pytest.raises(KeyError):
        store.image("test", "p0")
    with store.connect() as db:
        db.execute("UPDATE releases SET payload='{}' WHERE id=?", (release,))
    with pytest.raises(ValueError, match="corrupt"):
        store.load("test")


def test_projection_persisted_and_snapshot_invalidated_on_metadata_change(tmp_path):
    store = ExplorerStore(tmp_path / "explorer.sqlite3")
    value = bundle()
    snapshot = store.snapshot(value, "library:test")
    assert store.snapshot(value, "library:test") == snapshot
    changed_entry = value.entries[0].model_copy(update={"label": "Revisado"})
    changed = value.model_copy(update={"entries": (changed_entry, *value.entries[1:])})
    assert (
        store.snapshot(changed, "library:test")["snapshot_id"]
        != snapshot["snapshot_id"]
    )


def test_cosine_near_ties_keep_actual_numeric_order():
    high = 0.8 + 2e-13
    value = bundle(((1, 0, 0), (0.8, 0.6, 0), (high, np.sqrt(1 - high**2), 0)))
    assert [r["id"] for r in search(value, "p0", 2)] == ["p2", "p1"]


@pytest.mark.parametrize("corruption", ["other_snapshot", "coordinate", "invalid_json"])
def test_projection_cache_corruption_is_rebuilt(tmp_path, corruption):
    import json

    store = ExplorerStore(tmp_path / "store.sqlite3")
    original = store.snapshot(bundle(), "one")
    if corruption == "other_snapshot":
        payload = json.dumps(store.snapshot(bundle(((1, 0, 0),)), "two"))
    elif corruption == "coordinate":
        altered = json.loads(json.dumps(original))
        altered["points"][0]["x"] = 9000
        payload = json.dumps(altered)
    else:
        payload = "broken"
    with store.connect() as db:
        db.execute(
            "UPDATE projections SET payload=? WHERE id=?",
            (payload, original["snapshot_id"]),
        )
    assert store.snapshot(bundle(), "one") == original


def test_activation_compare_and_swap_preserves_newer_release(tmp_path):
    store = ExplorerStore(tmp_path / "store.sqlite3")
    first = store.publish("test", bundle(), {})
    second = store.publish("test", bundle(((1, 0, 0),)), {})
    store.activate("test", first)
    store.activate("test", second)
    with pytest.raises(ValueError, match="active_release_changed"):
        store.activate("test", first, expected_release=first)
    assert store.load("test")[0] == second


def test_bulk_images_check_release_hashes_and_retirement(tmp_path):
    store = ExplorerStore(tmp_path / "store.sqlite3")
    release = store.publish("test", bundle(), {"p0": png(), "p1": png()})
    store.activate("test", release)
    store.retire("test", "p0")
    assert store.active_images("test", release) == {"p1": png()}
    with pytest.raises(ValueError, match="active_release_changed"):
        store.active_images("test", "other")
    with store.connect() as db:
        db.execute("UPDATE images SET content=? WHERE member_id='p1'", (b"broken",))
    with pytest.raises(ValueError, match="corrupt_image"):
        store.active_images("test", release)
