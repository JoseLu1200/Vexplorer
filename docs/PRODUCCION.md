# Operación de Vexplorer en producción

La aplicación es pública, sin login, por decisión expresa del usuario: https://gex-dashboard.hopto.org/vexplorer/.

Release activado el 2026-11-14: `d0ea7a85e787f4358ab4dbb05ea0250395f2083b`, directorio `cad-d0ea7a85e787`. Conserva el trabajo de `main` (`0d9dee7`), incluida su reconstrucción 3D. CI del release: `43592672878`, aprobada. Véase [verificación pública](VERIFICACION_PRODUCCION_PUBLICA_2026-11-14.md).

## Servicio

Caddy existente publica TLS y `/vexplorer/*`. Uvicorn escucha solo en `127.0.0.1:18792`, mediante `systemctl --user vexplorer.service`, con **un único worker**. La cola y las reservas 3D usan sincronización dentro del proceso; varios workers no están soportados.

La raíz es `/home/kripta/apps/vexplorer`: `releases/` guarda código inmutable, `current` apunta al activo y `shared/` conserva datos, copias, restauraciones, catálogo, usuarios y `production.env`. El env tiene permisos 0600 y nunca se copia a Git o al release. [systemd-production.env.example](../deploy/systemd-production.env.example) contiene las variables efectivas; el ejemplo Docker no configura este servicio.

- Producción pública: `VEXPLORER_AUTH_ENABLED=false`, `VEXPLORER_ROOT_PATH=/vexplorer`.
- Origen autorizado: `https://gex-dashboard.hopto.org`; mutaciones con otro `Origin` devuelven 403.
- Proponente `gpt-6.1-sol` y crítico visual separado `gpt-6-astra`.
- Crítico: hasta cinco llamadas, dos correcciones de argumentos y dos reparaciones semánticas. Plazo global CAD: 600 segundos.
- DWG: LibreDWG 0.14 en `/home/kripta/apps/vexplorer/tools/libredwg-0.14/bin/dwg2dxf`.

No arranque el proxy Docker en este host ni reinicie aplicaciones vecinas.

## Acceso y límites

El histórico compartido y las mutaciones privadas de biblioteca/semántica están bloqueados; la interfaz los oculta. Los identificadores opacos permiten recuperar documentos y resultados. Este modo no ofrece aislamiento por usuario o empresa.

La admisión persiste en SQLite. CAD y reconstrucción comparten diez análisis live globales diarios y tres por cliente, por defecto. Los reenvíos idempotentes no generan otra llamada. Los límites por minuto y de subida/trabajos diarios sobreviven al reinicio; los rechazos temporales incluyen `Retry-After`.

DXF/DWG: 20 MiB por original; body máximo de 21 MiB en proxy/admisión temprana. Documentos: límite configurable de 1 GiB por defecto. Reconstrucción: tres trabajos por run, un sucesor por refinamiento, 16 MiB por trabajo y 256 MiB totales.

Un fallo excepcional de filesystem entre confirmar admisión 3D y publicar su directorio puede consumir cuota sin ejecutar el proveedor; no se repite el pago automáticamente.

## Autoridad de los resultados

La revisión es automática, sin aprobación humana obligatoria. El crítico debe decidir sobre cada medida numérica y respaldar cada aceptación con evidencia visual dirigida al campo. Las omisiones provocan una corrección automática de la crítica.

Lista y planos distinguen medidas observadas, deducidas, estimadas y desconocidas. Las estimaciones conservan nominal, rango, premisas y dependencias. Clasificar un herraje comprado del escenario no identifica un modelo comercial ni certifica su capacidad. Los campos sin justificar permanecen pendientes.

Un resultado puede ser útil y quedar incompleto. El éxito del proceso no certifica fabricación, resistencia, CNC, precisión industrial general ni precios empresariales. La reconstrucción 3D conserva su condición de hipótesis geométrica.

## Copias y restauración

`vexplorer-backup.timer` programa una copia diaria a las 03:30 UTC, con hasta veinte minutos de dispersión. Comprueba que no haya trabajos CAD/3D activos, detiene solo Vexplorer, crea/verifica la copia y lo arranca también si falla la copia.

Retiene hasta catorce archivos `scheduled-*` y 2 GiB de copias programadas. Exige 1 GiB libre adicional al tamaño de la fuente. No elimina copias manuales ni de despliegues. Incluye bases de datos, documentos y `reconstruction/`; rechaza WAL/journals no vacíos en modo quiescente, rutas inseguras y symlinks.

Comandos:
- `systemctl --user status vexplorer-backup.timer`
- `systemctl --user start vexplorer-backup.service`
- `journalctl --user -u vexplorer-backup.service -n 40`

Restaure siempre a un destino nuevo mediante `python -m tools.backup restore --archive ARCHIVO.zip --destination DESTINO_NUEVO`, usando el Python del venv. Arranque una instancia loopback con `VEXPLORER_DATA_DIR` y `VEXPLORER_HISTORY_DB` apuntando a esa restauración y compare jobs, revisiones y hashes de artefactos CAD/3D.

Env, usuarios y catálogo se custodian por separado. Las copias programadas residen en el mismo host; su réplica externa es una operación independiente.

## Actualización

[build-release.ps1](../deploy/build-release.ps1) empaqueta un commit exacto con manifest y SHA-256, sin secretos ni datos. Antes de activar: CI, trabajos inactivos, backup/restauración y candidato funcionando contra datos restaurados, con HTTP e inferencia real verificados.

La activación cambia atómicamente `current` y reinicia solo Vexplorer. Conserve release y env anteriores para rollback. No sobrescriba datos restaurados encima de los activos.

Después compruebe acceso público, bloqueos 403, persistencia tras reinicio, restauración funcional y códigos HTTP de aplicaciones vecinas. Health por sí solo no valida CAD.

## Empaquetado reproducible local

`python -m tools.build_release --output .runtime/release-build` genera un snapshot determinista del runtime allowlisted. Incluye backend, frontend servido, fuentes locales, `frontend/core/ui.js`, herramientas operativas y manifiestos de dependencias Python/Node; excluye secretos, env, bases de datos, datasets, referencias privadas, pruebas y `.runtime`. Falla si falta una entrada esencial. `RELEASE.json` identifica el commit base y el SHA-256 del árbol de payload; `MANIFEST.sha256` permite verificar cada entrada. El archivo no contiene una fecha variable y normaliza tiempos, propietarios y modos de tar/gzip.

El comando no transfiere ni activa el resultado. Antes de promover un candidato, ejecútelo dos veces sobre el árbol integrado, compruebe igualdad de `candidate_id`, `payload_tree_sha256` y SHA-256 del archivo, y después siga el flujo de backup, restauración y smoke anterior. El `git_head` de un snapshot con cambios locales solo identifica su base; el hash de payload identifica los bytes empaquetados. Para un cierre completamente trazable, integre primero y vuelva a generar el candidato desde el commit definitivo.
