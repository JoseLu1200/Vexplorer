from __future__ import annotations

from backend.app.contratos.modelos import Comparable, CostConcept, Estimate, Result


def estimate_result(result: Result, comparables: tuple[Comparable, ...]) -> Estimate:
    if result.state != "completed":
        raise ValueError("result_needs_review")
    if not comparables:
        raise ValueError("no_comparables")
    if not result.pieces:
        raise ValueError("result_has_no_confirmed_pieces")
    if any(piece.length_mm is None or piece.width_mm is None or piece.quantity is None for piece in result.pieces):
        raise ValueError("insufficient_dimensions")
    materials = {piece.material for piece in result.pieces}
    finishes = {piece.finish for piece in result.pieces}
    if None in materials or len(materials) != 1 or None in finishes or len(finishes) != 1:
        raise ValueError("missing_compatible_material_or_finish")
    reference = comparables[0]
    if reference.material not in materials or reference.finish not in finishes:
        raise ValueError("missing_compatible_tariff")
    target_area = sum(piece.length_mm * piece.width_mm * piece.quantity for piece in result.pieces if piece.length_mm is not None and piece.width_mm is not None and piece.quantity is not None)
    material_factor = target_area / reference.reference_area_mm2
    fixed = CostConcept(id="setup", label="Preparación fija", cost_type="fixed", base_amount=reference.fixed_cost_eur, factor=1, amount=round(reference.fixed_cost_eur, 2), explanation="El coste fijo no escala con dimensiones ni cantidad.", comparable_id=reference.id)
    material_amount = round(reference.material_cost_eur * material_factor, 2)
    material_rate = reference.material_cost_eur / (reference.reference_area_mm2 / 1_000_000)
    material = CostConcept(id="material", label="Consumo de tablero", cost_type="material", base_amount=reference.material_cost_eur, factor=round(material_factor, 6), amount=material_amount, explanation=f"Tarifa sintética {material_rate:.2f} EUR/m² aplicada al área total confirmada de todas las piezas; no incluye el fijo.", comparable_id=reference.id)
    concepts = (fixed, material)
    return Estimate(run_id=result.run_id, result_revision=result.result_revision, concepts=concepts, total=round(sum(item.amount for item in concepts), 2), hours=None, assumptions=("Histórico y tarifas sintéticos; estimación no apta para compra.", "Sin referencia de horas compatible: horas desconocidas."), comparable_ids=(reference.id,))
