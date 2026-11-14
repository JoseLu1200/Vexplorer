from backend.app.semantic_explorer.store import ExplorerStore
from backend.tests.test_semantic_explorer import bundle
from tests.test_backup import _create_live_data_dir
from tools.backup import create_backup, restore_backup


def test_backup_restores_release_pointer_and_tombstones(tmp_path):
    source = tmp_path / "source"
    _create_live_data_dir(source).close()
    store = ExplorerStore(source / "semantic_explorer.sqlite3")
    release = store.publish("test", bundle(), {})
    store.activate("test", release)
    store.retire("test", "p0")
    create_backup(source, tmp_path / "backup.zip")
    restored = tmp_path / "restored"
    restore_backup(tmp_path / "backup.zip", restored)
    recovered = ExplorerStore(restored / "semantic_explorer.sqlite3")
    assert recovered.load("test")[0] == release
    recovered.activate("test", release)
    assert all(e.id != "p0" for e in recovered.load("test")[1].entries)
