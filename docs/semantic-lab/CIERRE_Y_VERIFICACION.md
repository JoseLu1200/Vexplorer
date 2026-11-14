# Cierre y verificación de la entrega

Fecha: 2026-11-14. Rama de entrega: `experiment/semantic-furniture`, base `42095101ac93c9c39d62271a62333ed924f8e51c`. El usuario autorizó explícitamente organizar la documentación y ejecutar `git add`, `git commit` y `git push`. La entrega reúne el laboratorio inicial y las ampliaciones posteriores de datasets y clasificadores.

## Verificación final sobre el árbol de entrega

| Comprobación | Resultado observado |
|---|---|
| Suite completa `python -m pytest -q` | **509 passed en 90,64 s** |
| Ruff sobre `tools/semantic_lab` y sus ocho archivos de tests | Sin hallazgos |
| `python -m compileall -q tools/semantic_lab` | Correcto |
| JSON de evidencia | Diez archivos parseables antes de este registro; sin originales CAD ni pesos |
| Enlaces locales Markdown | Todos los enlaces comprobados del índice, informes y README resolvieron |
| Integridad de entradas Jev/EG2, comprobación posterior | 160/160 pares texto/render coincidentes; 320/320 identidades de petición coincidentes |
| Evaluación pagada Jev | 320 respuestas válidas; cada petición tuvo un intento; cero errores API en ese lote |

La suite final usó Python 3.14.2, pytest 9.0.2, NumPy 2.3.5, SciPy 1.17.0, scikit-learn 1.8.0 y joblib 1.5.3. Los modelos preentrenados se habían ejecutado en el entorno de inferencia documentado; la suite no vuelve a descargar pesos ni repite peticiones pagadas.

La cifra inicial de 466 tests y las verificaciones intermedias se conservan como historia de sus fases. La cifra de 509 corresponde al árbol final que incorpora también probes de datasets/app, clasificadores locales y Jev.

## Revisión final GPT-6 Astra

El dictamen ampliado considera válida la evidencia como **experimento aislado y comparación retrospectiva exploratoria**, sin hallazgos bloqueantes tras corregir los puntos identificados. No acredita superioridad causal, producción, verdad técnica humana, detección OOD general ni estimación económica.

Además de los hallazgos iniciales, se corrigieron:

- Nombre de la métrica entre vistas Plank: Hit@1, no Recall@1.
- Dependencia directa de joblib y persistencia de modelos propios reutilizable desde otro proceso.
- Paridad de macro-F1/balanced accuracy entre Jev y el evaluador local; se recalculó desde respuestas guardadas, sin API.
- Persistencia Jev limitada a campos permitidos de respuesta; se descartan campos extra del proveedor.
- Deduplicación de solicitudes simultáneas, reintentos limitados a 429/529 y esperas acotadas.
- Presupuesto HTTP compartido que cuenta reintentos e intentos fallidos.
- Separación entre tokens reportados originalmente, tokens de nuevas respuestas sin caché y coste desconocido cuando la entrega es ambigua.
- Documentación de snapshots de app, métricas proxy, revisión posterior de integridad y rutas genéricas para publicación.

Los controles añadidos después de los ensayos se identifican como tales. No se afirma que protegieran retroactivamente las ejecuciones anteriores. Los resultados originales se conservaron y las correcciones de métricas mantuvieron registros previos de procedencia.

## Contenido de la entrega

Se publican código del laboratorio, pruebas, extras de dependencias, documentación Markdown, registros de coordinación y resúmenes JSON seleccionados. El [índice](README.md) organiza todas las fases y los [resultados iniciales](../SEMANTIC_LAB_2026-11-14.md) siguen identificados como una corrida histórica.

No se incluyen credenciales, archivos `.env`, CAD/PDF de terceros, renders derivados, pesos, cachés de API, entornos virtuales, modelos Joblib ni la instantánea de los cambios paralelos de la app. Esos artefactos locales se describen para reproducción autorizada, no se redistribuyen con el código.

El repositorio fuente de la app evolucionó en otra rama durante las pruebas. Se probaron snapshots identificados y se conservaron sus hashes; sus cambios de producto no forman parte de este commit. Publicar el laboratorio no integra Gemma o Jev en los endpoints de la app y no despliega servicios.

## Identificación y siguientes usos

El commit que contiene este archivo identifica la entrega; se puede consultar con `git log -1 --oneline` y `git show --stat HEAD` desde esta rama. La respuesta de entrega comunica el commit y el resultado del push comprobado contra el remoto.

Para usar los resultados, distinguir recuperación vectorial, clasificación cerrada, abstención y evaluación económica. La regresión logística sobre EG2/geometría mejoró la taxonomía amplia ensayada; Jev visual mejoró la pequeña y mostró rechazo útil en el control mecánico. Ninguno de esos resultados convierte los vecinos en comparables de precio sin un histórico y una evaluación independientes.
