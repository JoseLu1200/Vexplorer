# Agente de operación — producto privado

## Identidad y autorización

- Identidad: agente de IA de operaciones; no representa a una persona.
- Rol: despliegue privado, copias verificables y CI.
- Archivo creado por la delegación explícita del usuario del 2026-11-14.

## Tarea y alcance

- Implementar Task 5 de `docs/superpowers/plans/2026-11-14-private-production.md`.
- Propiedad exclusiva de esta tarea: `Dockerfile`, `compose.yaml`, `.dockerignore`, `deploy/*`, `.github/workflows/*`, `tools/backup.py`, `tools/manage_users.py`, `tests/test_backup.py`, `docs/PRODUCCION.md`, `.runtime/production/ops-report.md` y este archivo.
- Solo lectura: backend, frontend, contratos, `pyproject.toml`, catálogo económico y pruebas ajenas.
- El despliegue remoto se realizó solo tras autorización explícita, preservando las aplicaciones existentes; no se inventan tarifas ni se documentan secretos.

## Contrato coordinado con backend

- Producción: `VEXPLORER_ENV=production`, `VEXPLORER_DATA_DIR` persistente (`/var/lib/vexplorer/data` en Compose), `VEXPLORER_USERS_FILE=/run/secrets/vexplorer_users`, `VEXPLORER_COST_CATALOG` configurable y `VEXPLORER_ALLOWED_ORIGINS` obligatorio.
- Usuarios JSON: objeto `username -> $scrypt$ln=14,r=8,p=1$<salt_base64url>$<digest_base64url>`; nombres ASCII `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`.
- HTTP Basic en todo salvo `GET /api/v1/health` y `GET /health`; identidad autenticada en `request.state.actor`.
- Un proceso Uvicorn y un worker de trabajos por proceso; cola acotada mediante `VEXPLORER_JOB_MAX_PENDING`.
- Proxy Caddy expone TLS; el backend no publica puertos al host. Datos persistentes en volumen nombrado.

## Estado

- Implementación, despliegue privado y verificación integrada de Task 5 terminadas. Release activo: `cd57f4f4ac3dca81b82a2d520057dfe3261b07be`.

## Dependencias y avisos

- Backend confirmó nombres, formato scrypt, health checks, política de origen y límite de trabajos.
- Economía debe aportar un catálogo empresarial real. El catálogo activo de aceptación está marcado `synthetic:true`; operaciones no lo presenta como tarifas reales.
- Caddy publica `https://gex-dashboard.hopto.org/vexplorer/` sin capturar el `/api/*` existente; ocho endpoints anteriores conservaron sus códigos.
- El servicio de usuario está activo y habilitado, liga solo `127.0.0.1:18792` y `Linger=yes`. El disco permanece cerca del 95% y requiere seguimiento.

## Registro de verificación

- TDD RED: `python -m pytest tests/test_backup.py -q` falló en colección porque `tools.backup` no existía.
- TDD GREEN inicial: mismo comando, `14 passed`; regresión posterior del límite de 1024 bytes RED y suite final propia `15 passed in 0.48s`.
- Docker estaba instalado pero el daemon no activo; tras arranque reversible autorizado, servidor Docker 29.4.2 disponible.
- `docker build --tag vexplorer:production-test .`: correcto con Python 3.14.2 y vendor Three.js generado localmente.
- `docker compose config --quiet`: correcto; red backend interna y red de egress separada sin publicar el puerto de app.
- Imagen verificada como UID/GID 10001, sin tests/evaluation/data/.git; volumen nuevo escribible por el usuario no-root.
- Caddy 2.10.2 validó el Caddyfile y sus políticas HTTPS sin errores.
- Smoke final: auth/origen/root path/job/restart correctos; backup online restaurado en volumen nuevo y datos reabiertos; recursos efímeros eliminados.
- VPS desplegado con venv Python 3.12.3, constraints exactas, unidad systemd de usuario y Caddy integrado con backup recuperable.
- Aceptación remota: geometría, revisión, cuatro láminas SVG/DXF, costes parciales demo, exportaciones, ejecución live y replay grabado correctos.
- Reinicio del servicio propio y restauración a destino nuevo conservaron 18 respuestas GET; SQLite pasó `integrity_check`. CI `43549417513` correcta.
- Verificación propia final: 15 tests, compileall, Compose, dos configuraciones Caddy, superficie de imagen y diff-check correctos.
- Pendiente operativo: copias manuales con retención externa, ensayos periódicos de restauración y sustitución explícita del catálogo demo cuando existan tarifas empresariales aprobadas.
