# Agente de operación — producto privado

## Identidad y autorización

- Identidad: agente de IA de operaciones; no representa a una persona.
- Rol: despliegue privado, copias verificables y CI.
- Archivo creado por la delegación explícita del usuario del 2026-11-14.

## Tarea y alcance

- Implementar Task 5 de `docs/superpowers/plans/2026-11-14-private-production.md`.
- Propiedad exclusiva de esta tarea: `Dockerfile`, `compose.yaml`, `.dockerignore`, `deploy/*`, `.github/workflows/*`, `tools/backup.py`, `tools/manage_users.py`, `tests/test_backup.py`, `docs/PRODUCCION.md`, `.runtime/production/ops-report.md` y este archivo.
- Solo lectura: backend, frontend, contratos, `pyproject.toml`, catálogo económico y pruebas ajenas.
- No se desplegará a ningún servidor ni se inventará VPS, hostname, tarifas o secretos.

## Contrato coordinado con backend

- Producción: `VEXPLORER_ENV=production`, `VEXPLORER_DATA_DIR` persistente (`/var/lib/vexplorer/data` en Compose), `VEXPLORER_USERS_FILE=/run/secrets/vexplorer_users`, `VEXPLORER_COST_CATALOG` configurable y `VEXPLORER_ALLOWED_ORIGINS` obligatorio.
- Usuarios JSON: objeto `username -> $scrypt$ln=14,r=8,p=1$<salt_base64url>$<digest_base64url>`; nombres ASCII `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`.
- HTTP Basic en todo salvo `GET /api/v1/health` y `GET /health`; identidad autenticada en `request.state.actor`.
- Un proceso Uvicorn y un worker de trabajos por proceso; cola acotada mediante `VEXPLORER_JOB_MAX_PENDING`.
- Proxy Caddy expone TLS; el backend no publica puertos al host. Datos persistentes en volumen nombrado.

## Estado

- Implementación y verificación integrada de Task 5 terminadas dentro del alcance propio.

## Dependencias y avisos

- Backend confirmó nombres, formato scrypt, health checks, política de origen y límite de trabajos.
- Economía aportará un catálogo configurable real; operaciones solo montará la ruta y documentará su obligatoriedad/procedencia.
- El hostname TLS real es `gex-dashboard.hopto.org`; publicar la aplicación permanece pendiente de revisión final y autorización concreta.
- Inspección VPS inicial de solo lectura: Caddy/TLS existentes, `/api/*` ocupado, puerto loopback 18792 libre, disco al 95% y usuario SSH sin Docker/sudo no interactivo.
- Backend/frontend incorporaron después `VEXPLORER_ROOT_PATH=/vexplorer`. Linger de `kripta` quedó habilitado con autorización para un futuro servicio de usuario; no se desplegó código ni se recargó Caddy.

## Registro de verificación

- TDD RED: `python -m pytest tests/test_backup.py -q` falló en colección porque `tools.backup` no existía.
- TDD GREEN inicial: mismo comando, `14 passed`; regresión posterior del límite de 1024 bytes RED y suite final propia `15 passed in 0.48s`.
- Docker estaba instalado pero el daemon no activo; tras arranque reversible autorizado, servidor Docker 29.4.2 disponible.
- `docker build --tag vexplorer:production-test .`: correcto con Python 3.14.2 y vendor Three.js generado localmente.
- `docker compose config --quiet`: correcto; red backend interna y red de egress separada sin publicar el puerto de app.
- Imagen verificada como UID/GID 10001, sin tests/evaluation/data/.git; volumen nuevo escribible por el usuario no-root.
- Caddy 2.10.2 validó el Caddyfile y sus políticas HTTPS sin errores.
- Smoke final: auth/origen/root path/job/restart correctos; backup online restaurado en volumen nuevo y datos reabiertos; recursos efímeros eliminados.
- VPS bootstrap autorizado: venv Python 3.12.3, constraints exactas y `pip check` correctos, 251 MiB; aún sin código/secretos/servicio/Caddy.
- Verificación propia final: 15 tests, compileall, Compose, dos configuraciones Caddy, superficie de imagen y diff-check correctos.
- Pendiente externo: copiar release/secretos, instalar la unidad, importar el snippet Caddy y ejecutar aceptación remota solo tras review/autorización. Ninguna aplicación existente fue reiniciada o modificada.
