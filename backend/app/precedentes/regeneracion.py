"""Idea 2.5: detección y regeneración de embeddings obsoletos de la biblioteca (hallazgo H9).

Un elemento es obsoleto si su ``result_revision`` no es la revisión vigente del run, o si su
embedding falta o no se puede leer (corrupto o de espacio incompatible). La detección es pura sobre
hechos ya recopilados; la regeneración reutiliza el caché por ``embedding_cache_key`` y guarda con
los métodos existentes del repositorio.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import Field

from backend.app.contratos.modelos import (
    EmbeddingMetadata,
    LibraryItem,
    Result,
    RunSnapshot,
)
from backend.app.precedentes.comun import ModeloEstricto
from backend.app.semantic.descriptor import (
    build_descriptor,
    descriptor_fingerprint,
    semantic_text,
)
from backend.app.semantic.embeddings import (
    EmbeddingProviderError,
    EmbeddingResult,
    embedding_cache_key,
)

MotivoObsolescencia = Literal["revision_obsoleta", "embedding_ausente", "embedding_corrupto", "espacio_distinto"]
EstadoVector = Literal["ok", "ausente", "corrupto", "espacio_distinto"]
EstadoRegeneracion = Literal["pendiente", "regenerado", "de_cache", "error", "omitido"]


class ProveedorEmbeddings(Protocol):
    model: str
    dimensions: int

    def embed(self, text: str) -> EmbeddingResult: ...


class RepositorioBiblioteca(Protocol):
    def get_library_items(self) -> tuple[LibraryItem, ...]: ...

    def save_library_item(self, item: LibraryItem) -> None: ...

    def get_run(self, run_id: str) -> RunSnapshot: ...

    def get_result(self, run_id: str, revision: int | None = None) -> Result: ...

    def get_embedding(self, cache_key: str, model: str, dimensions: int, descriptor_version: str) -> tuple[float, ...]: ...

    def save_embedding(self, cache_key: str, model: str, dimensions: int, descriptor_version: str, vector: tuple[float, ...]) -> None: ...


class HechosElemento(ModeloEstricto):
    """Hechos observados de un elemento; entrada de la detección pura."""

    elemento: LibraryItem
    revision_vigente: int | None
    run_existe: bool
    estado_vector: EstadoVector


class ElementoObsoleto(ModeloEstricto):
    library_item_id: str
    run_id: str
    revision_guardada: int
    revision_vigente: int | None
    motivos: tuple[MotivoObsolescencia, ...]


class ResultadoElemento(ModeloEstricto):
    library_item_id: str
    run_id: str
    revision_guardada: int
    revision_vigente: int | None
    motivos: tuple[MotivoObsolescencia, ...]
    estado: EstadoRegeneracion
    codigo: str | None = None
    motivo_omision: str | None = None
    embedding: EmbeddingMetadata | None = None


class InformeRegeneracion(ModeloEstricto):
    simular: bool
    total_elementos: int = Field(ge=0)
    total_obsoletos: int = Field(ge=0)
    limite: int = Field(ge=1)
    modelo: str | None = None
    dimensiones: int | None = None
    elementos: tuple[ResultadoElemento, ...]


def estado_vector(repositorio: RepositorioBiblioteca, elemento: LibraryItem, espacio_vigente: tuple[str, int] | None = None) -> EstadoVector:
    """``espacio_vigente`` = (modelo, dimensiones) del proveedor; sin proveedor no se juzga el espacio."""
    metadatos = elemento.embedding
    if metadatos is None:
        return "ausente"
    if espacio_vigente is not None and (metadatos.model, metadatos.dimensions) != espacio_vigente:
        return "espacio_distinto"
    try:
        repositorio.get_embedding(metadatos.cache_key, metadatos.model, metadatos.dimensions, metadatos.descriptor_version)
    except KeyError:
        return "ausente"
    except (ValueError, EmbeddingProviderError):
        return "corrupto"
    return "ok"


def recopilar_hechos(repositorio: RepositorioBiblioteca, espacio_vigente: tuple[str, int] | None = None) -> tuple[HechosElemento, ...]:
    hechos: list[HechosElemento] = []
    for elemento in sorted(repositorio.get_library_items(), key=lambda item: item.id):
        try:
            vigente = repositorio.get_run(elemento.run_id).result_revision
            existe = True
        except KeyError:
            vigente, existe = None, False
        hechos.append(HechosElemento(elemento=elemento, revision_vigente=vigente, run_existe=existe, estado_vector=estado_vector(repositorio, elemento, espacio_vigente)))
    return tuple(hechos)


def detectar_obsoletos(hechos: tuple[HechosElemento, ...]) -> tuple[ElementoObsoleto, ...]:
    """Función pura: lista elementos obsoletos ordenados por id."""
    obsoletos: list[ElementoObsoleto] = []
    for hecho in hechos:
        motivos: list[MotivoObsolescencia] = []
        if not hecho.run_existe or hecho.revision_vigente != hecho.elemento.result_revision:
            motivos.append("revision_obsoleta")
        if hecho.estado_vector == "ausente":
            motivos.append("embedding_ausente")
        elif hecho.estado_vector == "corrupto":
            motivos.append("embedding_corrupto")
        elif hecho.estado_vector == "espacio_distinto":
            motivos.append("espacio_distinto")
        if motivos:
            obsoletos.append(ElementoObsoleto(
                library_item_id=hecho.elemento.id,
                run_id=hecho.elemento.run_id,
                revision_guardada=hecho.elemento.result_revision,
                revision_vigente=hecho.revision_vigente,
                motivos=tuple(motivos),
            ))
    obsoletos.sort(key=lambda item: item.library_item_id)
    return tuple(obsoletos)


def _resultado(obsoleto: ElementoObsoleto, estado: EstadoRegeneracion, **extra: object) -> ResultadoElemento:
    return ResultadoElemento(
        library_item_id=obsoleto.library_item_id,
        run_id=obsoleto.run_id,
        revision_guardada=obsoleto.revision_guardada,
        revision_vigente=obsoleto.revision_vigente,
        motivos=obsoleto.motivos,
        estado=estado,
        **extra,
    )


def regenerar_elemento(
    repositorio: RepositorioBiblioteca,
    proveedor: ProveedorEmbeddings,
    elemento: LibraryItem,
    obsoleto: ElementoObsoleto,
    ahora: Callable[[], str],
) -> ResultadoElemento:
    if obsoleto.revision_vigente is None:
        return _resultado(obsoleto, "omitido", motivo_omision="sin_revision_vigente")
    try:
        resultado = repositorio.get_result(elemento.run_id, obsoleto.revision_vigente)
    except KeyError:
        return _resultado(obsoleto, "omitido", motivo_omision="revision_vigente_inexistente")
    try:
        descriptor = build_descriptor(resultado)
    except ValueError as exc:
        return _resultado(obsoleto, "omitido", motivo_omision=str(exc) or "descriptor_no_disponible")
    modelo, dimensiones, version = proveedor.model, proveedor.dimensions, descriptor.descriptor_version
    texto = semantic_text(descriptor)
    clave = embedding_cache_key(version, modelo, dimensiones, texto)
    try:
        repositorio.get_embedding(clave, modelo, dimensiones, version)
        estado: EstadoRegeneracion = "de_cache"
    except (KeyError, ValueError, EmbeddingProviderError):
        # Ausente o corrupto en caché: se vuelve a embeber y se sobrescribe.
        try:
            generado = proveedor.embed(texto)
            if generado.model != modelo or generado.dimensions != dimensiones:
                raise EmbeddingProviderError("embedding_space_incompatible")
            repositorio.save_embedding(clave, generado.model, generado.dimensions, version, generado.vector)
        except EmbeddingProviderError as exc:
            return _resultado(obsoleto, "error", codigo=str(exc) or "semantic_provider_failed")
        estado = "regenerado"
    metadatos = EmbeddingMetadata(model=modelo, dimensions=dimensiones, descriptor_version=version, cache_key=clave, status="cache" if estado == "de_cache" else "generated")
    actualizado = LibraryItem(
        id=elemento.id,
        run_id=elemento.run_id,
        result_revision=resultado.result_revision,
        label=elemento.label,
        descriptor=descriptor,
        descriptor_fingerprint=descriptor_fingerprint(descriptor),
        created_at=ahora(),
        embedding=metadatos,
    )
    try:
        repositorio.save_library_item(actualizado)
    except (KeyError, ValueError) as exc:
        return _resultado(obsoleto, "error", codigo=f"guardado_fallido:{exc}")
    return _resultado(obsoleto, estado, embedding=metadatos)


def ahora_utc() -> str:
    return datetime.now(UTC).isoformat()


def regenerar_obsoletos(
    repositorio: RepositorioBiblioteca,
    proveedor: ProveedorEmbeddings | None,
    simular: bool,
    limite: int,
    ahora: Callable[[], str] = ahora_utc,
) -> InformeRegeneracion:
    """Detecta y (si ``simular`` es False) regenera. Requiere proveedor cuando no se simula."""
    if not simular and proveedor is None:
        raise LookupError("proveedor_no_disponible")
    espacio = (proveedor.model, proveedor.dimensions) if proveedor is not None else None
    hechos = recopilar_hechos(repositorio, espacio)
    obsoletos = detectar_obsoletos(hechos)
    por_id = {hecho.elemento.id: hecho.elemento for hecho in hechos}
    seleccion = obsoletos[:limite]
    if simular:
        elementos = tuple(_resultado(item, "pendiente") for item in seleccion)
    else:
        assert proveedor is not None
        elementos = tuple(regenerar_elemento(repositorio, proveedor, por_id[item.library_item_id], item, ahora) for item in seleccion)
    return InformeRegeneracion(
        simular=simular,
        total_elementos=len(hechos),
        total_obsoletos=len(obsoletos),
        limite=limite,
        modelo=proveedor.model if proveedor is not None else None,
        dimensiones=proveedor.dimensions if proveedor is not None else None,
        elementos=elementos,
    )
