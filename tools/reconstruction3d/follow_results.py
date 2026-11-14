"""Complete rendering and evaluator outputs as the local Idol batch finishes."""

import argparse
import json
from pathlib import Path
import time
from .splats import render_folder
from .gallery import build
from .evaluate import evaluate
from .jev import run as run_jev


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--credential-file", type=Path, required=True)
    a = p.parse_args()
    for attempt in range(360):
        for path in sorted(a.root.glob("results/*/*/seed-*/run.json")):
            folder = path.parent
            if not (folder / "diagnostic-views/renderer.json").exists():
                print("Render", folder, flush=True)
                render_folder(folder)
        run_jev(a.root, a.credential_file)
        build(a.root)
        report = evaluate(a.root)
        completed = sum(x["status"] in ("generated", "failed") for x in report["idol"])
        (a.root / "evaluation-current.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
        )
        print("Completed Idol arms", completed, "/18", flush=True)
        if completed == 18:
            with (a.root / "evaluation-final.json").open("x", encoding="utf8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            break
        time.sleep(30)
