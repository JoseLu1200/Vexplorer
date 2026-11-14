"""Idea 2.5: detección y regeneración de embeddings obsoletos de la biblioteca (hallazgo H9).

Un elemento es obsoleto si su ``result_revision`` no es la revisión vigente del run, o si su
embedding falta o no se puede leer (corrupto o de espacio incompatible). La detección es pura sobre
hechos ya recopilados; la regeneración reutiliza el caché por ``embedding_cache_key`` y guarda con
los métodos existentes del repositorio.

Con un ``ContextoEspacio`` (ver ``mantenimiento.RegistroEspacio``) la identidad del espacio incluye
la huella de las frases de control (2.6): un embedding sellado con una huella distinta de la
referencia vigente es obsoleto (``huella_retirada``) y su regeneración **no** reutiliza el caché,
porque ``cache_key`` no incluye la huella. Un embedding sin sello (anterior a este mecanismo) solo se
marca (``huella_desconocida``) si se pide con ``incluir_sin_huella``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
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

logger = logging.getLogger(__name__)

MotivoObsolescencia = Literal["revision_obsoleta", "embedding_ausente", "embedding_corrupto", "espacio_distinto", "huella_retirada", "huella_desconocida"]
EstadoVector = Literal["ok", "ausente", "corrupto", "espacio_distinto", "huella_retirada", "huella_desconocida"]
EstadoRegeneracion = Literal["pendiente", "regenerado", "de_cache", "error", "omitido"]


class ProveedorEmbeddings(Protocol):
    model: str
    dimensions: int

    def embed(self, text: str) -> EmbeddingResult: ...


class RepositorioBiblioteca(Protocol):
    def get_library_items(self) -> tuple[LibraryItem, ...]: ...

    def save_library_item(self, item: LibraryItem) -> None: ...

    def get_run(self, run_id: str) -> RunSnapshot: ...

    def get_library_item(self, run_id: str) -> LibraryItem: ...

    def get_result(self, run_id: str, revision: int | None = None) -> Result: ...

    def get_embedding(self, cache_key: str, model: str, dimensions: int, descriptor_version: str) -> tuple[float, ...]: ...

    def save_embedding(self, cache_key: str, model: str, dimensions: int, descriptor_version: str, vector: tuple[float, ...]) -> None: ...

    def invalidate_embeddings(self, model: str, dimensions: int) -> int: ...


@dataclass(frozen=True)
class Sello:
    """Huella del espacio (2.6) y versión de las frases de control con que se calculó."""

    huella_id: str
    version_frases: str


class LatidoPerdido(RuntimeError):
    """Un ``latido`` la lanza cuando el candado de la operación se ha perdido: hay que abortar."""


# Motivos por los que el enganche tras guardar puede regenerar sin tocar la revisión guardada.
MOTIVOS_DE_ESPACIO: frozenset[str] = frozenset({"huella_retirada", "espacio_distinto", "embedding_ausente", "embedding_corrupto"})


class ContextoEspacio(Protocol):
    """Vincula cada embedding guardado con la huella del espacio (2.6) bajo la que se generó."""

    def referencia_vigente(self, modelo: str, dimensiones: int) -> Sello | None: ...

    def sello(self, cache_key: str) -> Sello | None: ...

    def sellar(
        self, cache_key: str, modelo: str, dimensiones: int, descriptor_version: str, huella_esperada: str | None = None, generado_en: str | None = None
    ) -> bool: ...

    def registrar_guardado(self, item: LibraryItem) -> object: ...


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
    abortado: bool = False
    modelo: str | None = None
    dimensiones: int | None = None
    elementos: tuple[ResultadoElemento, ...]


def estado_vector(
    repositorio: RepositorioBiblioteca,
    elemento: LibraryItem,
    espacio_vigente: tuple[str, int] | None = None,
    contexto: ContextoEspacio | None = None,
    incluir_sin_huella: bool = False,
) -> EstadoVector:
    """``espacio_vigente`` = (modelo, dimensiones) del proveedor; sin proveedor no se juzga el espacio.

    La identidad del espacio es (modelo, dimensiones, descriptor_version) más, con ``contexto``, la
    huella sellada del vector frente a la referencia vigente de (modelo, dimensiones).
    """
    metadatos = elemento.embedding
    if metadatos is None:
        return "ausente"
    if espacio_vigente is not None and (metadatos.model, metadatos.dimensions) != espacio_vigente:
        return "espacio_distinto"
    if metadatos.descriptor_version != elemento.descriptor.descriptor_version:
        return "espacio_distinto"
    try:
        repositorio.get_embedding(metadatos.cache_key, metadatos.model, metadatos.dimensions, metadatos.descriptor_version)
    except KeyError:
        return "ausente"
    except (ValueError, EmbeddingProviderError):
        return "corrupto"
    if contexto is not None:
        vigente = contexto.referencia_vigente(metadatos.model, metadatos.dimensions)
        if vigente is not None:
            sello = contexto.sello(metadatos.cache_key)
            if sello is None or sello.version_frases != vigente.version_frases:
                # Sin sello o calculado con otras frases de control: no es comparable con la referencia.
                return "huella_desconocida" if incluir_sin_huella else "ok"
            if sello.huella_id != vigente.huella_id:
                return "huella_retirada"
    return "ok"


def recopilar_hechos(
    repositorio: RepositorioBiblioteca,
    espacio_vigente: tuple[str, int] | None = None,
    contexto: ContextoEspacio | None = None,
    incluir_sin_huella: bool = False,
    solo_ids: frozenset[str] | None = None,
) -> tuple[HechosElemento, ...]:
    hechos: list[HechosElemento] = []
    for elemento in sorted(repositorio.get_library_items(), key=lambda item: item.id):
        if solo_ids is not None and elemento.id not in solo_ids:
            continue
        try:
            vigente = repositorio.get_run(elemento.run_id).result_revision
            existe = True
        except KeyError:
            vigente, existe = None, False
        hechos.append(HechosElemento(elemento=elemento, revision_vigente=vigente, run_existe=existe, estado_vector=estado_vector(repositorio, elemento, espacio_vigente, contexto, incluir_sin_huella)))
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
        elif hecho.estado_vector in {"espacio_distinto", "huella_retirada", "huella_desconocida"}:
            motivos.append(hecho.estado_vector)
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


def _cache_en_espacio_retirado(contexto: ContextoEspacio | None, obsoleto: ElementoObsoleto, clave: str, modelo: str, dimensiones: int) -> bool:
    """La caché por ``cache_key`` no distingue huellas: si el vector está sellado con otra, no vale."""
    if contexto is None:
        return False
    if "huella_retirada" in obsoleto.motivos or "huella_desconocida" in obsoleto.motivos:
        return True
    vigente = contexto.referencia_vigente(modelo, dimensiones)
    sello = contexto.sello(clave)
    return vigente is not None and sello is not None and sello != vigente


def _modificado_durante_regeneracion(repositorio: RepositorioBiblioteca, leido: LibraryItem) -> bool:
    """Relee el elemento justo antes de escribir (no hay escritura condicional en el repositorio: queda
    solo la ventana entre esta lectura y ``save_library_item``)."""
    try:
        actual = repositorio.get_library_item(leido.run_id)
    except KeyError:
        return True
    return (actual.created_at, actual.result_revision, actual.descriptor_fingerprint) != (leido.created_at, leido.result_revision, leido.descriptor_fingerprint)


def regenerar_elemento(
    repositorio: RepositorioBiblioteca,
    proveedor: ProveedorEmbeddings,
    elemento: LibraryItem,
    obsoleto: ElementoObsoleto,
    ahora: Callable[[], str],
    contexto: ContextoEspacio | None = None,
    latido: Callable[[], None] | None = None,
    conservar_revision: bool = False,
) -> ResultadoElemento:
    """Regenera el embedding de un elemento.

    ``conservar_revision`` reconstruye el descriptor de la revisión ya guardada en la biblioteca en
    lugar de la vigente del run (el enganche tras guardar no puede cambiar lo que el usuario guardó).
    ``latido`` actúa de *fencing*: se invoca justo antes de cada escritura y lanza si el candado se perdió.
    """
    revision = elemento.result_revision if conservar_revision else obsoleto.revision_vigente
    if revision is None:
        return _resultado(obsoleto, "omitido", motivo_omision="sin_revision_vigente")
    try:
        resultado = repositorio.get_result(elemento.run_id, revision)
    except KeyError:
        return _resultado(obsoleto, "omitido", motivo_omision="revision_vigente_inexistente")
    try:
        descriptor = build_descriptor(resultado)
    except ValueError as exc:
        return _resultado(obsoleto, "omitido", motivo_omision=str(exc) or "descriptor_no_disponible")
    modelo, dimensiones, version = proveedor.model, proveedor.dimensions, descriptor.descriptor_version
    texto = semantic_text(descriptor)
    clave = embedding_cache_key(version, modelo, dimensiones, texto)
    # La huella se toma ANTES de embeber: si la referencia cambia mientras tanto, no se sella.
    referencia = contexto.referencia_vigente(modelo, dimensiones) if contexto is not None else None
    try:
        if _cache_en_espacio_retirado(contexto, obsoleto, clave, modelo, dimensiones):
            raise KeyError(clave)
        repositorio.get_embedding(clave, modelo, dimensiones, version)
        estado: EstadoRegeneracion = "de_cache"
    except (KeyError, ValueError, EmbeddingProviderError):
        # Ausente, corrupto o de un espacio retirado en caché: se vuelve a embeber y se sobrescribe.
        try:
            generado = proveedor.embed(texto)
            if generado.model != modelo or generado.dimensions != dimensiones:
                raise EmbeddingProviderError("embedding_space_incompatible")
            if latido is not None:
                latido()
            repositorio.save_embedding(clave, generado.model, generado.dimensions, version, generado.vector)
        except EmbeddingProviderError as exc:
            return _resultado(obsoleto, "error", codigo=str(exc) or "semantic_provider_failed")
        estado = "regenerado"
        if contexto is not None and referencia is not None:
            contexto.sellar(clave, modelo, dimensiones, version, huella_esperada=referencia.huella_id)
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
    if latido is not None:
        latido()
    if _modificado_durante_regeneracion(repositorio, elemento):
        # El usuario guardó otra cosa mientras se embebía: escribir ahora pisaría su guardado.
        return _resultado(obsoleto, "omitido", motivo_omision="modificado_durante_regeneracion")
    try:
        repositorio.save_library_item(actualizado)
    except (KeyError, ValueError) as exc:
        return _resultado(obsoleto, "error", codigo=f"guardado_fallido:{exc}")
    if contexto is not None:
        try:
            contexto.registrar_guardado(actualizado)
        except Exception:
            logger.warning("no se pudo registrar la regeneracion de %s", elemento.id, exc_info=True)
    return _resultado(obsoleto, estado, embedding=metadatos)


def ahora_utc() -> str:
    return datetime.now(UTC).isoformat()


def _solo_por_espacio(obsoletos: tuple[ElementoObsoleto, ...], elementos: dict[str, LibraryItem]) -> tuple[ElementoObsoleto, ...]:
    """Descarta ``revision_obsoleta`` y los elementos sin embedding; deja solo motivos de espacio."""
    seleccion: list[ElementoObsoleto] = []
    for obsoleto in obsoletos:
        if elementos[obsoleto.library_item_id].embedding is None:
            continue
        motivos = tuple(motivo for motivo in obsoleto.motivos if motivo != "revision_obsoleta")
        if motivos and all(motivo in MOTIVOS_DE_ESPACIO for motivo in motivos):
            seleccion.append(obsoleto.model_copy(update={"motivos": motivos}))
    return tuple(seleccion)


def regenerar_obsoletos(
    repositorio: RepositorioBiblioteca,
    proveedor: ProveedorEmbeddings | None,
    simular: bool,
    limite: int,
    ahora: Callable[[], str] = ahora_utc,
    contexto: ContextoEspacio | None = None,
    incluir_sin_huella: bool = False,
    latido: Callable[[], None] | None = None,
    solo_ids: frozenset[str] | None = None,
    conservar_revision: bool = False,
) -> InformeRegeneracion:
    """Detecta y (si ``simular`` es False) regenera. Requiere proveedor cuando no se simula.

    ``latido`` se invoca antes de cada elemento (renueva el lease del candado persistente) y puede
    abortar la ejecución lanzando ``LatidoPerdido`` (el informe es entonces parcial: ``abortado`` y el
    resto de elementos como ``omitido``). ``solo_ids`` restringe la detección a esos elementos.

    ``conservar_revision`` (enganche tras guardar): ignora ``revision_obsoleta``, actúa solo por
    ``MOTIVOS_DE_ESPACIO``, nunca sobre elementos sin embedding y no cambia la revisión guardada.
    """
    if not simular and proveedor is None:
        raise LookupError("proveedor_no_disponible")
    espacio = (proveedor.model, proveedor.dimensions) if proveedor is not None else None
    hechos = recopilar_hechos(repositorio, espacio, contexto, incluir_sin_huella, solo_ids)
    obsoletos = detectar_obsoletos(hechos)
    if conservar_revision:
        obsoletos = _solo_por_espacio(obsoletos, {hecho.elemento.id: hecho.elemento for hecho in hechos})
    por_id = {hecho.elemento.id: hecho.elemento for hecho in hechos}
    seleccion = obsoletos[:limite]
    abortado = False
    if simular:
        elementos = tuple(_resultado(item, "pendiente") for item in seleccion)
    else:
        assert proveedor is not None
        resultados: list[ResultadoElemento] = []
        for posicion, item in enumerate(seleccion):
            try:
                if latido is not None:
                    latido()
                resultados.append(regenerar_elemento(repositorio, proveedor, por_id[item.library_item_id], item, ahora, contexto, latido, conservar_revision))
            except LatidoPerdido:
                abortado = True
                resultados.extend(_resultado(pendiente, "omitido", motivo_omision="candado_perdido") for pendiente in seleccion[posicion:])
                break
        elementos = tuple(resultados)
    return InformeRegeneracion(
        simular=simular,
        total_elementos=len(hechos),
        total_obsoletos=len(obsoletos),
        limite=limite,
        abortado=abortado,
        modelo=proveedor.model if proveedor is not None else None,
        dimensiones=proveedor.dimensions if proveedor is not None else None,
        elementos=elementos,
    )
