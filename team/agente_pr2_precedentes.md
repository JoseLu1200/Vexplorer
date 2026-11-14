# Agente PR2 — precedentes

## Identidad y autorización

- Identidad: agente de IA revisor/implementador de precedentes para la integración PR2.
- Autorización: delegación explícita del coordinador bajo la solicitud vigente del usuario, 2026-11-14.
- No representa ni deduce una identidad humana.

## Alcance

- `backend/app/precedentes/piezas.py`
- `backend/app/precedentes/lotes.py`
- `backend/app/precedentes/analogia.py`
- `backend/app/precedentes/hibrido.py`
- Pruebas focales `backend/tests/test_precedentes_{lotes,analogia,hibrido}.py`
- Este registro.
- Sin commits; integración y `api_embeddings.py` pertenecen a coordinación/seguridad.

## Tarea

1. Conservar `cantidad=None` y excluir esa pieza de cálculos exactos de lote.
2. Recuperar suficientes comparables de analogía válidos, sin que candidatos descartados consuman el límite solicitado.
3. Rechazar o normalizar de forma estable pesos finitos cuya suma desborde.

## Estado y verificación

- Estado inicial: revisión en solo lectura completada; 77 pruebas focales existentes aprobadas.
- RED observado: los tres tests focales fallaron por las causas esperadas
  (cantidad ambigua computada como una unidad, suma infinita aceptada y límite
  consumido por comparables no estimables).
- GREEN implementado: cantidad desconocida a `sin_clasificar`; analogía examina
  un pool acotado hasta completar comparables válidos; suma de pesos no finita
  rechazada.
- Verificación final focal: `python -m pytest -q` sobre lotes, analogía e
  híbrido → 30 aprobadas en 8,74 s. `ruff check` y `git diff --check` sobre
  los archivos propios → sin errores.
- Límites deliberados fuera de este bloque: fallback geométrico visible, MAD nulo sin alerta y estimación por superficie con aviso de piezas sobredimensionadas.
