# Agente cierre corpus semántico

## Identidad y autorización

- Identidad: agente de IA `cierre_corpus`; no representa a una persona.
- Rol: A para el corpus y posible acuerdo contractual con B (`cierre_abstencion`).
- Archivo creado por delegación explícita de `/root` el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: generar un corpus sintético real de mobiliario con planos públicos pobres y referencia técnica privada para BOM, roles, montaje y alternativas válidas.
- Referencia: `docs/superpowers/plans/2026-11-14-poc-closure.md`, bloque Corpus.
- Estado: implementación y corpus congelados; pendiente revelar la ruta privada solo tras freeze de predicciones.

## Alcance y reservas

- Propiedad exclusiva: `tools/prepare_semantic_corpus.py`, helpers nuevos propios si fueran necesarios, `tests/test_prepare_semantic_corpus.py`, `docs/CORPUS_SEMANTICO.md`, datasets generados en rutas nuevas ignoradas y este registro.
- Solo lectura: runtime, contratos, runner estricto y evaluación semántica ajena.
- No se editará runtime ni `backend/app/contratos/` sin acuerdo explícito A/B y aviso a raíz.
- Solapes: ninguno detectado en las rutas reservadas.

## Hecho en el último bloque

- Generador `semantic-furniture-corpus-1` implementado por TDD y congelado; cualquier cambio requiere otra versión y artefactos nuevos.
- Corpus materializado fuera del repositorio: 18 ZIP públicos (12 desarrollo, 6 reservado) y referencia privada separada.
- Corregida una interpenetración de balda/divisor mediante ocurrencias izquierda/derecha; auditoría independiente confirma cero solapes de volumen positivo.
- Sellado post-inferencia acordado con `cierre_semantica`: SHA exacto, IDs completos y envelope `semantic-evaluation/v1` solo después del freeze.
- Añadido helper separado de sellado por lote para no modificar el generador/corpus v1 congelado; admite smoke o reservado, conserva fallos y valida hash de entrada por caso.
- Humo `sx-001` sellado después del freeze y evaluado sin acceso a holdout: roles y ocurrencias F1 0 con cobertura 1; montaje no evaluable por abstención explícita.
- Aprobado como A el delta contractual aditivo GeneralFurniture 0.6 solicitado por montaje; aclarado que `cierre_abstencion` sigue siendo B/único escritor de `modelos.py`.

## Siguiente bloque

- Esperar confirmación y hash de predicciones congeladas; entonces comunicar solo la ruta privada y ejecutar el sello offline.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | Referencia privada offline v1 por rol y relación, sin IDs de oráculo para matching | Evitar que igualdad dimensional suplante semántica | Acuerdo con `cierre_semantica` y aviso a `/root` |
| 2026-11-14 | ZIP público con `id,file,format,unit,view_kind,instruction,sha256` | Compatibilidad exacta con `tools/run_general_benchmark.py` | Instrucción de `/root` |
| 2026-11-14 | La verdad es de diseño sintético conocido | No atribuir revisión humana o industrial inexistente | Plan de cierre y acuerdo offline |
| 2026-11-14 | Unidad de partición = proyecto + firma estructural | Las clases de producto aparecen en ambos splits; el holdout es topológico | Acordado con raíz y semántica |
| 2026-11-14 | Alternativas solo de unión visualmente indistinguible | No aceptar add-ons ocultos que cambiarían BOM o dibujo | Revisión de raíz |

## Dependencias / avisos

- Necesito de: `cierre_semantica` consumirá las referencias privadas después de congelar predicciones.
- Afecta a: runner público estricto y evaluador semántico offline.
- Aviso realizado: contrato enviado/aprobado por `cierre_semantica`; `/root` informado.
- Cambio de `contratos/`: no aplica; no solicitado.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| RED inicial | `python -m pytest -q tests/test_prepare_semantic_corpus.py` | fallo de import esperado | generador ausente |
| Focal final | `python -m pytest -q tests/test_prepare_semantic_corpus.py` | 7 passed | sin red |
| Runner + corpus | `python -m pytest -q tests/test_prepare_semantic_corpus.py tests/test_run_general_benchmark.py` | 15 passed | sin red |
| Lint propio | `python -m ruff check tools/prepare_semantic_corpus.py tools/seal_semantic_reference.py tests/test_prepare_semantic_corpus.py` | all checks passed | solo alcance propio |
| Suite compartida | `python -m pytest -q` | 652 passed en 136.24 s | árbol concurrente integrado |
| Integración post-freeze | `python -m tools.seal_semantic_reference ...` + `python -m tools.evaluate_semantic ...` | 1 caso evaluado; hashes registrados en reporte a raíz | solo desarrollo `sx-001` |
| Artefacto real | auditoría independiente + `load_public_sources(..., strict_bundles=True)` | 18 aceptados; 6 proyectos/firmas; 0 solapes; 0 cruces | referencia no abierta por runtime |

## Bloqueos y cierre

- Bloqueos: apertura/sellado privado espera freeze de predicciones por diseño.
- Pendientes: suite compartida, freeze externo, sellado y transferencia privada.
- Reservas liberadas: no aplica.
- Entrega: pendiente a `/root`; la referencia privada se comunicará solo por ruta, sin contenido.
