from __future__ import annotations

import pymupdf
from fastapi.testclient import TestClient

from backend.app.main import create_app


def _vector_and_raster_pdf() -> bytes:
    document = pymupdf.open()
    vector = document.new_page(width=300, height=100)
    vector.draw_rect((20, 20, 180, 80))
    vector.insert_text((24, 45), "DO NOT SCALE DRAWING")
    raster = document.new_page(width=100, height=100)
    ppm = b"P6\n2 2\n255\n" + bytes((0, 80, 160)) * 4
    raster.insert_image(raster.rect, stream=ppm)
    payload = document.tobytes()
    document.close()
    return payload


def _upload(client: TestClient) -> tuple[dict, bytes]:
    source = _vector_and_raster_pdf()
    response = client.post(
        "/api/v1/documents",
        files={"file": ("mixed.pdf", source, "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()["data"], source


def test_scaled_vector_child_preserves_page_provenance_and_scale_conflict_warnings(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none"))
    parent, source = _upload(client)

    assert parent["artifacts"]["normalized_dxf"] is None
    assert [page["content_kind"] for page in parent["artifacts"]["pages"]] == ["vector", "raster"]
    selected = client.post(
        f"/api/v1/documents/{parent['document_id']}/pages/1/select",
        json={
            "mm_per_pdf_point": 0.5,
            "confirmed_by": "technical-reviewer",
            "reason": "Scale checked against an explicit reference",
        },
    )

    assert selected.status_code == 200
    child = selected.json()["data"]
    assert child["source"]["parent_document_id"] == parent["document_id"]
    assert child["source"]["page_number"] == 1
    assert child["source"]["unit"] == "mm"
    assert child["artifacts"]["normalized_dxf"]["source_page"] == 1
    assert child["artifacts"]["normalized_dxf"]["unit"] == "mm"
    assert child["artifacts"]["pages"][0]["page_number"] == 1
    assert child["artifacts"]["pages"][0]["normalized_dxf"]["unit"] == "mm"
    assert child["ingestion"]["scale_provenance"]["confirmed_by"] == "technical-reviewer"
    assert "scale_conflicts_with_document_note:page=1:do_not_scale" in child["ingestion"]["warnings"]
    assert client.get(child["artifacts"]["original"]["url"]).content == source


def test_raster_page_creates_visual_review_child_without_cad_geometry(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none"))
    parent, _ = _upload(client)

    selected = client.post(
        f"/api/v1/documents/{parent['document_id']}/pages/2/select",
        json={"confirmed_by": "technical-reviewer", "reason": "Manual visual interpretation"},
    )

    assert selected.status_code == 200
    child = selected.json()["data"]
    assert child["ingestion"]["state"] == "needs_review"
    assert child["ingestion"]["capabilities"]["geometry_analysis"] is False
    assert child["ingestion"]["capabilities"]["visual_general_review"] is True
    assert child["artifacts"]["normalized_dxf"] is None
    preview = client.get(child["artifacts"]["preview"]["url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert child["audit"]["selected_by"] == "technical-reviewer"
    assert child["audit"]["selection_reason"] == "Manual visual interpretation"

    run = client.post(
        "/api/v1/runs",
        json={
            "document_id": child["document_id"],
            "mode": "geometry_only",
            "input_kind": "general_furniture",
        },
    )
    assert run.status_code == 201
