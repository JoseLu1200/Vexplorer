from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from tools.build_release import build_release


GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class ReleaseRehearsalError(ValueError):
    pass


def _git(repository: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseRehearsalError("git_check_failed") from exc
    return result.stdout.strip()


def assert_frozen_tree(repository: Path, expected_head: str) -> str:
    repository = repository.resolve()
    if GIT_SHA.fullmatch(expected_head) is None:
        raise ReleaseRehearsalError("invalid_expected_git_head")
    observed_head = _git(repository, "rev-parse", "HEAD")
    if observed_head != expected_head:
        raise ReleaseRehearsalError("unexpected_git_head")
    return observed_head


def rehearse(repository: Path, output: Path, expected_head: str) -> dict[str, object]:
    repository = repository.resolve()
    output = output.resolve()
    assert_frozen_tree(repository, expected_head)
    if output.exists():
        raise ReleaseRehearsalError("output_already_exists")
    first = build_release(repository, output / "build-a")
    second = build_release(repository, output / "build-b")
    if (
        first.candidate_id != second.candidate_id
        or first.payload_tree_sha256 != second.payload_tree_sha256
        or first.archive_sha256 != second.archive_sha256
        or first.archive.read_bytes() != second.archive.read_bytes()
    ):
        raise ReleaseRehearsalError("release_not_reproducible")
    receipt: dict[str, object] = {
        "schema_version": "1.0",
        "git_head": first.git_head,
        "candidate_id": first.candidate_id,
        "payload_tree_sha256": first.payload_tree_sha256,
        "archive_sha256": first.archive_sha256,
        "files": first.files,
        "archive_a": str(first.archive),
        "archive_b": str(second.archive),
        "byte_reproducible": True,
        "remote_actions": False,
    }
    receipt_path = output / "rehearsal.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build two byte-identical reviewed working-tree snapshots at one expected HEAD; never deploy."
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = rehearse(args.repository, args.output, args.expected_head)
    except ReleaseRehearsalError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
