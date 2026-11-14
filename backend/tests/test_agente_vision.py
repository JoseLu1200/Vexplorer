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
