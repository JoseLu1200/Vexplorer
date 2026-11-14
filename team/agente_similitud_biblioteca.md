# Agente API de biblioteca y similitud

## Identidad y autorización

- Identidad: agente de IA `library_api`; no representa a una persona.
- Rol: integración API de biblioteca dentro del swarm GPT-6.1 Sol solicitado por el usuario.
- Archivo creado por delegación explícita de `/root` el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: deduplicar diseños y revisiones antes del límite, combinar recuperación semántica con reranking técnico determinista y separar scores/advertencias/conteos en la API.
- Referencia: T12, recuperación histórica explicable y no engañosa.
- Estado: implementación congelada y verificación focal verde; lista para QA final de coordinación.

## Alcance y reservas

- Archivos editables: `backend/app/main.py`, pruebas dirigidas de API bajo `backend/tests/` y este registro.
- Solo lectura: contratos Pydantic, repositorio, descriptor semántico, frontend y evaluación.
- Compartido: `backend/app/main.py` contiene cambios concurrentes; se editará solo el bloque de biblioteca/similitud mediante hunks mínimos.
- Solape resuelto: `/root/similarity_backend` posee exclusivamente `backend/app/similarity/service.py`; esta tarea consumirá sus helpers sin editarlo. `/root/similarity_interface` posee el frontend.

## Hecho en el último bloque

- Leídas reglas, documentos obligatorios, registros de equipo e implementación/rutas actuales.
- Causa observada: la API limita después de ordenar registros, no colapsa fingerprints equivalentes y el modo semántico devuelve solo coseno sin ranking técnico ni conteos de repeticiones.
- Acuerdo directo con motor y raíz: campos aditivos de match/grupo, helper de deduplicación y ranking semántico; UI y evaluación avisadas de nombres y semántica antes de implementar.
- API conserva respuestas legacy por defecto y ofrece `include_summary=true` para envelopes con diseños/registros/duplicados; deduplica antes de `limit` y conserva todos los IDs equivalentes por match.
- Gate production fail-closed: solo guarda resultados completados y revisados con declaración `real_furniture`, referencia no vacía y aprobación explícita; rechaza `synthetic`, hashes de fixtures conocidos y fuentes sin hash. Persiste identidad autenticada o, en acceso anónimo, el nombre manual de la revisión.
- Config publica `library_requires_real_reviewed`; operación y UI recibieron el shape exacto. El hash admite manifests vigentes con clave superior y manifests operativos con `source.sha256`.
- HTML/JS/CSS sin hash se sirven con `Cache-Control: no-cache` para revalidar tras despliegue; API y otros assets conservan su política previa.

## Siguiente bloque

- Ninguno propio; coordinación ejecutará suite completa y revisión Astra sobre el árbol congelado.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | No modificar `contratos/` | Requiere acuerdo A/B y aviso C; no existe todavía para estos campos | Reglas del repositorio y delegación de `/root` |
| 2026-11-14 | Deduplicar antes de `limit` | El límite debe representar diseños distintos, no copias/revisiones | Solicitud del usuario |
| 2026-11-14 | Respuestas enriquecidas solo con opt-in | Preservar clientes legacy y permitir migración sin ruptura | Revisión de coordinación |
| 2026-11-14 | Publicación production es una declaración responsable, no certificación | En acceso anónimo el servidor no puede probar identidad ni realidad de una fuente | Hallazgo Astra aceptado por `/root` |

## Dependencias / avisos

- Necesito de: nada pendiente dentro del alcance propio.
- Afecta a: consumidor frontend y evaluación independiente de ranking.
- Aviso realizado: propiedad y propuesta de envelope comunicadas a `/root` y al agente del motor antes de editar producto.
- Cambio de `contratos/`: acuerdos A/B explícitos con `/root/similarity_backend` y avisos/confirmación UI antes de ambos deltas (`SimilarityMatch`/`SimilarityGroup` y procedencia de biblioteca).

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| RED API | `.venv\\Scripts\\python.exe -m pytest backend/tests/test_backend_library_api.py -q` | 2 fallos esperados, 6 pasan | La ruta aún devuelve lista sin envelope/dedupe/reranking |
| RED publicación | `.venv\\Scripts\\python.exe -m pytest backend/tests/test_library_publication.py -q` | 1 fallo esperado | Config/gate aún ausentes |
| API + publicación | `.venv\\Scripts\\python.exe -m pytest backend/tests/test_backend_library_api.py backend/tests/test_library_publication.py -q` | 11 passed | Sin proveedor ni red |
| Focal afectada final | `.venv\\Scripts\\python.exe -m pytest backend/tests/test_backend_library_api.py backend/tests/test_library_publication.py backend/tests/test_static_cache_headers.py backend/tests/test_backend_embeddings.py backend/tests/test_backend_semantic.py backend/tests/test_backend_api_viewer.py backend/tests/test_private_auth.py backend/tests/test_similarity_technical.py -q` | 51 passed, 1 warning externo | Suite completa pertenece a coordinación |
| Estática | `compileall`; `git diff --check`; `ruff check` sobre contrato/helper/tests propios | pasa | Ruff global de `main.py` conserva dos hallazgos preexistentes ajenos (`export_json`, `code`) |

## Bloqueos y cierre

- Bloqueos: ninguno propio.
- Pendientes: suite completa/revisión final por `/root`.
- Reservas liberadas: rutas propias congeladas el 2026-11-14.
- Entrega: contratos, política, payloads, tests y limitaciones comunicados a `/root`, UI, motor, evaluación y operación.

## Límites reales

- La declaración `real_furniture` y `source_reference` es accountable pero no prueba que el documento sea real; en modo anónimo `attested_by` reproduce una identidad manual no verificada de la revisión.
- La denylist bloquea los bytes exactos de fixtures conocidos; una variante alterada no queda certificada ni detectada automáticamente.
- El coseno no es probabilidad ni equivalencia técnica; el score técnico sigue siendo determinista y depende de cobertura conocida.
