"""Expose frozen experimental B outputs in the real viewer on localhost.

The imported jobs are labelled study outputs. This does not insert them into
the app's observed evidence, historic prices, or confirmed manufacturing data.
"""

from pathlib import Path
import argparse
import json
from hashlib import sha256
from backend.app.reconstruction3d.artifacts import export_package
from backend.app.reconstruction3d.models import AssemblyProposal


def import_study(study, data):
    manifest = json.loads((study / "public-manifest.json").read_text())
    jobs = []
    for case in manifest["cases"]:
        source = study / "results" / "B" / case["id"] / "outcome.json"
        if not source.exists():
            continue
        outcome = json.loads(source.read_text(encoding="utf8"))
        job_id = sha256(
            (
                str(study.resolve())
                + case["id"]
                + sha256(source.read_bytes()).hexdigest()
            ).encode()
        ).hexdigest()[:32]
        dest = data / "reconstruction" / job_id
        if not dest.exists():
            dest.mkdir(parents=True)
            (dest / "source.png").write_bytes((study / case["input"]).read_bytes())
            export_package(
                AssemblyProposal.model_validate(outcome["proposal"]), dest / "artifacts"
            )
            state = {
                "job_id": job_id,
                "run_id": "study:" + case["id"],
                "status": outcome["status"],
                "source_refs": [case["input"]],
                "source_sha256": case["source_sha256"],
                "unit": case["unit"],
                "outcome": outcome,
                "study_output": True,
                "artifacts": sorted(
                    p.relative_to(dest / "artifacts").as_posix()
                    for p in (dest / "artifacts").rglob("*")
                    if p.is_file()
                ),
            }
            (dest / "status.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf8"
            )
        jobs.append(
            {
                "case_id": case["id"],
                "job_id": job_id,
                "path": f"/reconstruction.html?job={job_id}",
            }
        )
    (data / "study-jobs.json").write_text(json.dumps(jobs, indent=2))
    return jobs


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--study", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--port", type=int, default=8873)
    a = p.parse_args()
    print(json.dumps(import_study(a.study, a.data)), flush=True)
    from backend.app.main import create_app
    import uvicorn

    app = create_app(data_dir=a.data)
    from starlette.routing import Mount
    from fastapi.staticfiles import StaticFiles

    app.router.routes.insert(
        -1, Mount("/study", app=StaticFiles(directory=a.study, html=True))
    )
    uvicorn.run(app, host="127.0.0.1", port=a.port)
