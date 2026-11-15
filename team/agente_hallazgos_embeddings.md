# Agente de migración de embeddings — coordinación de trabajo

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA de migración de embeddings.
- Rol: backend semántico, configuración y despliegue de EmbeddingGemma 2.
- Archivo creado o designado explícitamente: `team/agente_hallazgos_embeddings.md`, autorizado por el usuario y coordinación el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: migrar la biblioteca semántica y el histórico textual desde OpenAI `text-embedding-3-small` a EmbeddingGemma 2 local, con identidad completa de espacio, pesos fijados, caché incompatible separada y despliegue sin descargas silenciosas.
- Referencia del plan: decisión de arquitectura semántica y encargo explícito de esta sesión.
- Estado: implementación terminada; pendiente suite integrada final de coordinación.

## Alcance y reservas

- Archivos o carpetas que puedo editar: `backend/app/semantic/embeddings.py`, `backend/app/agente/config.py`, secciones semánticas de `backend/app/main.py`, caché de biblioteca e histórico, metadatos de embedding en `backend/app/contratos/modelos.py`, pruebas relacionadas, `pyproject.toml`, `Dockerfile`, `compose.yaml`, `.env.example`, `deploy/*embedding*`/ejemplos de entorno, herramientas y documentación directamente afectadas.
- Dependencias que solo leeré: laboratorio y explorador semántico mixto, salvo ajuste imprescindible para conservar separación de identidades.
- Archivos compartidos que requieren coordinación: `main.py`, repositorio y contrato con coordinación/seguridad; modo de frontend con interfaz; campos de worker con jobs.
- Solapes detectados y acuerdo para resolverlos: coordinación autoriza cambios estrechos; no modificar campos del worker y avisar antes de tocar el modo del frontend.

## Hecho en el último bloque

- Migrados proveedor, configuración, caché de biblioteca, histórico, contratos, consumidores, herramientas, despliegue y documentación a EG2 textual fijado.
- Conservada lectura de metadatos OpenAI heredados sin admitirlos como comparables del espacio activo.
- Añadida serialización de inferencia CPU y fallo honesto si faltan pesos o dependencia.
- Eliminada la reutilización de umbrales OpenAI: EG2 exige calibración exacta por `space_id` o umbral explícito.
- Smoke real offline: vector 768 finito, norma L2 1,0.

## Siguiente bloque

- Coordinación ejecuta la suite integrada final y consolida entrega.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Runtime biblioteca/histórico usa EG2 texto 768 L2; explorador mantiene EG2 mixto | No inventar evidencia visual ausente y no mezclar espacios | Aclaración de revisión Astra transmitida por coordinación |
| 2026-11-14 | Snapshot fijado, montado en solo lectura y `local_files_only`; falta de pesos deshabilita generación | Operación reproducible y sin descarga silenciosa | Decisión de coordinación |
| 2026-11-14 | Umbrales EG2 ligados a `embeddinggemma2:<space_id>` | No reutilizar calibración OpenAI ni otra revisión/preprocesado | Revisión Astra y corrección RED→GREEN |

## Dependencias / avisos

- Necesito de: interfaz para renombrar `embedding_mode`; coordinación para consolidar cambios compartidos.
- Afecta a: capacidad semántica, biblioteca, histórico, regeneración, despliegue y caché persistente.
- Aviso realizado: hallazgos y plan enviados a coordinación antes de editar.
- Cambio de `contratos/`: autorizado explícitamente por el usuario para esta migración; avisar a frontend/seguridad.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| TDD proveedor/config/caché | pytest focal de embeddings e histórico | fallos esperados por API/`space_id` ausentes; GREEN posterior | modelos reales separados |
| Serialización CPU | `test_embeddinggemma2_provider_serializes_cpu_inference` | RED `maximum=2`; GREEN `maximum=1` | una instancia por proceso |
| Umbrales y endpoints | resolver + biblioteca/similitud | ausencia de calibración devuelve 409; umbral explícito y calibración exacta devuelven 200 | calibración industrial pendiente |
| Focal semántico final | pytest embeddings/history/regeneración/biblioteca/similitud | 107 passed, 1 warning externo, 18,89 s | antes del ajuste ergonómico final, cubierto por 20 tests posteriores |
| Ajuste descriptor de grupos | pytest biblioteca + abstención | 20 passed, 1 warning externo, 15,06 s | inferencia solo si hay una versión única |
| Backend amplio | `.venv\Scripts\python.exe -m pytest -q backend/tests` | 1010 passed, 2 warnings, 158,33 s | anterior al gate final de umbral, cubierto focalmente después |
| Config real | intérprete del laboratorio + snapshot fijado | `available=true`, `reason=null`, `space_id=c8c0554e...` | `.venv` base no lleva extra semántico |
| Smoke real offline | `D:\Vexplorer-semantic-lab\venv\Scripts\python.exe`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, snapshot `D:\Vexplorer-semantic-lab\hf-cache\models--google--embeddinggemma-2\snapshots\f9972ac22e696a105c482202646979e33e4b5a1e` | `google/embeddinggemma-2`; 768d; finito; norma 1,0; cold CPU 17,93 s; `space_id=c8c0554e...` | aviso externo Torch Windows; sin red |
| Compose | variables ficticias + `docker compose config --quiet` | exit 0 | imagen no construida: daemon no disponible |

## Bloqueos y cierre

- Bloqueos: ninguno del alcance propio.
- Pendientes: calibración EG2 con corpus autorizado y build de imagen cuando haya daemon Docker.
- Reservas liberadas: ninguna.
- Entrega a otra persona: coordinación recibió código estable, smoke y dictamen scoped APPROVE de Astra.
