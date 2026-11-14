"""Modelo común de pieza y extracción desde las fuentes disponibles.

Fuentes:
- ``biblioteca``: ``LibraryItem`` revisados. ``furniture-v1`` no tiene piezas;
  ``furniture-v2`` aporta ``part_features`` (material/acabado del descriptor);
  ``furniture-v3`` aporta ``components`` cuyo "material" es un
  ``material_tariff_id`` (identificador de tarifa, no un nombre de material).
- ``historico``: ``HistoricalRecord.components`` importados.
- ``peticion``: piezas explícitas enviadas por el cliente.

Todas las medidas en milímetros. Las funciones son puras y deterministas.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Literal, Protocol

from pydantic import Field

from backend.app.contratos.modelos import (
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    LibraryItem,
)
from backend.app.historico.models import HistoricalRecord
from backend.app.precedentes.comun import ModeloEstricto

FuentePieza = Literal["biblioteca", "historico", "peticion"]

LIMITE_PIEZAS = 2000


class PiezaRef(ModeloEstricto):
    """Pieza referenciable de cualquier fuente. Medidas en mm; ``None`` = desconocido."""

    origen_id: str = Field(min_length=1, max_length=200)
    pieza_id: str = Field(min_length=1, max_length=200)
    largo_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    ancho_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    espesor_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    cantidad: int | None = Field(default=None, gt=0)
    material: str | None = Field(default=None, max_length=200)
    acabado: str | None = Field(default=None, max_length=200)
    # False = tiene veta o no se puede girar 90° al cortar (lo usa el nesting de 3.1).
    rotable: bool = True
    fuente: FuentePieza


class PiezaPedido(ModeloEstricto):
    """Pieza de un pedido explícito: su origen es el ``pedido_id`` que la contiene."""

    pieza_id: str = Field(min_length=1, max_length=200)
    largo_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    ancho_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    espesor_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    cantidad: int | None = Field(default=None, gt=0)
    material: str | None = Field(default=None, max_length=200)
    acabado: str | None = Field(default=None, max_length=200)
    rotable: bool = True

    def a_pieza_ref(self, origen_id: str) -> PiezaRef:
        """La fuente se fija siempre a ``peticion``: el cliente no puede declarar otra."""
        datos = self.model_dump(exclude={"origen_id"})
        return PiezaRef(**datos, origen_id=origen_id, fuente="peticion")


class PiezaPeticion(PiezaPedido):
    """Pieza suelta enviada en la petición, con su ``origen_id`` (proyecto/run/record)."""

    origen_id: str = Field(min_length=1, max_length=200)

    def a_ref(self) -> PiezaRef:
        return self.a_pieza_ref(self.origen_id)


class FuenteBiblioteca(Protocol):
    """Cualquier objeto con ``get_library_items()`` (p. ej. el repositorio)."""

    def get_library_items(self) -> tuple[LibraryItem, ...]: ...


class OrigenDatos(ModeloEstricto):
    """Recuento de piezas por fuente, para informar del origen de los datos."""

    peticion: int = 0
    biblioteca: int = 0
    historico: int = 0


PREFIJO_TARIFA = "tarifa:"


def _material_tarifa(tarifa_id: str | None) -> str | None:
    """V3 guarda un id de tarifa, no un nombre: se prefija para no mezclar claves."""
    return f"{PREFIJO_TARIFA}{tarifa_id}" if tarifa_id else None


def piezas_desde_item_biblioteca(item: LibraryItem) -> tuple[PiezaRef, ...]:
    """Extrae piezas de un ``LibraryItem``. ``origen_id`` = ``run_id``."""
    descriptor = item.descriptor
    if isinstance(descriptor, FurnitureDescriptorV2):
        return tuple(
            PiezaRef(
                origen_id=item.run_id,
                pieza_id=f"pieza-{indice:03d}",
                largo_mm=parte.length_mm,
                ancho_mm=parte.width_mm,
                espesor_mm=parte.thickness_mm,
                cantidad=parte.quantity,
                material=descriptor.material,
                acabado=descriptor.finish,
                fuente="biblioteca",
            )
            for indice, parte in enumerate(descriptor.part_features, start=1)
        )
    if isinstance(descriptor, FurnitureDescriptorV3):
        return tuple(
            PiezaRef(
                origen_id=item.run_id,
                pieza_id=f"{componente.role}-{indice:03d}",
                largo_mm=componente.length_mm,
                ancho_mm=componente.width_mm,
                espesor_mm=componente.thickness_mm,
                cantidad=componente.quantity,
                material=_material_tarifa(
                    componente.material_tariff_id or descriptor.material_tariff_id
                ),
                acabado=None,
                fuente="biblioteca",
            )
            for indice, componente in enumerate(descriptor.components, start=1)
        )
    return ()


def piezas_desde_registro_historico(registro: HistoricalRecord) -> tuple[PiezaRef, ...]:
    """Extrae componentes de un registro histórico. ``origen_id`` = ``project_id``."""
    return tuple(
        PiezaRef(
            origen_id=registro.project_id,
            pieza_id=f"{registro.record_id}:{componente.component_id}",
            largo_mm=componente.length_mm,
            ancho_mm=componente.width_mm,
            espesor_mm=componente.thickness_mm,
            cantidad=componente.quantity,
            material=componente.material,
            acabado=componente.finish,
            fuente="historico",
        )
        for componente in registro.components
    )


def piezas_desde_biblioteca(items: Iterable[LibraryItem]) -> tuple[PiezaRef, ...]:
    por_run: dict[str, LibraryItem] = {}
    for item in items:
        actual = por_run.get(item.run_id)
        if actual is None or item.result_revision > actual.result_revision:
            por_run[item.run_id] = item
    ordenados = sorted(por_run.values(), key=lambda item: (item.run_id, item.id))
    return tuple(
        pieza for item in ordenados for pieza in piezas_desde_item_biblioteca(item)
    )


def ids_duplicados(piezas: Iterable[PiezaRef]) -> tuple[str, ...]:
    conteo = Counter((pieza.origen_id, pieza.pieza_id) for pieza in piezas)
    return tuple(
        sorted(
            f"{origen}/{pieza}" for (origen, pieza), cant in conteo.items() if cant > 1
        )
    )


def contar_origen(piezas: Iterable[PiezaRef]) -> OrigenDatos:
    recuento = {"peticion": 0, "biblioteca": 0, "historico": 0}
    for pieza in piezas:
        recuento[pieza.fuente] += 1
    return OrigenDatos(**recuento)


def unidades(pieza: PiezaRef) -> int:
    """Cantidad efectiva: ``None`` se cuenta como 1 unidad (supuesto documentado)."""
    return pieza.cantidad if pieza.cantidad is not None else 1
