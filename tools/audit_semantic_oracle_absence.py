"""Audit source trees for exact recipes held in a private semantic design spec."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


_TEXT_SUFFIXES = {".py", ".md", ".json", ".js", ".html", ".css", ".toml", ".txt"}


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("(", "[").replace(")", "]")


def audit_oracle_absence(private_spec: Path, source_roots: tuple[Path, ...]) -> dict[str, int]:
    payload = json.loads(private_spec.read_text(encoding="utf-8"))
    designs = payload.get("designs") if isinstance(payload, dict) else None
    if not isinstance(designs, list) or not designs:
        raise ValueError("private design spec requires designs")
    files = sorted({
        path.resolve()
        for root in source_roots
        for path in ([root] if root.is_file() else root.rglob("*"))
        if path.is_file() and path.suffix.lower() in _TEXT_SUFFIXES
    })
    texts = {path: path.read_text(encoding="utf-8", errors="ignore") for path in files}
    compact = {path: _compact(text) for path, text in texts.items()}
    leaks: list[str] = []
    for design in designs:
        project_id = design.get("project_id")
        bounds = [
            _compact(json.dumps(item.get("bounds_mm"), separators=(",", ":")))
            for item in design.get("occurrences", [])
            if isinstance(item, dict)
        ]
        relation_recipe = _compact(
            json.dumps(design.get("relations", []), separators=(",", ":"))
        )
        for path, text in texts.items():
            if isinstance(project_id, str) and project_id in text:
                leaks.append(f"{path}:private_project_id")
                continue
            bounds_hits = sum(fragment in compact[path] for fragment in bounds)
            if bounds_hits >= 2 or (relation_recipe != "[]" and relation_recipe in compact[path]):
                leaks.append(f"{path}:private_recipe_fragments")
    if leaks:
        raise ValueError("private semantic oracle leaked into source: " + ", ".join(leaks))
    return {"files_scanned": len(files), "private_designs_checked": len(designs), "leaks": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-design-spec", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, action="append", required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_oracle_absence(args.private_design_spec, tuple(args.source_root))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(1, f"Oracle audit failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
