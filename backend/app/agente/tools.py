from __future__ import annotations

from backend.app.contratos.modelos import ExplainPieceArgs, InspectEvidenceArgs, SelectScenarioArgs, VisualizeViewArgs


def _schema(name: str, description: str, model) -> dict:
    return {"type": "function", "name": name, "description": description, "parameters": model.model_json_schema(), "strict": True}


def tool_schemas(vision: bool = False) -> list[dict]:
    """Closed tool list. `visualizar_vista` only exists when the vision channel is enabled by configuration."""
    tools = [
        _schema("inspeccionar_evidencia", "Consulta evidencias por ID dentro del ledger autorizado del run actual.", InspectEvidenceArgs),
        _schema("entregar_despiece", "Entrega una hipótesis de montaje existente por referencia; no la confirma ni añade medidas.", SelectScenarioArgs),
        _schema("explicar_pieza", "Devuelve fuentes, estados, premisas y desconocidos de una hipótesis de componente en la revisión 1; no la confirma ni revela razonamiento interno.", ExplainPieceArgs),
    ]
    if vision:
        tools.append(_schema(
            "visualizar_vista",
            "Dibuja una vista del ledger actual como imagen con cada contorno numerado y devuelve la tabla número→ID de contorno. Sirve para ver relaciones (dentro de, repetido, alineado); las medidas siguen saliendo del ledger.",
            VisualizeViewArgs,
        ))
    return tools
