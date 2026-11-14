"""Renderer visual acotado: solo consume el ledger público."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from backend.app.agente.vision import RenderedView, VisionMark, render_view
from backend.app.contratos.modelos import (
    Bounds2D,
    CircularGeometry,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingObservation,
    DrawingView,
    Point2D,
)


def _points(*coordinates: tuple[float, float]) -> tuple[Point2D, ...]:
    return tuple(Point2D(x=x, y=y) for x, y in coordinates)


def _extraction(
    *,
    entity_count: int = 2,
    contour_count: int = 1,
    points_per_entity: int = 2,
    empty: bool = False,
) -> DrawingExtraction:
    entities = tuple(
        DrawingEntity(
            id=f"entity-{index:03d}",
            kind="LINE",
            layer="GEOMETRY",
            source_points=tuple(
                Point2D(x=index * 20 + point_index * 5, y=index * 10 + point_index * 3)
                for point_index in range(points_per_entity)
            ),
            points_mm=tuple(
                Point2D(x=index * 20 + point_index * 5, y=index * 10 + point_index * 3)
                for point_index in range(points_per_entity)
            ),
        )
        for index in range(0 if empty else entity_count)
    )
    contours = tuple(
        DrawingContour(
            id=f"contour-{index:03d}",
            view_id="view-public",
            source_entity_ids=(entities[index % len(entities)].id,),
            points_source=_points(
                (index * 4, index * 4),
                (100 - index * 4, index * 4),
                (100 - index * 4, 80 - index * 4),
                (index * 4, 80 - index * 4),
            ),
            points_mm=_points(
                (index * 4, index * 4),
                (100 - index * 4, index * 4),
                (100 - index * 4, 80 - index * 4),
                (index * 4, 80 - index * 4),
            ),
            closed=True,
        )
        for index in range(0 if empty else contour_count)
    )
    view = DrawingView(
        id="view-public",
        label="FRONT",
        entity_ids=tuple(entity.id for entity in entities),
        bounds_source=Bounds2D(min_x=0, min_y=0, max_x=100, max_y=80),
        bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=100, max_y=80),
    )
    observation = DrawingObservation(
        id="observation-public",
        view_id=view.id,
        contour_ids=tuple(contour.id for contour in contours),
        dimension_ids=(),
    )
    return DrawingExtraction(
        drawing_id="drawing-public",
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1.0,
        coordinate_unit="mm",
        entities=entities,
        views=(view,),
        contours=contours,
        dimensions=(),
        evidence=(),
        observations=(observation,),
    )


def _curved_extraction(kind: str = "CIRCLE") -> DrawingExtraction:
    center = Point2D(x=50, y=50)
    circular = CircularGeometry(
        kind=kind.lower(),
        center_source=center,
        center_mm=center,
        radius_source=25,
        radius_mm=25,
        start_angle_deg=0 if kind == "ARC" else None,
        end_angle_deg=90 if kind == "ARC" else None,
    )
    endpoints = (
        _points((75, 50), (50, 75)) if kind == "ARC" else _points((75, 50))
    )
    entity = DrawingEntity(
        id=f"entity-{kind.lower()}",
        kind=kind,
        layer="CURVES",
        source_points=endpoints,
        points_mm=endpoints,
        circular=circular,
    )
    annotation = DrawingEntity(
        id="entity-dimension",
        kind="DIMENSION",
        layer="DIMENSIONS",
        source_points=_points((0, 0), (100, 100), (0, 100), (100, 0)),
        points_mm=_points((0, 0), (100, 100), (0, 100), (100, 0)),
    )
    view = DrawingView(
        id="view-curves",
        label="FRONT",
        entity_ids=(annotation.id, entity.id),
        bounds_source=Bounds2D(min_x=0, min_y=0, max_x=100, max_y=100),
        bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=100, max_y=100),
    )
    return DrawingExtraction(
        drawing_id="drawing-curves",
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1.0,
        coordinate_unit="mm",
        entities=(annotation, entity),
        views=(view,),
        contours=(),
        dimensions=(),
        evidence=(),
        observations=(
            DrawingObservation(
                id="observation-curves",
                view_id=view.id,
                contour_ids=(),
                dimension_ids=(),
            ),
        ),
    )


def test_render_is_deterministic_decodable_and_self_describing() -> None:
    extraction = _extraction()

    first = render_view(extraction, "view-public")
    second = render_view(extraction, "view-public")
    shuffled = render_view(
        extraction.model_copy(update={"entities": tuple(reversed(extraction.entities))}),
        "view-public",
    )

    assert first == second == shuffled
    assert isinstance(first, RenderedView)
    assert first.media_type == "image/png"
    assert first.sha256 == sha256(first.png).hexdigest()
    assert len(first.png) <= 2_000_000
    with Image.open(BytesIO(first.png)) as image:
        image.load()
        assert image.format == "PNG"
        assert image.size == (first.width_px, first.height_px)
        assert max(image.size) <= 1024
        assert image.getbbox() is not None
    assert first.marks == (
        VisionMark("M001", "contour", "contour-000"),
        VisionMark("M002", "entity", "entity-000"),
        VisionMark("M003", "entity", "entity-001"),
    )
    with pytest.raises(FrozenInstanceError):
        first.width_px = 1  # type: ignore[misc]


@pytest.mark.parametrize("view_id", ["view-private", "../../private.dxf", "https://example.test/a.dxf"])
def test_arbitrary_nonpublic_view_is_rejected(view_id: str) -> None:
    with pytest.raises(ValueError, match="^unknown_view$"):
        render_view(_extraction(), view_id)


def test_empty_or_inconsistent_public_geometry_is_rejected() -> None:
    with pytest.raises(ValueError, match="^vision_geometry_unavailable$"):
        render_view(_extraction(empty=True), "view-public")

    extraction = _extraction(entity_count=2)
    bad_contour = extraction.contours[0].model_copy(
        update={"source_entity_ids": ("entity-001",)}
    )
    view = extraction.views[0].model_copy(update={"entity_ids": ("entity-000",)})
    inconsistent = extraction.model_copy(
        update={"views": (view,), "contours": (bad_contour,)}
    )
    with pytest.raises(ValueError, match="^vision_geometry_unavailable$"):
        render_view(inconsistent, "view-public")


@pytest.mark.parametrize(
    ("kwargs", "factory_kwargs"),
    [
        ({"max_entities": 1}, {"entity_count": 2}),
        ({"max_contours": 1}, {"contour_count": 2}),
        ({"max_points": 7}, {"entity_count": 2, "contour_count": 1, "points_per_entity": 2}),
    ],
)
def test_geometry_budgets_fail_before_creating_an_image(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, int], factory_kwargs: dict[str, int]
) -> None:
    def image_must_not_be_created(*args, **inner_kwargs):
        raise AssertionError("the image was created before the ledger budget was checked")

    monkeypatch.setattr("backend.app.agente.vision.Image.new", image_must_not_be_created)
    with pytest.raises(ValueError, match="^vision_budget_exceeded$"):
        render_view(_extraction(**factory_kwargs), "view-public", **kwargs)


def test_pixel_and_encoded_png_limits_are_enforced() -> None:
    rendered = render_view(_extraction(), "view-public", max_dimension_px=128)
    assert max(rendered.width_px, rendered.height_px) <= 128

    with pytest.raises(ValueError, match="^vision_budget_exceeded$"):
        render_view(_extraction(), "view-public", max_dimension_px=47)
    with pytest.raises(ValueError, match="^vision_budget_exceeded$"):
        render_view(_extraction(), "view-public", max_png_bytes=8)


def test_annotations_are_omitted_and_circle_uses_typed_geometry() -> None:
    rendered = render_view(_curved_extraction("CIRCLE"), "view-curves", max_dimension_px=128)

    assert [mark.source_id for mark in rendered.marks] == ["entity-circle"]
    with Image.open(BytesIO(rendered.png)) as image:
        image.load()
        pixels = image.convert("RGB")
        dark = [
            (x, y)
            for y in range(image.height)
            for x in range(image.width)
            if max(pixels.getpixel((x, y))) < 180
        ]
    assert dark
    assert any(x < image.width // 3 for x, _ in dark)
    assert any(x > image.width * 2 // 3 for x, _ in dark)
    assert any(y < image.height // 3 for _, y in dark)
    assert any(y > image.height * 2 // 3 for _, y in dark)


def test_arc_is_a_curve_not_the_false_endpoint_chord() -> None:
    rendered = render_view(_curved_extraction("ARC"), "view-curves", max_dimension_px=256)

    with Image.open(BytesIO(rendered.png)) as image:
        image.load()
        pixels = image.convert("RGB")
        # The 0°→90° curve reaches the upper-right bounding-box corner.
        upper_right_has_ink = any(
            max(pixels.getpixel((x, y))) < 180
            for y in range(20, image.height // 3)
            for x in range(image.width * 2 // 3, image.width - 20)
        )
        chord_midpoint_is_blank = all(
            min(pixels.getpixel((x, y))) > 220
            for y in range(image.height // 2 - 3, image.height // 2 + 4)
            for x in range(image.width // 2 - 3, image.width // 2 + 4)
        )
    assert upper_right_has_ink
    assert chord_midpoint_is_blank


def test_degenerate_arc_is_not_replaced_with_a_chord() -> None:
    extraction = _curved_extraction("ARC")
    entity = extraction.entities[1]
    circular = entity.circular.model_copy(update={"end_angle_deg": 0})
    entity = entity.model_copy(update={"circular": circular})
    extraction = extraction.model_copy(update={"entities": (extraction.entities[0], entity)})

    with pytest.raises(ValueError, match="^vision_geometry_unavailable$"):
        render_view(extraction, "view-curves")


def test_generated_curve_points_share_the_geometry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    def image_must_not_be_created(*args, **kwargs):
        raise AssertionError("curve budget was checked after raster allocation")

    monkeypatch.setattr("backend.app.agente.vision.Image.new", image_must_not_be_created)
    with pytest.raises(ValueError, match="^vision_budget_exceeded$"):
        render_view(_curved_extraction("CIRCLE"), "view-curves", max_points=65)
