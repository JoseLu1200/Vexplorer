"""Acceso común a los campos de los descriptores ``furniture-v1``, ``-v2`` y ``-v3``.

Cada versión de descriptor expone un conjunto distinto de campos. Este módulo centraliza
qué campos existen en cada versión y cómo leerlos, para que las funciones de precedentes
no repitan ``isinstance`` ni confundan "campo inexistente" con "valor desconocido".

Funciones puras; unidades en milímetros.
"""

from __future__ import annotations

from typing import Literal

from backend.app.contratos.modelos import (
    FurnitureDescriptor,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
)

Descriptor = FurnitureDescriptor | FurnitureDescriptorV2 | FurnitureDescriptorV3

TipoCampo = Literal["numerico", "categorico", "lista_mm"]

CAMPOS_DIMENSION: tuple[str, ...] = ("dimensions.width_mm", "dimensions.depth_mm", "dimensions.height_mm")

# Campos que pueden sugerirse a partir de precedentes, por versión de descriptor.
_CAMPOS_SUGERIBLES: dict[str, tuple[tuple[str, TipoCampo], ...]] = {
    "furniture-v1": (
        ("dimensions.width_mm", "numerico"),
        ("dimensions.depth_mm", "numerico"),
        ("dimensions.height_mm", "numerico"),
        ("material", "categorico"),
        ("finish", "categorico"),
    ),
    "furniture-v2": (
        ("dimensions.width_mm", "numerico"),
        ("dimensions.depth_mm", "numerico"),
        ("dimensions.height_mm", "numerico"),
        ("thicknesses_mm", "lista_mm"),
        ("material", "categorico"),
        ("finish", "categorico"),
    ),
    "furniture-v3": (
        ("dimensions.width_mm", "numerico"),
        ("dimensions.depth_mm", "numerico"),
        ("dimensions.height_mm", "numerico"),
        ("material_tariff_id", "categorico"),
    ),
}


def campos_sugeribles(descriptor: Descriptor) -> tuple[tuple[str, TipoCampo], ...]:
    """Campos de la versión del descriptor sobre los que tiene sentido sugerir un valor."""
    return _CAMPOS_SUGERIBLES[descriptor.descriptor_version]


def valor_campo(descriptor: Descriptor, campo: str) -> float | str | tuple[float, ...] | None:
    """Valor de un campo sugerible; ``None`` si es desconocido. ``KeyError`` si la versión no lo tiene."""
    if campo not in dict(campos_sugeribles(descriptor)):
        raise KeyError(campo)
    if campo.startswith("dimensions."):
        return getattr(descriptor.dimensions, campo.removeprefix("dimensions."))
    if campo == "thicknesses_mm":
        valores = tuple(float(item) for item in descriptor.thicknesses_mm)  # type: ignore[union-attr]
        return valores or None
    valor = getattr(descriptor, campo)
    if isinstance(valor, str):
        return valor.strip() or None
    return valor


def campo_desconocido(descriptor: Descriptor, campo: str) -> bool:
    """Un campo es desconocido si su valor falta o el descriptor lo declara en ``unknown_fields``."""
    return valor_campo(descriptor, campo) is None or campo in descriptor.unknown_fields


def familia(descriptor: Descriptor) -> str | None:
    return None if descriptor.family == "unknown" else descriptor.family


def estructura(descriptor: Descriptor) -> str | None:
    return None if descriptor.structure == "unknown" else descriptor.structure


def dimension(descriptor: Descriptor, eje: Literal["width_mm", "depth_mm", "height_mm"]) -> float | None:
    return getattr(descriptor.dimensions, eje)


def roles(descriptor: Descriptor) -> dict[str, int | None]:
    """Cantidad por rol; ``None`` si la cantidad del rol es desconocida."""
    if isinstance(descriptor, FurnitureDescriptorV3):
        resultado: dict[str, int | None] = {}
        for componente in descriptor.components:
            resultado[componente.role] = (resultado.get(componente.role) or 0) + componente.quantity
        return resultado
    resultado = {}
    for item in descriptor.roles:
        previo = resultado.get(item.role, 0)
        resultado[item.role] = None if item.quantity is None or previo is None else previo + item.quantity
    return resultado


def tiene_espesores(descriptor: Descriptor) -> bool:
    """``furniture-v1`` no registra espesores."""
    return not isinstance(descriptor, FurnitureDescriptor)


def espesores(descriptor: Descriptor) -> tuple[float, ...] | None:
    """Espesores distintos conocidos (mm). ``None`` si el campo no existe o está vacío."""
    if isinstance(descriptor, FurnitureDescriptorV2):
        return tuple(sorted({float(item) for item in descriptor.thicknesses_mm})) or None
    if isinstance(descriptor, FurnitureDescriptorV3):
        return tuple(sorted({float(item.thickness_mm) for item in descriptor.components})) or None
    return None


def tiene_material_texto(descriptor: Descriptor) -> bool:
    """``furniture-v3`` sólo guarda un identificador de tarifa, no un material en texto."""
    return not isinstance(descriptor, FurnitureDescriptorV3)


def material(descriptor: Descriptor) -> str | None:
    return getattr(descriptor, "material", None) if tiene_material_texto(descriptor) else None


def acabado(descriptor: Descriptor) -> str | None:
    return getattr(descriptor, "finish", None) if tiene_material_texto(descriptor) else None
