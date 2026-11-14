"""Plausibility of observations against the workshop catalog.

Pure and deterministic. Findings are hints for the agent and the reviewer: they never fill fields, confirm
thicknesses or change scenarios. A value missing from the catalog yields `unknown`, never a default.
"""
from __future__ import annotations

import json
import os
from itertools import pairwise
from math import hypot
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.contratos.modelos import (
    DecompositionScenario,
    DrawingEntity,
    DrawingExtraction,
)

DEFAULT_CATALOG_PATH = Path(__file__).with_name("catalogo_taller.json")
CATALOG_ENV = "VEXPLORER_WORKSHOP_CATALOG"
TOLERANCE_MM = 0.1
# A measured position farther than this from every drawn vertex (along the measuring direction) is not on geometry.
DIMENSION_ATTACH_TOLERANCE_MM = 0.5
MAX_DIMENSIONS_CHECKED = 200
NON_GEOMETRY_KINDS = {"DIMENSION", "TEXT", "MTEXT", "ATTRIB", "HATCH"}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DrillingSystem(_Model):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    pitch_mm: float = Field(gt=0)
    hole_diameter_mm: float = Field(gt=0)
    setback_mm: float | None = Field(default=None, gt=0)
    sources: tuple[str, ...] = ()


class WorkshopCatalog(_Model):
    source: str = Field(min_length=1)
    confirmed_by_workshop: bool = False
    drilling_systems: tuple[DrillingSystem, ...] = ()
    board_thicknesses_mm: tuple[float, ...] = ()
    thickness_tolerance_mm: float = Field(default=0.5, gt=0)
    edge_banding_thicknesses_mm: tuple[float, ...] = ()


class PlausibilityFinding(_Model):
    id: str
    check: Literal["hole_row_drilling_system", "observed_thickness_in_catalog", "dimension_attached_to_geometry"]
    status: Literal["pass", "fail", "unknown"]
    message: str
    evidence_ids: tuple[str, ...] = ()
    proposal_ids: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()


def load_catalog(path: Path | None = None) -> WorkshopCatalog:
    """Catalog from an explicit path, then from VEXPLORER_WORKSHOP_CATALOG, then the shipped default."""
    selected = path or (Path(os.environ[CATALOG_ENV]) if os.environ.get(CATALOG_ENV) else DEFAULT_CATALOG_PATH)
    return WorkshopCatalog.model_validate(json.loads(selected.read_text(encoding="utf-8")))


def _circle_mm(entity: DrawingEntity) -> tuple[float, float, float] | None:
    """Center and radius from a flattened circle (its last point repeats the first)."""
    points = entity.points_mm
    if entity.kind != "CIRCLE" or not points or len(points) < 4:
        return None
    ring = points[:-1] if points[0] == points[-1] else points
    center_x = sum(point.x for point in ring) / len(ring)
    center_y = sum(point.y for point in ring) / len(ring)
    return center_x, center_y, hypot(ring[0].x - center_x, ring[0].y - center_y)


def _setback(extraction: DrawingExtraction, view_entity_ids: set[str], centers: list[tuple[float, float]], vertical: bool) -> float | None:
    """Distance from the row to the nearest parallel edge of the smallest contour of the same view that holds it."""
    best: tuple[float, float] | None = None
    for contour in extraction.contours:
        if not contour.points_mm or not set(contour.source_entity_ids) <= view_entity_ids:
            continue
        xs = [point.x for point in contour.points_mm]
        ys = [point.y for point in contour.points_mm]
        if not all(min(xs) < x < max(xs) and min(ys) < y < max(ys) for x, y in centers):
            continue
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        coordinate = centers[0][0] if vertical else centers[0][1]
        low, high = (min(xs), max(xs)) if vertical else (min(ys), max(ys))
        distance = min(coordinate - low, high - coordinate)
        if best is None or area < best[0]:
            best = (area, distance)
    return None if best is None else best[1]


def _hole_findings(extraction: DrawingExtraction, catalog: WorkshopCatalog) -> list[PlausibilityFinding]:
    entities = {entity.id: entity for entity in extraction.entities}
    view_by_entity = {entity_id: view for view in extraction.views for entity_id in view.entity_ids}
    findings = []
    for item in extraction.evidence:
        if not item.id.startswith("evidence-holes-"):
            continue
        circles = [circle for entity_id in item.source_entity_ids if (circle := _circle_mm(entities[entity_id])) is not None]
        if len(circles) < 2:
            continue
        diameter = 2 * circles[0][2]
        vertical = abs(circles[-1][0] - circles[0][0]) <= TOLERANCE_MM
        along = sorted(circle[1] if vertical else circle[0] for circle in circles)
        spacings = [second - first for first, second in pairwise(along)]
        view = next((view_by_entity.get(entity_id) for entity_id in item.source_entity_ids if entity_id in view_by_entity), None)
        setback = _setback(extraction, set(view.entity_ids) if view else set(), [(circle[0], circle[1]) for circle in circles], vertical)
        matches = []
        for system in catalog.drilling_systems:
            if abs(diameter - system.hole_diameter_mm) > TOLERANCE_MM:
                continue
            if not all(abs(spacing / system.pitch_mm - round(spacing / system.pitch_mm)) * system.pitch_mm <= TOLERANCE_MM and round(spacing / system.pitch_mm) >= 1 for spacing in spacings):
                continue
            matches.append(system)
        if matches:
            system = matches[0]
            setback_text = (
                f"retranqueo dibujado {setback:.1f} mm ({'coincide' if abs(setback - system.setback_mm) <= TOLERANCE_MM else 'no coincide'} con {system.setback_mm:g} mm)"
                if setback is not None and system.setback_mm is not None else "retranqueo no medible"
            )
            message = f"Fila compatible con {system.label}: diámetro {diameter:.1f} mm, paso {system.pitch_mm:g} mm; {setback_text}. Sugiere lateral con taladro de sistema; no confirma la pieza."
            status: Literal["pass", "unknown", "fail"] = "pass"
        else:
            message = f"Fila de diámetro {diameter:.1f} mm sin sistema de taladro del catálogo que la explique; puede ser otro herraje."
            status = "unknown"
        findings.append(PlausibilityFinding(
            id=f"plausibility-{item.id}", check="hole_row_drilling_system", status=status, message=message,
            evidence_ids=(item.id,), entity_ids=item.source_entity_ids,
        ))
    return findings


def _thickness_findings(scenarios: tuple[DecompositionScenario, ...], catalog: WorkshopCatalog) -> list[PlausibilityFinding]:
    findings = []
    for scenario in scenarios:
        for proposal in scenario.components:
            if proposal.observed_thickness_mm is None:
                continue
            value = proposal.observed_thickness_mm
            if not catalog.board_thicknesses_mm:
                status: Literal["pass", "unknown", "fail"] = "unknown"
                message = f"Espesor observado {value:g} mm sin catálogo de tableros con el que contrastarlo (pendiente de compras)."
            elif any(abs(value - thickness) <= catalog.thickness_tolerance_mm for thickness in catalog.board_thicknesses_mm):
                status = "pass"
                message = f"Espesor observado {value:g} mm coincide con un tablero del catálogo; sigue requiriendo confirmación humana."
            else:
                status = "fail"
                message = f"Espesor observado {value:g} mm no coincide con ningún tablero del catálogo ({', '.join(f'{item:g}' for item in catalog.board_thicknesses_mm)} mm)."
            findings.append(PlausibilityFinding(
                id=f"plausibility-thickness-{proposal.id}", check="observed_thickness_in_catalog", status=status, message=message,
                proposal_ids=(proposal.id,), entity_ids=proposal.thickness_source_entity_ids,
            ))
    return findings


def _dimension_findings(extraction: DrawingExtraction) -> list[PlausibilityFinding]:
    """Linear dimensions whose measured positions match no drawn vertex of their view.

    Each extension point is projected onto the measuring direction; some vertex of the view's geometry must sit at
    that same coordinate. Extension lines may start away from the feature (a height taken at x=0 on a trapezoid), so
    only the measured coordinate is checked. A miss is typical of a non-associative dimension left behind after the
    geometry was stretched: the annotated value may not describe what is drawn. Millimetre coordinates only; findings
    only, the extraction status is not changed.
    """
    if extraction.coordinate_unit != "mm":
        return []
    entities = {entity.id: entity for entity in extraction.entities}
    vertices_by_view: dict[str, list[tuple[float, float]]] = {}
    for view in extraction.views:
        vertices_by_view[view.id] = [
            (point.x, point.y)
            for entity_id in view.entity_ids
            if (entity := entities.get(entity_id)) is not None and entity.kind not in NON_GEOMETRY_KINDS and entity.points_mm
            for point in entity.points_mm
        ]
    evidence_by_dimension = {item.id: item.evidence_ids for item in extraction.dimensions}
    findings = []
    for graphic in extraction.dimension_graphics[:MAX_DIMENSIONS_CHECKED]:
        anchors = (graphic.extension_start_a_mm, graphic.extension_start_b_mm)
        line = (graphic.dimension_start_mm, graphic.dimension_end_mm)
        vertices = vertices_by_view.get(graphic.view_id, [])
        if any(item is None for item in (*anchors, *line)) or not vertices:
            continue
        length = hypot(line[1].x - line[0].x, line[1].y - line[0].y)
        if length <= TOLERANCE_MM:
            continue
        direction = ((line[1].x - line[0].x) / length, (line[1].y - line[0].y) / length)
        projected = [x * direction[0] + y * direction[1] for x, y in vertices]
        gaps = [min(abs(anchor.x * direction[0] + anchor.y * direction[1] - value) for value in projected) for anchor in anchors]
        worst = max(gaps)
        if worst <= DIMENSION_ATTACH_TOLERANCE_MM:
            status: Literal["pass", "fail", "unknown"] = "pass"
            message = "Las dos posiciones medidas por la cota coinciden con vértices dibujados de su vista."
        else:
            status = "fail"
            message = f"Una posición medida por la cota queda a {worst:.1f} mm del vértice dibujado más cercano en su dirección: la cota puede no describir lo dibujado y debe revisarse."
        findings.append(PlausibilityFinding(
            id=f"plausibility-{graphic.dimension_id}", check="dimension_attached_to_geometry", status=status, message=message,
            evidence_ids=evidence_by_dimension.get(graphic.dimension_id, ()), entity_ids=(graphic.source_entity_id,),
        ))
    return findings


def check_plausibility(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], catalog: WorkshopCatalog | None = None) -> tuple[PlausibilityFinding, ...]:
    catalog = catalog or load_catalog()
    return tuple(_hole_findings(extraction, catalog) + _thickness_findings(scenarios, catalog) + _dimension_findings(extraction))
