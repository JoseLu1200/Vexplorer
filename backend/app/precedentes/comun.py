"""Utilidades compartidas del paquete ``precedentes``.

Convenciones del paquete:
- Identificadores, modelos y mensajes en español.
- Unidades en milímetros.
- Funciones de cálculo puras y deterministas; empates resueltos por identificador.
- Toda sugerencia derivada de precedentes es una hipótesis, nunca una medida observada.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

ESQUEMA_PRECEDENTES = "1.0.0"
PREFIJO_API = "/api/v1/precedentes"


class ModeloEstricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def respuesta_ok(valor: object) -> dict[str, object]:
    if hasattr(valor, "model_dump"):
        valor = valor.model_dump(mode="json")
    return {"schema_version": ESQUEMA_PRECEDENTES, "data": valor, "error": None}


def respuesta_error(codigo: str, mensaje: str | None = None) -> dict[str, object]:
    error: dict[str, object] = {"code": codigo}
    if mensaje is not None:
        error["message"] = mensaje
    return {"schema_version": ESQUEMA_PRECEDENTES, "data": None, "error": error}


def normalizar_texto(valor: str | None) -> str | None:
    """Clave de comparación exacta para material/acabado: sin espacios extremos y sin mayúsculas."""
    if valor is None:
        return None
    limpio = " ".join(valor.split()).casefold()
    return limpio or None
