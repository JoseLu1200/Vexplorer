import io
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.operacion.jobs import BoundedJobExecutor
from backend.app.reconstruction3d.router import create_reconstruction_router
from test_reconstruction3d_service import Provider, payload


def test_multiview_metadata_and_partial_result_survive_export_failure(
    tmp_path, monkeypatch
):
    import json
    import backend.app.reconstruction3d.router as module

    def fail(*args, **kwargs):
        raise RuntimeError("export failure")

    monkeypatch.setattr(module, "export_package", fail)

    def multi(run):
        c = context(run)
        c.visual_pages = c.visual_pages * 2
        return c

    executor = BoundedJobExecutor(1)
    provider = Provider(payload())
    app = FastAPI()
    app.include_router(
        create_reconstruction_router(
            root=tmp_path, context_loader=multi, provider=provider, executor=executor
        )
    )
    with TestClient(app) as client:
        job = client.post("/api/v1/runs/run-test/reconstruction", json={}).json()[
            "job_id"
        ]
        executor.shutdown()
        state = client.get(f"/api/v1/reconstruction/{job}").json()
        assert (
            state["status"] == "failed"
            and state["baseline"]["components"][0]["id"] == "p1"
        )
        assert state["partial_result_available"] is True
        items = provider.calls[0]["input_items"][-1]["content"]
        metadata = json.loads(
            next(
                x["text"].split(": ", 1)[1]
                for x in items
                if x.get("text", "").startswith("PUBLIC INPUT METADATA: ")
            )
        )
        assert "source_refs" not in metadata
        assert metadata["allowed_component_source_refs"] == ["input"]
        assert len(metadata["composite_views"]) == 2
        assert (
            metadata["composite_views"][0]["image_bounds_px"]
            != metadata["composite_views"][1]["image_bounds_px"]
        )


def context(run):
    if run != "run-test":
        raise KeyError(run)
    b = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(b, format="PNG")
    dim = SimpleNamespace(
        value_mm=100, model_dump=lambda **kw: {"value_mm": 100, "id": "d1"}
    )
    return SimpleNamespace(
        ledger_revision="r1",
        visual_pages=[
            SimpleNamespace(
                content=b.getvalue(), reference="page-1", sha256="sourcehash"
            )
        ],
        extraction=SimpleNamespace(dimensions=[dim]),
    )


def test_job_artifacts_and_no_missing_run_or_path_access(tmp_path):
    executor = BoundedJobExecutor(2)
    app = FastAPI()
    app.include_router(
        create_reconstruction_router(
            root=tmp_path,
            context_loader=context,
            provider=Provider(payload()),
            executor=executor,
        )
    )
    with TestClient(app) as client:
        assert (
            client.post("/api/v1/runs/missing/reconstruction", json={}).status_code
            == 404
        )
        response = client.post("/api/v1/runs/run-test/reconstruction", json={})
        assert response.status_code == 202
        job = response.json()["job_id"]
        for _ in range(100):
            status = client.get(f"/api/v1/reconstruction/{job}").json()
            if status["status"] not in ("queued", "running"):
                break
            time.sleep(0.02)
        assert status["status"] == "needs_review"
        assert (
            client.get(f"/api/v1/reconstruction/{job}/artifacts/assembly.glb").content[
                :4
            ]
            == b"glTF"
        )
        assert (
            client.get(
                f"/api/v1/reconstruction/{job}/artifacts/parts/p1.dxf"
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/reconstruction/{job}/artifacts/../status.json"
            ).status_code
            == 404
        )
        assert status["source_refs"] == ["page-1"]
    executor.shutdown()


def test_restart_marks_interrupted_and_disabled_model(tmp_path):
    import json

    p = tmp_path / "reconstruction" / ("a" * 32)
    p.mkdir(parents=True)
    (p / "status.json").write_text(json.dumps({"status": "running"}))
    executor = BoundedJobExecutor(1)
    app = FastAPI()
    app.include_router(
        create_reconstruction_router(
            root=tmp_path, context_loader=context, provider=None, executor=executor
        )
    )
    with TestClient(app) as client:
        assert (
            client.get("/api/v1/reconstruction/" + "a" * 32).json()["status"]
            == "interrupted"
        )
        assert (
            client.post("/api/v1/runs/run-test/reconstruction", json={}).status_code
            == 503
        )
    executor.shutdown()
