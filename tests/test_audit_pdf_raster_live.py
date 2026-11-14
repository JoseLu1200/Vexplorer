from __future__ import annotations

import httpx
import pytest

from tools.audit_pdf_raster_live import run_acceptance


def _handler(
    *,
    dimension_state: str = "unknown",
    geometry_analysis: bool = False,
    scale_provenance=None,
    normalized_dxf=None,
):
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
                    "state": "needs_review", "scale_provenance": scale_provenance,
                    "capabilities": {"geometry_analysis": geometry_analysis},
                },
                "artifacts": {"normalized_dxf": normalized_dxf},
            }})
        if path == "/api/v1/jobs" and request.method == "POST":
            return httpx.Response(202, json={"data": {"id": "job-1"}})
        if path == "/api/v1/jobs/job-1":
            return httpx.Response(200, json={"data": {
                "id": "job-1", "state": "succeeded", "run_id": "run-1", "error": None,
            }})
        if path == "/api/v1/runs/run-1/general":
            dimension = {"state": dimension_state, "value_mm": None}
            return httpx.Response(200, json={"data": {
                "status": "reviewed_incomplete", "proposal_revision": 1, "review_revision": 1,
                "draft": {"components": [{
                    "id": "visual-part", "source_view_ids": [],
                    "source_document_refs": ["document:doc-child"],
                    "length": dimension, "width": dimension, "thickness": dimension,
                }]},
            }})
        if path == "/api/v1/runs/run-1/general/derived":
            return httpx.Response(200, json={"data": {"package": {
                "status": "incomplete", "bom_rows": [{"component_id": "visual-part"}],
                "scene": {"status": "schematic_incomplete"},
                "cost_basis": {"status": "partial"},
            }}})
        return httpx.Response(404, json={"error": "unexpected"})

    return handler


def test_http_acceptance_persists_complete_path_without_metric_dimensions(tmp_path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-raster-fixture")

    with httpx.Client(
        base_url="http://acceptance.test",
        transport=httpx.MockTransport(_handler()),
    ) as client:
        report = run_acceptance(client, source, poll_interval_s=0)

    assert report["job"]["state"] == "succeeded"
    assert report["child"]["geometry_analysis"] is False
    assert report["child"]["scale_provenance"] is None
    assert report["child"]["normalized_dxf"] is None
    assert report["general"]["components"][0]["source_view_ids"] == []
    assert report["general"]["components"][0]["dimension_values_mm"] == {
        "length": None, "width": None, "thickness": None,
    }
    assert report["derived"] == {
        "package_status": "incomplete", "bom_row_count": 1,
        "scene_status": "schematic_incomplete", "cost_basis_status": "partial",
    }


@pytest.mark.parametrize("dimension_state", ("conflict", "hypothesis"))
def test_http_acceptance_rejects_null_dimensions_not_marked_unknown(
    tmp_path, dimension_state
) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-raster-fixture")
    with httpx.Client(
        base_url="http://acceptance.test",
        transport=httpx.MockTransport(_handler(dimension_state=dimension_state)),
    ) as client, pytest.raises(
        AssertionError, match="raster_acceptance_metric_dimension_not_unknown"
    ):
        run_acceptance(client, source, poll_interval_s=0)


@pytest.mark.parametrize(
    ("geometry_analysis", "scale_provenance", "normalized_dxf"),
    (
        (True, None, None),
        (False, {"mm_per_pdf_point": 1.0}, None),
        (False, None, {"url": "/normalized.dxf", "unit": "mm"}),
    ),
)
def test_http_acceptance_rejects_metric_authority_for_unscaled_raster(
    tmp_path, geometry_analysis, scale_provenance, normalized_dxf
) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-raster-fixture")
    with httpx.Client(
        base_url="http://acceptance.test",
        transport=httpx.MockTransport(_handler(
            geometry_analysis=geometry_analysis,
            scale_provenance=scale_provenance,
            normalized_dxf=normalized_dxf,
        )),
    ) as client, pytest.raises(
        AssertionError, match="raster_acceptance_unexpected_metric_authority"
    ):
        run_acceptance(client, source, poll_interval_s=0)
