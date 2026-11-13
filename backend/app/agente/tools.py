from __future__ import annotations

from backend.app.contratos.modelos import ExplainPieceArgs, InspectEvidenceArgs, SelectScenarioArgs


def _schema(name: str, description: str, model) -> dict:
    return {"type": "function", "name": name, "description": description, "parameters": model.model_json_schema(), "strict": True}


def tool_schemas() -> list[dict]:
    return [
        _schema("inspeccionar_evidencia", "Consulta evidencias por ID dentro del ledger autorizado del run actual.", InspectEvidenceArgs),
        _schema("entregar_despiece", "Entrega una hipótesis de montaje existente por referencia; no la confirma ni añade medidas.", SelectScenarioArgs),
        _schema("explicar_pieza", "Devuelve fuentes, estados, fórmulas, premisas y desconocidos de una pieza resuelta; no revela razonamiento interno.", ExplainPieceArgs),
    ]
