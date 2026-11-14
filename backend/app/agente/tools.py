from __future__ import annotations

from backend.app.contratos.modelos import (
    ExplainPieceArgs,
    InspectEvidenceArgs,
    ListEvidenceArgs,
    InspectSeparatedPartArgs,
    InspectTableMeasuresArgs,
    ProposeTableProgramArgs,
    SelectAssemblyCandidateArgs,
    SelectScenarioArgs,
)


def _strictify_schema(value):
    if isinstance(value, dict):
        normalized = {key: _strictify_schema(item) for key, item in value.items() if key != "default"}
        if normalized.get("type") == "object" or "properties" in normalized:
            properties = normalized.get("properties", {})
            normalized["additionalProperties"] = False
            normalized["required"] = list(properties)
        return normalized
    if isinstance(value, list):
        return [_strictify_schema(item) for item in value]
    return value


def _schema(name: str, description: str, model) -> dict:
    return {"type": "function", "name": name, "description": description, "parameters": _strictify_schema(model.model_json_schema()), "strict": True}


def tool_schemas() -> list[dict]:
    return [
        _schema("listar_evidencias", "Lista IDs de evidencia del ledger actual con cursor estable y filtro opcional; no devuelve geometría completa.", ListEvidenceArgs),
        _schema("inspeccionar_evidencia", "Consulta evidencias por ID dentro del ledger autorizado del run actual.", InspectEvidenceArgs),
        _schema("entregar_despiece", "Entrega una hipótesis de montaje existente por referencia; no la confirma ni añade medidas.", SelectScenarioArgs),
        _schema("explicar_pieza", "Devuelve fuentes, estados, premisas y desconocidos de una hipótesis de componente en la revisión 1; no la confirma ni revela razonamiento interno.", ExplainPieceArgs),
    ]


def parts_tool_schemas() -> list[dict]:
    return [
        _schema(
            "inspeccionar_pieza",
            "Consulta una observación de pieza separada del ledger actual, incluidas vistas, medidas, cantidad, fuentes y desconocidos.",
            InspectSeparatedPartArgs,
        ),
        _schema(
            "entregar_candidato_montaje",
            "Entrega por ID un candidato de montaje ya calculado; no confirma el montaje ni permite aportar medidas o cantidades.",
            SelectAssemblyCandidateArgs,
        ),
    ]


def table_tool_schemas() -> list[dict]:
    return [
        _schema(
            "inspeccionar_medidas_mesa",
            "Consulta por ID medidas y evidencias del ledger de vistas montadas actual; no modifica valores.",
            InspectTableMeasuresArgs,
        ),
        _schema(
            "proponer_descomposicion",
            "Propone un programa acotado por referencias y reglas; no admite números, coordenadas, cantidades ni placements libres.",
            ProposeTableProgramArgs,
        ),
    ]
