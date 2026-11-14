# Agente de similitud y operación de biblioteca

## Identidad y autorización

- Identidad: agente de IA delegado por `/root`; no representa a una persona.
- Rol: diagnosticar persistencia/publicación de biblioteca e histórico público y preparar un backfill operativo seguro.
- Archivo creado y designado explícitamente: `team/agente_similitud_operacion.md`, delegación de `/root` del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: explicar con evidencia por qué la biblioteca publicada está vacía pese a tener embeddings configurados, localizar datos reales elegibles y proponer/automatizar una publicación idempotente y auditable.
- Estado: causa y elegibilidad cerradas; tooling y runbook implementados; V2 activado y verificado sin importar datos no elegibles.

## Alcance y reservas

- Propiedad: este registro; nuevos tooling y pruebas de publicación/backfill bajo `tools/` y `tests/`; nueva documentación operativa específica si resulta necesaria.
- Solo lectura: servicio y datos remotos, `backend/app/main.py`, contratos, repositorio/biblioteca/histórico, frontend, datasets locales y documentación existente.
- No editar: `main.py`, modelos, biblioteca de producto, frontend, artefactos de otros agentes, despliegue o datos vivos sin aprobación concreta de `/root`.
- Solapes: `tools/backup.py`, `tests/test_backup.py` y `docs/PRODUCCION.md` siguen perteneciendo a operación/release; no se modificarán.

## Hecho en el último bloque

- Leídas las reglas del repositorio, el estado de operación, histórico real, fuentes públicas y despliegue.
- Confirmado documentalmente que el release excluye datasets y que la carga API de fuentes públicas quedó pendiente.
- Reproducido el estado público: proveedor semántico disponible, Biblioteca con cero elementos.
- Inspeccionadas en modo read-only las tres ejecuciones remotas: todas usan `mesa_demo_001.dxf`; una revisión se declara ensayo sintético y las otras dos carecen de revisión. Ninguna cumple «mueble real revisado».
- Implementado `tools/backfill_library.py` con manifiesto estricto, inventario remoto, verificación de hash/revisión/no sintético, dry-run predeterminado, protección de embeddings y verificación posterior.
- Implementado `tools/rehearse_library_release.py`: exige HEAD base exacto, genera dos paquetes con `tools.build_release` y comprueba igualdad byte a byte sin acción remota.
- Ajustado el rehearsal a snapshots allowlisted revisados con cambios locales: exige HEAD base exacto e igualdad byte a byte, pero no usa un worktree limpio como bloqueo artificial.
- Preflight remoto read-only: servicio activo en `127.0.0.1:18792`, 7,6 GiB libres, permisos 0700/0600 correctos, Python 3.12.3 y las tres SQLite con `integrity_check=ok`.
- Detectado cambio concurrente de producción a `cad-d0ea7a85e787`; su commit/branch/worktree local exacto es `d0ea7a85...`, `feat/cad-completion`, `.worktrees/cad-completion`.
- Comparado su manifiesto con el release público anterior: 35 rutas añadidas y 39 cambiadas. El snapshot del worktree principal no puede reemplazarlo sin perder mejoras CAD.
- Verificado que la base CAD bloquea actualmente Biblioteca/similitud públicas con 403 y deshabilita la capacidad semántica anunciada; la integración debe reconciliar esta frontera además de portar el gate de publicación.
- Paquete V1 bloqueado antes de transferir por ocho rutas CAD/operativas eliminadas; V2 regenerado conserva cero rutas eliminadas frente al current.
- V2 verificado y staged con hash exacto; copia v2 y restauración aislada creadas y validadas.
- Rehearsal sobre `127.0.0.1:18793` pasó health, sesión, config, run, Biblioteca vacía, assets CAD y utilidad de backup; proceso temporal detenido.
- `current` y PID productivo permanecieron intactos; no hubo activación, reinicio, cambio de Caddy ni importación de datos.
- Añadidos pruebas focales y runbook `docs/BIBLIOTECA_OPERACION.md`.
- Tras GO explícito, CAS confirmó el release CAD esperado y cero jobs activos; se activó V2 con cambio atómico y se reinició solo Vexplorer.
- Smoke público posterior correcto en health, raíz, sesión, config, Biblioteca y assets CAD; las tres SQLite conservaron integridad y Biblioteca/histórico siguen vacíos.
- Recibo completo en `docs/RECIBO_DESPLIEGUE_SIMILITUD_2026-11-14.md`; rollback CAD, backup y restauración aislada permanecen disponibles.
- V4 UI final comparado contra V2: solo cambiaron `frontend/app.js`, `frontend/core/ui.js` y metadata; hashes/tamaños del manifiesto verificados.
- Tras CAS de V2, cero jobs y conteos sin cambios, V4 se activó atómicamente; smoke público y hashes UI exactos pasaron, con V2 conservado como rollback inmediato.
- QA final de navegador confirmó Biblioteca visible `0/0/0`, histórico/costes ocultos, estado semántico preciso y cero errores de consola; evidencia en `.runtime/similarity-repair/public-library-final.png`.

## Siguiente bloque

- Entregar a `/root` y permanecer disponible para QA pública final o rollback si apareciera una regresión.

## Dependencias / avisos

- Necesito de: aprobación de `/root` para cualquier importación, backup nuevo, reinicio o despliegue.
- Afecta a: biblioteca/similitud e histórico publicado; no cambia contratos.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Inspección inicial | documentación y `git status --short` | completada; árbol concurrentemente modificado preservado | falta evidencia remota |
| TDD RED | `.venv/Scripts/python.exe -m pytest tests/test_backfill_library.py -q` | error esperado: módulo ausente | antes de implementar |
| Focal GREEN | mismo comando | 13 passed | incluye precondición de backup para `--apply` |
| Backup + backfill | `.venv/Scripts/python.exe -m pytest tests/test_backfill_library.py tests/test_backup.py -q` | 40 passed antes de añadir el caso de backup; focal actualizado 13 passed | pruebas offline |
| Lint | `ruff check tools/backfill_library.py tests/test_backfill_library.py` | correcto | focal |
| Suite integrada concurrente | `.venv/Scripts/python.exe -m pytest -q` | 680 passed, 7 failed | fallos concurrentes en similitud/API de biblioteca; ninguno en tooling propio |
| Dry-run público negativo | `python -m tools.backfill_library ...` contra run revisado de demo | 0 elegibles, rechazo `known_non_real_source`; ninguna escritura | servicio sigue con API anterior |
| Tooling final | `.venv/Scripts/python.exe -m pytest tests/test_rehearse_library_release.py tests/test_backfill_library.py -q` | 17 passed | no se construyó candidato antes del freeze |
| Gate integrado | `.venv/Scripts/python.exe -m pytest backend/tests/test_library_publication.py tests/test_backfill_library.py tests/test_rehearse_library_release.py -q` | 18 passed, 1 aviso externo de TestClient | API persiste atestación server-side y tooling exige verificarla tras aplicar |

## Bloqueos y cierre

- Bloqueos: no existen muebles reales revisados elegibles; por ello el estado público vacío es el resultado correcto.
- Pendientes: QA pública final de coordinación; eventual dry-run con un manifiesto real autorizado cuando exista.
- Reservas liberadas: no.
