from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backup_timer_quiesces_only_vexplorer_and_restarts_it() -> None:
    service = (
        ROOT / "deploy/systemd-user/vexplorer-backup.service"
    ).read_text(encoding="utf-8")
    timer = (
        ROOT / "deploy/systemd-user/vexplorer-backup.timer"
    ).read_text(encoding="utf-8")

    assert "--check-idle-only" in service
    assert "systemctl --user stop vexplorer.service" in service
    assert "--quiescent" in service
    assert "systemctl --user start vexplorer.service" in service
    assert "ReadWritePaths=%h/apps/vexplorer/shared/backups" in service
    assert "ReadWritePaths=%h/apps/vexplorer/shared/data" not in service
    assert "--max-total-bytes 2147483648" in service
    assert "--min-free-bytes 1073741824" in service
    assert "docker" not in service.lower()
    assert "OnCalendar=" in timer
    assert "Persistent=true" in timer


def test_release_builder_requires_all_frontend_surfaces_and_excludes_tests() -> None:
    builder = (ROOT / "deploy/build-release.ps1").read_text(encoding="utf-8")

    for required in (
        "frontend/index.html",
        "frontend/app.js",
        "frontend/explorer.html",
        "frontend/explorer.js",
        "frontend/explorer.css",
        "frontend/vendor/three/LICENSE",
        "tools/backup_rotate.py",
    ):
        assert required in builder
    assert '($_ -notlike "frontend/tests/*")' in builder
    assert "git -C $repo archive" in builder


def test_systemd_environment_example_uses_runtime_names_and_public_limits() -> None:
    example = (
        ROOT / "deploy/systemd-production.env.example"
    ).read_text(encoding="utf-8")

    assert "VEXPLORER_DATA_DIR=/home/kripta/apps/vexplorer/shared/data" in example
    assert "VEXPLORER_COST_CATALOG=/home/kripta/apps/vexplorer/shared/config/cost-catalog.json" in example
    assert "VEXPLORER_AUTH_ENABLED=false" in example
    assert "VEXPLORER_GENERAL_JOB_TIMEOUT_SECONDS=600" in example
    assert "VEXPLORER_GENERAL_REVIEW_MAX_SEMANTIC_REPAIRS=2" in example
    assert "VEXPLORER_PUBLIC_LIVE_DAILY_LIMIT=10" in example
    assert "VEXPLORER_PUBLIC_LIVE_CLIENT_DAILY_LIMIT=3" in example
    assert "VEXPLORER_USERS_FILE_HOST" not in example
    assert "VEXPLORER_COST_CATALOG_HOST" not in example
