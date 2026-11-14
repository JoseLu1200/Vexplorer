# Agente semántica v2 — dataset

## Identidad y autorización

- Identidad: agente de IA `semantica_v2_dataset`; no representa a una persona.
- Rol: ampliar el corpus sintético semántico sin tocar runtime ni contratos.
- Archivo creado por delegación explícita de `/root` el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: crear una versión nueva y sustancial del corpus, con 60–100 casos, muchas topologías independientes, dificultad/unknowns explícitos y partición sin fuga.
- Estado: diagnóstico terminado; implementación TDD en curso.

## Alcance y reservas

- Propiedad exclusiva para v2: `tools/prepare_semantic_corpus.py`, `tests/test_prepare_semantic_corpus.py`, `docs/CORPUS_SEMANTICO.md`, nuevos auxiliares de dataset y este registro.
- Solo lectura: runtime, contratos, evaluador, runner y referencias privadas ya materializadas.
- La reserva histórica de `agente_cierre_corpus.md` conserva v1 congelado; la delegación de raíz transfiere estas rutas a este agente solo para una versión nueva retrocompatible.
- No se revelarán respuestas privadas a agentes de runtime ni se tocarán artefactos holdout existentes.

## Hecho en el último bloque

- Leídas reglas raíz, registro histórico del corpus y fuentes objetivo.
- Diagnosticado que v1 tiene 6 proyectos/topologías y 18 casos; sus variantes repiten la misma geometría con vistas omitidas, por lo que no constituyen diseños independientes.
- Implementado v2 con 16 topologías (10 desarrollo, 6 reservado), 80 casos y metadatos privados de dificultad, observabilidad y desconocidos.
- Corregida la cohorte antes del baseline: los tres holdouts v1 pasan a desarrollo/regresión y los seis holdouts v2 son topologías nuevas.
- Artefacto público rev2 generado en `.runtime/semantic-v2-20261114-rev2/public`; la ruta privada queda retenida hasta congelar predicciones.
- Añadida firma visible normalizada por proyección, independiente de roles/uniones privadas: 10 firmas development y 6 reserved, sin cruces.
- Eliminado el sellador duplicado del preparador; el CLI delega al helper canónico de evaluación y acepta subconjuntos por lote.
- Compatibilidad v1 comprobada byte a byte contra snapshot del generador original con `PYTHONHASHSEED=0`.
- Rev2 invalidada al detectar en smoke desarrollo solapamiento global de V1/V2; rev3 desplaza cada proyección por su bbox y garantiza gap mínimo de 100 mm solo para v2.
- Rev3 generada en `.runtime/semantic-v2-20261114-rev3/`; mantiene topologías/splits/IDs y cambia hashes de inputs. Pendiente preview visual de raíz.
- Erratum rev4: alternativas preservan `supported_by` obligatorio y añaden `fixed_to` opcional; detectado tras iniciar inferencia rev3 e inspeccionar el smoke dev `sx-001`, pero antes de predicciones semánticas o scores holdout. Ningún contenido holdout formó el erratum.
- Artefacto válido `.runtime/semantic-v2-20261114-rev4-reference-erratum/`: sus 82 archivos públicos se copiaron literalmente de rev3; solo cambia la referencia privada.
- Auditoría privada del erratum: 80 alternativas, `removed_count=0`, 80 adiciones `supported_by|required=true` y ningún otro caso/campo modificado.
- Causa hashseed confirmada en orden de `CLASS` de `ezdxf`; futuras generaciones v2 canonicalizan esa colección. Test CLI con seeds 1/4 exige árboles públicos/privados byte-idénticos. Artefactos rev3/erratum intactos.

## Siguiente bloque

- Esperar freeze de ambos runs antes de revelar a evaluación la ruta privada rev2.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | Mantener v1 congelado y añadir v2 | Evitar invalidar hashes y referencias selladas | Delegación de `/root` y registro histórico |
| 2026-11-14 | Particionar por proyecto y firma estructural antes de generar vistas | Impedir fuga por variantes o geometría casi idéntica | Requisito explícito de la tarea |
| 2026-11-14 | No puntuar `fixed_to` como observable solo por contacto/proyección | Un plano ortográfico pobre no revela tornillos, cola o herrajes | Limitación geométrica del benchmark |
| 2026-11-14 | Mover todos los holdouts v1 a desarrollo y reservar seis topologías nuevas | El holdout v2 no puede reutilizar diseños ya vistos en diagnóstico | Corrección solicitada por `/root` antes del baseline |

## Dependencias / avisos

- Necesito de: evaluación debe consumir el formato v2 sin exponer la referencia al runtime.
- Afecta a: generación del benchmark y documentación offline; no cambia runtime.
- Aviso realizado: diseño comunicado a `/root` mediante la delegación activa.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| RED expansión | `python -m pytest -q tests/test_prepare_semantic_corpus.py` | 8 fallos esperados por v2 ausente | antes de implementación |
| RED holdout nuevo | `python -m pytest -q tests/test_prepare_semantic_corpus.py::test_v2_reserved_topologies_exclude_every_previously_used_v1_holdout` | fallo esperado: incluía tres holdouts v1 | corregido antes del baseline |
| Focal final | `python -m pytest -q tests/test_prepare_semantic_corpus.py` | 10 passed | sin red |
| Integración semántica | `python -m pytest -q tests/test_prepare_semantic_corpus.py tests/test_semantic_evaluation.py tests/test_run_general_benchmark.py` | 41 passed | observada antes de cambio concurrente posterior |
| Lint propio | `python -m ruff check tools/prepare_semantic_corpus.py tools/semantic_corpus_v2.py tests/test_prepare_semantic_corpus.py` | all checks passed | alcance propio |
| Diff propio | `git diff --check -- ...` | exit 0 | alcance propio |
| Suite completa | `python -m pytest -q` | error de colección ajeno: `compare_semantic_reports` importado por test pero aún ausente en `evaluation.semantic` | evaluación modificada concurrentemente; fuera de alcance |
| Focal final actualizado | `python -m pytest -q tests/test_prepare_semantic_corpus.py` | 13 passed | incluye holdout nuevo, firma visible, snapshot v1 y CLI de sellado |
| Integración final actualizada | `python -m pytest -q tests/test_prepare_semantic_corpus.py tests/test_semantic_evaluation.py tests/test_run_general_benchmark.py` | 47 passed | sin red |
| Suite completa, último intento | `python -m pytest -q` | error de colección ajeno: falta `evaluation.assembly` | nuevo módulo/prueba concurrente fuera de alcance |
| RED layout v2 | `python -m pytest -q tests/test_prepare_semantic_corpus.py::test_v2_orthographic_view_layer_bounding_boxes_never_overlap` | fallo esperado `sx-001`, V1/V2 | offset lateral heredado incorrecto |
| Gate rev3 | bbox global 80 casos + fixture 800×320 + snapshot v1 | 3 passed | gap mínimo 100 mm; v1 intacto |
| Focal rev3 | `python -m pytest -q tests/test_prepare_semantic_corpus.py` | 15 passed | artefacto rev3 generado después |
| RED alternativa aditiva | test focal de soporte + fijación | fallo esperado: `supported_by` desaparecía | defecto conceptual reproducido sin predicciones |
| Público rev3 vs rev4 erratum | hash de cada uno de 82 archivos | 0 diferencias | no requiere repetir inferencia |
| RED reproducibilidad cross-process | CLI v2 con `PYTHONHASHSEED=1` y `4` | árboles distintos por orden de clases DXF | causa confirmada |
| GREEN reproducibilidad cross-process | mismo test tras canonicalizar clases v2 | passed; árboles público/privado idénticos | no modifica artefactos congelados |
| Focal final | `python -m pytest -q tests/test_prepare_semantic_corpus.py` | 17 passed | incluye v1 snapshot y seeds 1/4 |
| Integración final | corpus + evaluación semántica + runner | 51 passed | sin red |

## Bloqueos y cierre

- Bloqueos: la suite global está transitoriamente bloqueada por `evaluation.assembly`, fuera del alcance propio.
- Pendientes: sellar/evaluar con la referencia privada rev4 solo tras freeze; etiquetar por separado inferencia rev3 y erratum rev4.
- Reservas liberadas: no aplica.
- Entrega a otra persona: `/root`, con formato, pruebas y límites de inferibilidad.
