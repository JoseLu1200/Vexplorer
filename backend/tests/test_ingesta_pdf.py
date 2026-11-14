from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pymupdf
import pytest

from backend.app.ingesta.dxf_reader import parse_dxf
from backend.app.ingesta.pdf_reader import PdfIngestionError, PdfScaleConfirmation, ingest_pdf


def _vector_pdf(path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=72, height=144)
    page.draw_line((6, 12), (66, 12), width=0.5)
    page.insert_text((6, 30), "SIDE 500")
    document.save(path)
    document.close()
    return path


def _raster_pdf(path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=72, height=72)
    ppm = b"P6\n2 2\n255\n" + bytes((255, 0, 0)) * 4
    page.insert_image(page.rect, stream=ppm)
    document.save(path)
    document.close()
    return path


def test_vector_pdf_keeps_units_unknown_and_emits_nonmetric_dxf_without_scale(tmp_path: Path) -> None:
    result = ingest_pdf(_vector_pdf(tmp_path / "drawing.pdf"), tmp_path / "artifacts")

    assert result.source_unit == "unknown"
    assert result.unit_scale_to_mm is None
    assert result.scale_provenance is None
    assert result.status == "needs_review"
    page = result.pages[0]
    assert page.content_kind == "vector"
    assert (page.width_points, page.height_points) == pytest.approx((72, 144))
    assert page.width_mm is page.height_mm is None
    assert page.vector_paths and any(block.text == "SIDE 500" for block in page.text_blocks)
    assert page.preview_path.read_bytes().startswith(b"\x89PNG")
    assert page.normalized_layer == "PDF_PAGE_0001"
    assert page.normalized_dxf_path is not None
    normalized = parse_dxf(page.normalized_dxf_path)
    assert normalized.source_unit == "unknown"
    assert normalized.unit_scale_to_mm is None
    assert "source_unit_unknown" in result.warnings


def test_confirmed_pdf_scale_produces_metric_dxf_with_provenance(tmp_path: Path) -> None:
    scale = PdfScaleConfirmation(
        mm_per_pdf_point=0.5,
        confirmed_by="technical-reviewer",
        confirmed_at=datetime(2026, 11, 14, 10, 30, tzinfo=timezone.utc),
    )
    result = ingest_pdf(_vector_pdf(tmp_path / "scaled.pdf"), tmp_path / "artifacts", scale=scale)

    assert result.source_unit == "mm" and result.unit_scale_to_mm == 0.5
    assert result.scale_provenance == scale
    assert (result.pages[0].width_mm, result.pages[0].height_mm) == pytest.approx((36, 72))
    normalized = parse_dxf(result.pages[0].normalized_dxf_path)
    assert normalized.source_unit == "mm"
    line = next(entity for entity in normalized.entities if entity.kind == "LINE")
    assert line.points[0] == pytest.approx((3, 66))
    assert line.points[1] == pytest.approx((33, 66))


def test_raster_pdf_is_previewed_without_fake_geometry(tmp_path: Path) -> None:
    result = ingest_pdf(_raster_pdf(tmp_path / "scan.pdf"), tmp_path / "artifacts")

    page = result.pages[0]
    assert page.content_kind == "raster"
    assert not page.vector_paths
    assert page.image_count == 1
    assert page.preview_path.is_file()
    assert page.normalized_dxf_path is None
    assert "raster_page_requires_manual_review:1" in result.warnings


def test_invalid_pdf_and_page_overflow_are_rejected_before_rendering(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not a pdf")
    with pytest.raises(PdfIngestionError, match="cannot open PDF"):
        ingest_pdf(invalid, tmp_path / "invalid-artifacts")

    many = tmp_path / "many.pdf"
    document = pymupdf.open()
    document.new_page()
    document.new_page()
    document.save(many)
    document.close()
    with pytest.raises(PdfIngestionError, match="page limit exceeded"):
        ingest_pdf(many, tmp_path / "many-artifacts", max_pages=1)


def test_single_pdf_path_cannot_bypass_segment_budget(tmp_path: Path) -> None:
    source = tmp_path / "dense-path.pdf"
    document = pymupdf.open()
    page = document.new_page()
    shape = page.new_shape()
    shape.draw_polyline([(0, 0), (10, 0), (20, 0), (30, 0)])
    shape.finish()
    shape.commit()
    document.save(source)
    document.close()

    with pytest.raises(PdfIngestionError, match="vector segment limit exceeded"):
        ingest_pdf(source, tmp_path / "artifacts", max_segments_per_page=2)


def test_do_not_scale_note_is_preserved_as_conflict_warning(tmp_path: Path) -> None:
    source = tmp_path / "do-not-scale.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=72)
    page.draw_line((0, 0), (300, 72))
    page.insert_text((5, 20), "DO NOT SCALE DRAWING")
    document.save(source)
    document.close()
    scale = PdfScaleConfirmation(
        mm_per_pdf_point=1.0,
        confirmed_by="technical-reviewer",
        confirmed_at=datetime(2026, 11, 14, 10, 30, tzinfo=timezone.utc),
    )

    result = ingest_pdf(source, tmp_path / "artifacts", scale=scale)

    assert result.scale_provenance == scale
    assert "scale_conflicts_with_document_note:page=1:do_not_scale" in result.warnings
