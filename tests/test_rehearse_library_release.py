from __future__ import annotations

import subprocess

import pytest

from tools.rehearse_library_release import ReleaseRehearsalError, assert_frozen_tree


def _repository(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "release@example.invalid"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Release Test"], cwd=repository, check=True)
    (repository / "tracked.txt").write_text("frozen\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "frozen"], cwd=repository, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, text=True, capture_output=True
    ).stdout.strip()
    return repository, head


def test_frozen_tree_requires_exact_clean_commit(tmp_path) -> None:
    repository, head = _repository(tmp_path)

    assert assert_frozen_tree(repository, head) == head


def test_snapshot_gate_rejects_wrong_commit_but_allows_reviewed_dirty_tree(tmp_path) -> None:
    repository, head = _repository(tmp_path)
    with pytest.raises(ReleaseRehearsalError, match="unexpected_git_head"):
        assert_frozen_tree(repository, "0" * 40)

    (repository / "untracked.txt").write_text("not frozen\n", encoding="utf-8")
    assert assert_frozen_tree(repository, head) == head
