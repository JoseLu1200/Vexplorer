from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

import ezdxf
import pymupdf
import pytest
from PIL import Image

from backend.app.general_furniture.visual_evidence import (
    VisualEvidenceArtifact,
    render_visual_evidence,
)
from backend.app.geometria.extraction import extract_drawing


def _dxf(path: Path, *, width: float, diagonal: bool = False) -> None:
    document = ezdxf.new("R2018")
    document.units = ezdxf.units.MM
    space = document.modelspace()
    space.add_lwpolyline(
        [(0, 0), (width, 0), (width, 40), (0, 40)], close=True
    )
    if diagonal:
        space.add_line((0, 0), (width, 40))
    document.saveas(path)


def _pdf(path: Path) -> None:
    document = pymupdf.open()
    first = document.new_page(width=200, height=100)
    first.draw_rect((10, 10, 190, 90), color=(1, 0, 0), width=4)
    second = document.new_page(width=120, height=240)
    second.draw_circle((60, 120), 40, color=(0, 0, 1), width=5)
    document.save(path)
    document.close()


def test_cad_artifacts_are_source_bound_bounded_and_geometry_specific(
    tmp_path: Path,
) -> None:
    rectangle = tmp_path / "rectangle.dxf"
    diagonal = tmp_path / "diagonal.dxf"
    _dxf(rectangle, width=100)
    _dxf(diagonal, width=100, diagonal=True)

    first = render_visual_evidence(
        rectangle,
        extraction=extract_drawing(rectangle, input_kind="general_furniture"),
        source_document_refs=("document:rectangle",),
        max_dimension_px=256,
    )
    second = render_visual_evidence(
        diagonal,
        extraction=extract_drawing(diagonal, input_kind="general_furniture"),
        source_document_refs=("document:diagonal",),
        max_dimension_px=256,
    )

    assert len(first) == len(second) == 1
    artifact = first[0]
    assert isinstance(artifact, VisualEvidenceArtifact)
    assert artifact.authority == "visual_context_not_measurement_source"
    assert artifact.media_type == "image/png"
    assert artifact.source_sha256 == sha256(rectangle.read_bytes()).hexdigest()
    assert artifact.image_sha256 == sha256(artifact.content).hexdigest()
    assert artifact.source_document_refs == ("document:rectangle",)
    assert artifact.source_view_ids == ("view-unknown",)
    assert artifact.source_contour_ids
    assert artifact.crop_bounds_source == (0.0, 0.0, 100.0, 40.0)
    assert max(artifact.width_px, artifact.height_px) <= 256
    with Image.open(BytesIO(artifact.content)) as image:
        image.load()
        assert image.format == "PNG"
        assert image.size == (artifact.width_px, artifact.height_px)
    assert artifact.image_sha256 != second[0].image_sha256
    assert artifact.reference != second[0].reference


def test_pdf_renders_only_selected_actual_page_with_page_provenance(
    tmp_path: Path,
) -> None:
    source = tmp_path / "two-pages.pdf"
    _pdf(source)

    artifacts = render_visual_evidence(
        source,
        selected_pdf_page=2,
        source_document_refs=("document:pdf", "artifact:original"),
        max_dimension_px=300,
    )

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.source_view_ids == ("pdf-page-0002",)
    assert artifact.source_contour_ids == ()
    assert artifact.source_document_refs == ("document:pdf", "artifact:original")
    assert artifact.crop_bounds_source == (0.0, 0.0, 120.0, 240.0)
    assert artifact.width_px == 150
    assert artifact.height_px == 300
    assert artifact.warnings == ("pdf_visual_context_only",)
    with Image.open(BytesIO(artifact.content)) as image:
        image.load()
        assert image.getpixel((75, 100)) != (255, 255, 255)


def test_rejects_budget_before_raster_and_requires_normalized_cad(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drawing.dxf"
    _dxf(source, width=100)
    extraction = extract_drawing(source, input_kind="general_furniture")

    with pytest.raises(ValueError, match="visual_evidence_budget_exceeded"):
        render_visual_evidence(
            source,
            extraction=extraction,
            max_dimension_px=256,
            max_total_pixels=65_535,
        )
    with pytest.raises(ValueError, match="visual_evidence_budget_exceeded"):
        render_visual_evidence(
            source,
            extraction=extraction,
            max_dimension_px=48,
        )
    with pytest.raises(ValueError, match="visual_evidence_budget_exceeded"):
        render_visual_evidence(
            source,
            extraction=extraction,
            max_total_png_bytes=1,
        )
    with pytest.raises(ValueError, match="normalized_dxf_required_for_dwg"):
        render_visual_evidence(tmp_path / "source.dwg", extraction=extraction)
    with pytest.raises(ValueError, match="selected_pdf_page_required"):
        pdf = tmp_path / "drawing.pdf"
        _pdf(pdf)
        render_visual_evidence(pdf)


def test_unknown_view_gets_clean_overview_and_gap_based_marked_regions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "three-projections.dxf"
    document = ezdxf.new("R2018")
    document.units = ezdxf.units.MM
    space = document.modelspace()
    for offset_x, offset_y, width, height in (
        (0, 0, 100, 50),
        (180, 0, 60, 50),
        (0, 140, 100, 30),
    ):
        space.add_lwpolyline(
            [
                (offset_x, offset_y),
                (offset_x + width, offset_y),
                (offset_x + width, offset_y + height),
                (offset_x, offset_y + height),
            ],
            close=True,
        )
    document.saveas(source)

    artifacts = render_visual_evidence(
        source,
        extraction=extract_drawing(source, input_kind="general_furniture"),
        max_dimension_px=300,
        max_total_pixels=4 * 300 * 300,
    )

    assert len(artifacts) == 4
    overview, *regions = artifacts
    assert overview.reference.endswith(":view:view-unknown:overview")
    assert "clean_source_overview" in overview.warnings
    assert {item.source_id for item in overview.marks} == set(
        overview.source_contour_ids
    )
    with Image.open(BytesIO(overview.content)) as image:
        assert (255, 235, 115) in set(image.getdata())
    assert [item.reference.rsplit(":", 1)[-1] for item in regions] == [
        "region-001",
        "region-002",
        "region-003",
    ]
    assert all(item.source_view_ids == ("view-unknown",) for item in regions)
    assert all(len(item.source_contour_ids) == 1 for item in regions)
    assert all("spatial_region_not_semantic_view" in item.warnings for item in regions)
    assert all(item.marks[0].mark_id == "M001" for item in regions)
    assert all(item.marks[0].source_kind == "contour" for item in regions)
    assert all(item.marks[0].source_id in item.source_contour_ids for item in regions)
    assert len({(item.reference, item.marks[0].mark_id) for item in regions}) == 3
    bounded = render_visual_evidence(
        source,
        extraction=extract_drawing(source, input_kind="general_furniture"),
        max_dimension_px=300,
        max_total_pixels=4 * 300 * 300,
        max_artifacts=3,
    )
    assert len(bounded) == 3
    assert "spatial_region_crops_truncated:2_of_3" in bounded[0].warnings
    assert "optional_region_crops_omitted:1" in bounded[0].warnings
    assert {item.source_id for item in bounded[0].marks} == set(
        bounded[0].source_contour_ids
    )
    assert [item.reference.rsplit(":", 1)[-1] for item in bounded[1:]] == [
        "region-001",
        "region-002",
    ]


def test_many_optional_regions_are_prioritized_deterministically_under_budget(
    tmp_path: Path,
) -> None:
    source = tmp_path / "five-regions.dxf"
    document = ezdxf.new("R2018")
    document.units = ezdxf.units.MM
    space = document.modelspace()
    for index, x in enumerate((0, 100, 200, 300, 400), start=1):
        for inset in range(index):
            offset = inset * 2
            space.add_lwpolyline(
                [
                    (x + offset, offset),
                    (x + 40 - offset, offset),
                    (x + 40 - offset, 40 - offset),
                    (x + offset, 40 - offset),
                ],
                close=True,
            )
    document.saveas(source)
    extraction = extract_drawing(source, input_kind="general_furniture")

    first = render_visual_evidence(
        source, extraction=extraction, max_dimension_px=256,
        max_total_pixels=4 * 256 * 256, max_artifacts=4,
    )
    second = render_visual_evidence(
        source, extraction=extraction, max_dimension_px=256,
        max_total_pixels=4 * 256 * 256, max_artifacts=4,
    )

    assert len(first) == 4
    assert [item.source_contour_ids for item in first] == [
        item.source_contour_ids for item in second
    ]
    assert [len(item.source_contour_ids) for item in first[1:]] == [5, 4, 3]
    assert "spatial_region_crops_truncated:3_of_5" in first[0].warnings


def test_all_layer_view_overviews_precede_optional_crop_selected_by_complexity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "layered-three-views.dxf"
    document = ezdxf.new("R2018")
    document.units = ezdxf.units.MM
    space = document.modelspace()
    for layer in ("ORTHO_FRONT", "ORTHO_TOP", "ORTHO_SIDE"):
        document.layers.add(layer)
        rectangles = [
            ((0, 0), (40, 20)),
            ((100, 0), (140, 20)),
        ]
        if layer == "ORTHO_FRONT":
            rectangles.append(((2, 2), (38, 18)))
        for (min_x, min_y), (max_x, max_y) in rectangles:
            space.add_lwpolyline(
                [
                    (min_x, min_y),
                    (max_x, min_y),
                    (max_x, max_y),
                    (min_x, max_y),
                ],
                close=True,
                dxfattribs={"layer": layer},
            )
    document.saveas(source)
    extraction = extract_drawing(source)

    artifacts = render_visual_evidence(
        source,
        extraction=extraction,
        max_artifacts=4,
        max_dimension_px=256,
        max_total_pixels=4 * 256 * 256,
    )

    assert len(artifacts) == 4
    assert [item.reference.rsplit(":", 1)[-1] for item in artifacts[:3]] == [
        "overview",
        "overview",
        "overview",
    ]
    assert [item.source_view_ids for item in artifacts[:3]] == [
        ("view-front",),
        ("view-side",),
        ("view-top",),
    ]
    crop = artifacts[3]
    assert crop.source_view_ids == ("view-front",)
    assert len(crop.source_contour_ids) == 2
    assert "optional_region_crops_omitted:5" in artifacts[0].warnings


def test_mandatory_overviews_still_fail_when_they_exceed_artifact_budget(
    tmp_path: Path,
) -> None:
    source = tmp_path / "three-views.dxf"
    _dxf(source, width=100)
    extraction = extract_drawing(source, input_kind="general_furniture")
    original = extraction.views[0]
    extraction = extraction.model_copy(update={
        "views": tuple(
            original.model_copy(update={"id": f"view-{index}"})
            for index in range(3)
        ),
    })

    with pytest.raises(ValueError, match="visual_evidence_budget_exceeded"):
        render_visual_evidence(
            source, extraction=extraction, max_artifacts=2, max_views=4,
        )


def test_clean_overview_preserves_source_dashed_linetype(tmp_path: Path) -> None:
    source = tmp_path / "linetypes.dxf"
    document = ezdxf.new("R2018")
    document.units = ezdxf.units.MM
    document.linetypes.add("QA_DASHED", pattern=[0.4, 0.25, -0.15])
    space = document.modelspace()
    space.add_line((0, 20), (100, 20))
    space.add_line((0, 0), (100, 0), dxfattribs={"linetype": "QA_DASHED"})
    document.saveas(source)

    artifact = render_visual_evidence(
        source,
        extraction=extract_drawing(source, input_kind="general_furniture"),
        max_dimension_px=256,
    )[0]

    assert "source_linetypes_preserved:QA_DASHED" in artifact.warnings
    with Image.open(BytesIO(artifact.content)) as image:
        pixels = image.convert("RGB")
        solid = [pixels.getpixel((x, 24)) for x in range(24, pixels.width - 24)]
        dashed = [
            pixels.getpixel((x, pixels.height - 24))
            for x in range(24, pixels.width - 24)
        ]
    assert sum(value != (255, 255, 255) for value in solid) > 0.9 * len(solid)
    dark_dashed = sum(value != (255, 255, 255) for value in dashed)
    assert 0.2 * len(dashed) < dark_dashed < 0.9 * len(dashed)
