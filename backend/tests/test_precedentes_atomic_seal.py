from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from backend.app.precedentes.espacio import AlmacenEspacio, HuellaEspacio
from backend.app.precedentes.mantenimiento import RegistroEspacio


def _huella(identificador: str, creada_en: str) -> HuellaEspacio:
    return HuellaEspacio(
        modelo="modelo-prueba",
        dimensiones=2,
        version_frases="control-v1",
        huella_id=identificador * 64,
        vectores=((1.0, 0.0),),
        creada_en=creada_en,
    )


def test_rotacion_entre_validacion_y_escritura_no_deja_sello_obsoleto(
    tmp_path: Path, monkeypatch
) -> None:
    almacen = AlmacenEspacio(tmp_path / "espacio.sqlite3")
    anterior = _huella("a", "2026-11-14T10:00:00+00:00")
    nueva = _huella("b", "2026-11-14T10:01:00+00:00")
    almacen.registrar(anterior)
    registro = RegistroEspacio(almacen, ahora=lambda: "2026-11-14T10:02:00+00:00")
    abrir_db = registro._db
    primera_apertura = True

    @contextmanager
    def abrir_db_con_rotacion():
        nonlocal primera_apertura
        with abrir_db() as db:
            if primera_apertura:
                primera_apertura = False
                almacen.rotar(nueva, "2026-11-14T10:01:00+00:00")
            yield db

    monkeypatch.setattr(registro, "_db", abrir_db_con_rotacion)

    sellado = registro.sellar(
        "cache-key",
        anterior.modelo,
        anterior.dimensiones,
        "descriptor-v1",
        huella_esperada=anterior.huella_id,
    )

    assert sellado is False
    assert registro.sello("cache-key") is None
