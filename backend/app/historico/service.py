from __future__ import annotations

from backend.app.contratos.modelos import Comparable, Result

_CATALOG = (
    dict(id="hist-syn-1", name="Estantería sintética compacta", width=800.0, depth=300.0, height=1700.0, material="tablero sintético", finish="melamina sintética", fixed=40.0, variable=60.0, area=1_200_000.0),
    dict(id="hist-syn-2", name="Estantería sintética alta", width=1000.0, depth=350.0, height=2100.0, material="contrachapado sintético", finish="barniz sintético", fixed=55.0, variable=95.0, area=1_800_000.0),
    dict(id="hist-syn-3", name="Módulo sintético abierto", width=700.0, depth=280.0, height=1500.0, material="tablero sintético", finish="sin acabado", fixed=35.0, variable=48.0, area=980_000.0),
)


def _assembly_dimensions(result: Result) -> tuple[float | None, float | None, float | None]:
    if result.input_semantics == "separated_part_views":
        candidate = next((item for item in result.assembly_candidates if item.id == result.selected_assembly_candidate_id), None)
        if candidate is None:
            candidates = result.assembly_candidates
            signatures = [{item.axis: item.value_mm if item.state == "derived" else None for item in value.derived_dimensions} for value in candidates]
            if signatures and all(item == signatures[0] for item in signatures):
                values = signatures[0]
                return values.get("width"), values.get("depth"), values.get("height")
            return None, None, None
        values = {item.axis: item.value_mm if item.state == "derived" else None for item in candidate.derived_dimensions}
        return values.get("width"), values.get("depth"), values.get("height")
    pieces = {piece.role: piece for piece in result.pieces}
    side, top = pieces.get("side_panel"), pieces.get("top_panel")
    selected = result.review.selected_scenario_id if result.review else None
    if side and top and side.thickness_mm:
        thickness = side.thickness_mm
        depth = side.width_mm or top.width_mm
        if selected == "scenario-between-sides" and top.length_mm and side.length_mm:
            return top.length_mm + 2 * thickness, depth, side.length_mm
        if selected == "scenario-cap-sides" and top.length_mm and side.length_mm:
            return top.length_mm, depth, side.length_mm + 2 * thickness
    piece = result.pieces[0] if result.pieces else None
    return (piece.length_mm if piece else None, piece.width_mm if piece else None, None)


def find_comparables(result: Result, limit: int = 3) -> tuple[Comparable, ...]:
    piece = result.pieces[0] if result.pieces else None
    width, depth, _height = _assembly_dimensions(result)
    material = piece.material if piece else None
    finish = piece.finish if piece else None
    values: list[Comparable] = []
    for item in _CATALOG:
        diffs: list[str] = []
        dimensional_penalty = 0.5
        if width and depth:
            dimensional_penalty = min(1.0, abs(width - item["width"]) / item["width"] + abs(depth - item["depth"]) / item["depth"])
            diffs.append(f"dimensiones: {width:g}×{depth:g} mm frente a {item['width']:g}×{item['depth']:g} mm")
        else:
            diffs.append("dimensiones insuficientes para comparar completamente")
        material_match = material == item["material"]
        finish_match = finish == item["finish"]
        diffs.append("material coincide" if material_match else f"material distinto: {material or 'desconocido'} / {item['material']}")
        diffs.append("acabado coincide" if finish_match else f"acabado distinto: {finish or 'desconocido'} / {item['finish']}")
        score = max(0.0, 1.0 - 0.6 * dimensional_penalty - (0 if material_match else 0.2) - (0 if finish_match else 0.2))
        values.append(Comparable(id=item["id"], name=item["name"], family="estanteria_rectangular", width_mm=item["width"], depth_mm=item["depth"], height_mm=item["height"], material=item["material"], finish=item["finish"], score=round(score, 4), differences=tuple(diffs), fixed_cost_eur=item["fixed"], material_cost_eur=item["variable"], reference_area_mm2=item["area"], hours=None))
    return tuple(sorted(values, key=lambda value: value.score, reverse=True)[:limit])
