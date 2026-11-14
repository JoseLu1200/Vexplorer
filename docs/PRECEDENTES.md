# Precedentes: ideas 2.1–3.5 del brainstorming de embeddings

Implementación en `backend/app/precedentes/` de las ideas 2.1 a 3.5 de [BRAINSTORMING_EMBEDDINGS](BRAINSTORMING_EMBEDDINGS.md). Incluye backend, API y tests; **no incluye interfaz**. Las ideas 1.1–1.7 corresponden a otro integrante.

## Principios

- Los números (medidas, cantidades, espesores) se comparan con reglas deterministas; el embedding solo aporta la parte semántica.
- Toda sugerencia basada en precedentes es una **hipótesis**, informa de su soporte (n/N, rango, ids de los vecinos) y **se abstiene** por debajo de un mínimo.
- Los datos sintéticos o publicados se declaran como tales; nunca se presentan como coste empresarial.
- No se modifican `contratos/` ni `historico/`: los modelos viven en el propio paquete y se podrán promover con acuerdo A/B.
- Todo `/api/v1/precedentes/*` devuelve **403 en acceso público**, igual que el histórico y la biblioteca.

## Endpoints

Prefijo común: `/api/v1/precedentes`.

| Idea | Método y ruta | Qué hace | Requiere proveedor |
|---|---|---|---|
| 2.1 | `POST /sugerencias` | Sugiere valores desconocidos del descriptor (dimensiones, espesores, material, acabado) a partir de vecinos de la misma familia ordenados por `geometric_match` | No |
| 2.2 | `POST /presupuesto-analogia` | Compara un coste calculado con el rango de costes de comparables del histórico; alerta en múltiplos de la dispersión robusta (MAD) | Solo en modo `semantic` |
| 2.3 | `POST /similares-hibrido` | `score = w_geo·geométrico + w_sem·coseno`, con componentes visibles; si falta el embedding, cae a solo geométrico y lo indica | No (usa vectores guardados) |
| 2.4 | `POST /piezas/gemelas` | Agrupa piezas casi idénticas de distintos orígenes con tolerancia por eje (≤ 50 mm), espesor y material exactos, sin encadenamiento; propone medida estándar | No |
| 2.5 | `POST /embeddings/regenerar` | Detecta embeddings obsoletos (revisión, ausencia, corrupción o espacio distinto); por defecto solo simula | Sí, para regenerar |
| 2.6 | `POST /embeddings/espacio/verificar`, `POST /embeddings/espacio/rotar`, `GET /embeddings/espacio`, `GET /embeddings/espacio/historico` | Huella del espacio con frases de control; detecta deriva del modelo y permite rotar la referencia | Sí, para verificar y rotar |
| 2.7 | `python -m tools.evaluar_recuperacion` | Precision@k, recall@k, MRR y nDCG@k con juicios de relevancia (`evaluation/recuperacion/`) | No |
| 3.1 | `POST /piezas/lotes` | Agrupa piezas de varios pedidos por (espesor, material, acabado) exactos y estima tableros por superficie (no es *nesting*) | No |
| 3.2 | `POST /busqueda` | Traduce una frase a filtros estructurados con un LLM (herramienta `aplicar_filtros_busqueda`, esquema estricto) y filtra de forma determinista; con `filtros` no llama al LLM | Sí, solo con `consulta` |
| 3.3 | `POST /imagen/indexar`, `POST /imagen/similares` | Mecanismo de embeddings de imagen de las vistas del plano; sin proveedor configurado | Sí (no hay ninguno en producción) |
| 3.4 | `POST /decisiones`, `GET /decisiones/resumen` | Registra aceptaciones o rechazos de comparables y recomienda pesos (AUC por componente); nunca se aplican solos | No |
| 3.5 | `POST /herrajes/registros`, `GET /herrajes/registros`, `POST /herrajes/sugerencias` | Almacén propio de herrajes por registro histórico y sugerencia por precedentes; probado solo con datos sintéticos | No |

## Almacenamiento

Cada funcionalidad con estado usa su propio SQLite en el directorio de datos: `precedentes_espacio.sqlite3`, `precedentes_decisiones.sqlite3`, `precedentes_imagen.sqlite3` y `precedentes_herrajes.sqlite3`. No se tocan las tablas existentes.

## Límites conocidos

- **Umbrales provisionales:** `score_minimo` de 2.1 (0,5), los múltiplos de dispersión de 2.2 y los umbrales de 3.3 no están calibrados. Dependen de la medición 1.1/1.2.
- **2.3** sigue usando el texto embebido actual, que incluye medidas e incógnitas (hallazgos H1/H2). Cambiarlo exige una nueva `descriptor_version` y volver a embeber la biblioteca.
- **2.6** no está ligado a `EmbeddingMetadata`; la verificación se lanza a mano.
- **2.5 y 2.6:** el candado y el intervalo mínimo están en memoria de cada proceso; no se coordinan entre varios workers.
- **3.3 y 3.5** son mecanismos sin datos ni modelo reales.
- **3.1** estima tableros por superficie con un aprovechamiento fijo; no coloca piezas.
- Los errores de validación del cuerpo usan el 422 por defecto de FastAPI (`detail`), como `api/history.py`; los errores de negocio usan el sobre `{schema_version, data, error}`.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q backend/tests/test_precedentes_*.py
```

Estado y evidencias en [team/pablo.md](../team/pablo.md).
