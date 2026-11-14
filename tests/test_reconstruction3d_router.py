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


class InlineExecutor:
    def reserve(self):
        return True

    def release(self):
        pass

    def submit_reserved(self, fn):
        fn()


def test_refinement_freezes_source_inherits_answers_and_preserves_parent(tmp_path):
    import json

    calls = []

    def load(run):
        calls.append(run)
        return context(run)

    provider = Provider(payload())
    app = FastAPI()
    app.include_router(
        create_reconstruction_router(
            root=tmp_path,
            context_loader=load,
            provider=provider,
            executor=InlineExecutor(),
        )
    )
    with TestClient(app) as client:
        root = client.post("/api/v1/runs/run-test/reconstruction", json={}).json()[
            "job_id"
        ]
        original = client.get(f"/api/v1/reconstruction/{root}").json()
        r = client.post(
            f"/api/v1/reconstruction/{root}/refine",
            json={
                "answers": [
                    {"question": "function", "answer": "Separador de escritorio"}
                ],
                "envelope_mm": {"width": 100},
                "intended_use": "Separador",
            },
        )
        assert r.status_code == 202, r.text
        child = client.get(f"/api/v1/reconstruction/{r.json()['job_id']}").json()
        assert child["status"] == "needs_review"
        assert child["parent_job_id"] == root and child["revision"] == 2
        assert child["source_sha256"] == original["source_sha256"]
        assert child["clarifications"][0]["answer"] == "Separador de escritorio"
        assert child["envelope_mm"] == {"width": 100}
        r2 = client.post(
            f"/api/v1/reconstruction/{child['job_id']}/refine",
            json={"intended_use": "Separador móvil"},
        )
        assert r2.status_code == 202
        next_state = client.get(f"/api/v1/reconstruction/{r2.json()['job_id']}").json()
        assert next_state["clarifications"] == child["clarifications"]
        assert next_state["envelope_mm"] == child["envelope_mm"]
        assert calls == ["run-test"], "Refine must not load possibly changed source"
        assert client.get(f"/api/v1/reconstruction/{root}").json() == original
        assert json.loads(
            (tmp_path / "reconstruction" / root / "input-context.json").read_text()
        )


def test_refinement_rejects_bad_questions_blank_answers_and_changed_source(tmp_path):
    provider = Provider(payload())
    app = FastAPI()
    app.include_router(
        create_reconstruction_router(
            root=tmp_path,
            context_loader=context,
            provider=provider,
            executor=InlineExecutor(),
        )
    )
    with TestClient(app) as client:
        job = client.post("/api/v1/runs/run-test/reconstruction", json={}).json()[
            "job_id"
        ]
        n = len(provider.calls)
        url = f"/api/v1/reconstruction/{job}/refine"
        for body in (
            {},
            {"answers": [{"question": "function", "answer": " "}]},
            {"answers": [{"question": "unknown", "answer": "yes"}]},
            {"envelope_mm": {"width": -1}},
            {
                "answers": [
                    {"question": "function", "answer": "a"},
                    {"question": "function", "answer": "b"},
                ]
            },
        ):
            assert client.post(url, json=body).status_code == 422
        (tmp_path / "reconstruction" / job / "source.png").write_bytes(b"tampered")
        assert client.post(url, json={"intended_use": "desk"}).status_code == 409
        assert len(provider.calls) == n


def test_refinement_unscaled_abstention_can_gain_user_scale(tmp_path):
    provider = Provider(
        {
            "status": "insufficient_evidence",
            "intended_use": "desconocido",
            "unit": "relative",
            "components": [],
            "assumptions": [],
            "missing_information": ["function"],
            "functional_notes": [],
        }
    )

    def unscaled(run):
        c = context(run)
        c.extraction.dimensions = []
        return c

    app = FastAPI()
    app.include_router(
        create_reconstruction_router(
            root=tmp_path,
            context_loader=unscaled,
            provider=provider,
            executor=InlineExecutor(),
        )
    )
    with TestClient(app) as client:
        job = client.post("/api/v1/runs/run-test/reconstruction", json={}).json()[
            "job_id"
        ]
        provider.data = payload("relative")
        response = client.post(
            f"/api/v1/reconstruction/{job}/refine", json={"intended_use": "Panel"}
        )
        child = client.get(f"/api/v1/reconstruction/{response.json()['job_id']}").json()
        assert child["unit"] == "relative" and "assembly.glb" not in child["artifacts"]
        provider.data = payload()
        response = client.post(
            f"/api/v1/reconstruction/{job}/refine", json={"envelope_mm": {"width": 100}}
        )
        metric = client.get(
            f"/api/v1/reconstruction/{response.json()['job_id']}"
        ).json()
        assert metric["unit"] == "mm" and metric["status"] == "needs_review"
        assert metric["outcome"]["user_declarations"]["is_observed_in_drawing"] is False
        assert metric["certified_for_manufacturing"] is False


def test_refinement_rejects_active_legacy_context_tamper_and_revision_limit(tmp_path):
    import json

    provider = Provider(payload())
    app = FastAPI()
    app.include_router(
        create_reconstruction_router(
            root=tmp_path,
            context_loader=context,
            provider=provider,
            executor=InlineExecutor(),
        )
    )
    with TestClient(app) as client:
        job = client.post("/api/v1/runs/run-test/reconstruction", json={}).json()[
            "job_id"
        ]
        dest = tmp_path / "reconstruction" / job
        initial = json.loads((dest / "status.json").read_text())
        n = len(provider.calls)
        for changes, code in [
            ({"status": "running"}, "parent_not_finished"),
            (
                {"refinement_supported": False},
                "regenerate_original_to_enable_refinement",
            ),
            ({"revision": 11}, "refinement_limit_reached"),
        ]:
            (dest / "status.json").write_text(json.dumps({**initial, **changes}))
            r = client.post(
                f"/api/v1/reconstruction/{job}/refine", json={"intended_use": "desk"}
            )
            assert r.status_code == 409 and r.json()["detail"] == code
        (dest / "status.json").write_text(json.dumps(initial))
        (dest / "input-context.json").write_text("{}")
        r = client.post(
            f"/api/v1/reconstruction/{job}/refine", json={"intended_use": "desk"}
        )
        assert r.status_code == 409 and r.json()["detail"] == "frozen_input_changed"
        assert len(provider.calls) == n


def test_previous_answer_can_be_corrected_after_question_disappears_and_exports_provenance(
    tmp_path,
):
    provider = Provider(payload())
    app = FastAPI()
    app.include_router(
        create_reconstruction_router(
            root=tmp_path,
            context_loader=context,
            provider=provider,
            executor=InlineExecutor(),
        )
    )
    with TestClient(app) as client:
        job = client.post("/api/v1/runs/run-test/reconstruction", json={}).json()[
            "job_id"
        ]
        provider.data["missing_information"] = ["mounting"]
        child = client.post(
            f"/api/v1/reconstruction/{job}/refine",
            json={
                "answers": [{"question": "function", "answer": "Desk divider"}],
                "envelope_mm": {"width": 100},
            },
        ).json()["job_id"]
        corrected = client.post(
            f"/api/v1/reconstruction/{child}/refine",
            json={"answers": [{"question": "function", "answer": "Privacy screen"}]},
        )
        assert corrected.status_code == 202
        state = client.get(
            f"/api/v1/reconstruction/{corrected.json()['job_id']}"
        ).json()
        assert state["clarifications"] == [
            {"question": "function", "answer": "Privacy screen"}
        ]
        assert (
            client.get(f"/api/v1/reconstruction/{child}").json()["clarifications"][0][
                "answer"
            ]
            == "Desk divider"
        )
        manifest = client.get(
            f"/api/v1/reconstruction/{state['job_id']}/artifacts/revision.json"
        )
        assert manifest.status_code == 200
        exported = manifest.json()
        assert exported["source_sha256"] == state["source_sha256"]
        assert exported["parent_job_id"] == child and exported["revision"] == 3
        assert exported["user_declarations"]["envelope_mm"] == {"width": 100}
        assert exported["user_declarations"]["answers"] == state["clarifications"]
        assert exported["user_declarations"]["is_observed_in_drawing"] is False
