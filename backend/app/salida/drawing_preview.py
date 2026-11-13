"""Visual CAD preview using ezdxf's MIT-licensed drawing backend.

This SVG has its own page coordinates. It is not a measurement ledger and must
not be overlaid with source coordinates or used to infer components.
"""
from __future__ import annotations

from pathlib import Path
from time import monotonic
from xml.etree import ElementTree as ET

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, config, layout, svg
from ezdxf.addons.drawing.properties import Properties
from ezdxf.entities import DXFGraphic


class _BoundedFrontend(Frontend):
    """Bound expanded entities, block recursion and time between entities."""

    def __init__(self, context: RenderContext, backend: svg.SVGBackend):
        super().__init__(context, backend, config.Configuration(
            background_policy=config.BackgroundPolicy.WHITE,
            image_policy=config.ImagePolicy.IGNORE,
            proxy_graphic_policy=config.ProxyGraphicPolicy.IGNORE,
            hatch_policy=config.HatchPolicy.SHOW_OUTLINE,
        ))
        self._remaining = 25000
        self._depth = 0
        self._deadline = monotonic() + 15

    def draw_entity(self, entity: DXFGraphic, properties: Properties) -> None:
        self._remaining -= 1
        if self._remaining < 0 or self._depth >= 16 or monotonic() > self._deadline:
            raise ValueError("preview_complexity_limit")
        self._depth += 1
        try:
            super().draw_entity(entity, properties)
        finally:
            self._depth -= 1


def render_drawing_preview(path: Path) -> str:
    """Render modelspace for display only, without loading image attachments.

    The time budget is cooperative between entities, not a process-level limit.
    Filled hatches are represented by their outlines; no layouts or ACIS solids.
    """
    try:
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("preview_complexity_limit")
        doc = ezdxf.readfile(path)
        backend = svg.SVGBackend()
        _BoundedFrontend(RenderContext(doc), backend).draw_layout(doc.modelspace())
        value = backend.get_string(layout.Page(0, 0))
        if len(value.encode("utf-8")) > 3 * 1024 * 1024:
            raise ValueError("preview_complexity_limit")
        # Generated paths only: never allow active content or external resources.
        root = ET.fromstring(value)
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag not in {"svg", "g", "path", "line", "polyline", "polygon", "rect", "defs", "style"}:
                raise ValueError("invalid_dxf")
            if any("href" in key.lower() or key.lower().startswith("on") for key in element.attrib):
                raise ValueError("invalid_dxf")
        return value
    except ValueError as exc:
        if str(exc) in {"preview_complexity_limit", "invalid_dxf"}:
            raise
        raise ValueError("invalid_dxf") from exc
    except (OSError, ezdxf.DXFError, ET.ParseError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid_dxf") from exc
