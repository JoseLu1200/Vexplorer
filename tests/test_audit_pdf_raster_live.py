from __future__ import annotations

import httpx

from tools.audit_pdf_raster_live import run_acceptance


def test_http_acceptance_persists_complete_path_without_metric_dimensions(tmp_path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-raster-fixture")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/documents":
            return httpx.Response(201, json={"data": {
                "document_id": "doc-parent", "ingestion": {"state": "needs_review"},
            }})
        if path == "/api/v1/documents/doc-parent/pdf-pages/1/normalize":
            return httpx.Response(200, json={"data": {
                "document_id": "doc-child",
                "ingestion": {
                    "state": "needs_review", "scale_provenance": None,
                    "capabilities": {"geometry_analysis": False},
                },
            }})
        if path == "/api/v1/jobs" and request.method == "POST":
            return httpx.Response(202, json={"data": {"id": "job-1"}})
        if path == "/api/v1/jobs/job-1":
            return httpx.Response(200, json={"data": {
                "id": "job-1", "state": "succeeded", "run_id": "run-1", "error": None,
            }})
        if path == "/api/v1/runs/run-1/general":
            unknown = {"state": "unknown", "value_mm": None}
            return httpx.Response(200, json={"data": {
                "status": "reviewed_incomplete", "proposal_revision": 1, "review_revision": 1,
                "draft": {"components": [{
                    "id": "visual-part", "source_view_ids": [],
                    "source_document_refs": ["document:doc-child"],
                    "length": unknown, "width": unknown, "thickness": unknown,
                }]},
            }})
        if path == "/api/v1/runs/run-1/general/derived":
            return httpx.Response(200, json={"data": {"package": {
                "status": "incomplete", "bom_rows": [{"component_id": "visual-part"}],
                "scene": {"status": "schematic_incomplete"},
                "cost_basis": {"status": "partial"},
            }}})
        return httpx.Response(404, json={"error": "unexpected"})

    with httpx.Client(
        base_url="http://acceptance.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        report = run_acceptance(client, source, poll_interval_s=0)

    assert report["job"]["state"] == "succeeded"
    assert report["child"]["geometry_analysis"] is False
    assert report["general"]["components"][0]["source_view_ids"] == []
    assert report["general"]["components"][0]["dimension_values_mm"] == {
        "length": None, "width": None, "thickness": None,
    }
    assert report["derived"] == {
        "package_status": "incomplete", "bom_row_count": 1,
        "scene_status": "schematic_incomplete", "cost_basis_status": "partial",
    }
