# Operación privada de Vexplorer

Este despliegue está preparado para un único servidor privado del equipo. No es una instalación remota realizada ni un diseño SaaS multiempresa. Antes de exponerlo hacen falta un hostname real, DNS hacia el servidor, puertos 80/443 accesibles para ACME y una política de copia externa del operador.

### Nota sobre `gex-dashboard.hopto.org`

La inspección de solo lectura del 2026-11-14 encontró Caddy y TLS ya operativos en el host, varios servicios bajo el mismo dominio, `/api/*` reservado por otra aplicación y el puerto loopback `18792` libre. No se debe arrancar el servicio `proxy` de este Compose allí porque competiría por 80/443. La integración propuesta es un contenedor propio publicado solo como `127.0.0.1:18792` y handles Caddy `/vexplorer/*` situados antes del catch-all existente.

Frontend y backend admiten ahora el prefijo común `VEXPLORER_ROOT_PATH=/vexplorer`: los assets son relativos al documento, el cliente antepone el base path y los enlaces de artefactos lo conservan. El snippet `deploy/vps-vexplorer.caddy` usa `handle_path /vexplorer/*` para retirar el prefijo antes del proxy; la API interna sigue siendo `/api/v1` y no captura el `/api` existente del host. Limita cada body a 21 MiB antes de FastAPI, protegiendo `/tmp`; la app limita cada DXF a 20 MiB y el total de documentos mediante `VEXPLORER_MAX_STORAGE_BYTES` (1 GiB por defecto). La revisión final del Caddyfile y la autorización concreta de despliegue siguen siendo gates.

El host tenía 7,9 GiB libres (95% usado), 3,1 GiB de RAM disponible y swap en uso. Hay que liberar o presupuestar espacio antes de transferir imágenes. El usuario SSH `kripta` puede leer el Caddyfile activo, pero no accede al socket Docker y `sudo -n` exige contraseña; el operador deberá ejecutar los pasos privilegiados. La salud se mantuvo HTTP 308→HTTPS y HTTPS 200 con certificado verificado antes y después de la inspección.

Existe una alternativa de menor huella: Python 3.12.3, pip y `venv` están disponibles; el home de `kripta` es escribible, Caddy 2.11.7 y su admin local 2019 están activos, y `kripta` puede editar el Caddyfile. `loginctl enable-linger kripta` quedó aplicado con autorización y `Linger=yes`, de modo que un futuro servicio `systemd --user` puede persistir tras logout/reboot. No se ha creado el venv ni el servicio y Python 3.12 deberá verificarse contra las restricciones, distintas del build Docker comprobado en 3.14.2.

### Instalación venv prevista para el VPS

El bootstrap de dependencias ya existe en `/home/kripta/apps/vexplorer/venv`: se transfirió solo `deploy/requirements-runtime.txt`, coincidió su SHA-256 local/remoto, la instalación Python 3.12.3 terminó y `pip check` no encontró incompatibilidades. Ocupa 251 MiB. Todavía no hay código, secretos, servicio ni listener.

Después de la revisión final, la instalación debe usar esta estructura privada:

```text
/home/kripta/apps/vexplorer/
├── venv/
├── releases/<revision>/       # solo backend/app, frontend runtime y tools/backup.py
├── current -> releases/<revision>
└── shared/
    ├── data/
    ├── backups/
    ├── config/cost-catalog.json
    ├── secrets/users.json
    └── production.env
```

`shared/production.env` (0600) debe declarar, sin registrar valores secretos:

```dotenv
VEXPLORER_ENV=production
VEXPLORER_DATA_DIR=/home/kripta/apps/vexplorer/shared/data
VEXPLORER_USERS_FILE=/home/kripta/apps/vexplorer/shared/secrets/users.json
VEXPLORER_COST_CATALOG=/home/kripta/apps/vexplorer/shared/config/cost-catalog.json
VEXPLORER_ALLOWED_ORIGINS=https://gex-dashboard.hopto.org
VEXPLORER_ROOT_PATH=/vexplorer
VEXPLORER_JOB_MAX_PENDING=8
VEXPLORER_MAX_STORAGE_BYTES=1073741824
OPENAI_MODEL=gpt-6.1-sol
OPENAI_MAX_OUTPUT_TOKENS=4096
OPENAI_VISION_ENABLED=false
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=256
```

La clave de proveedor, si se habilita live, se añade al env privado; no se pasa en argv ni se copia al release. Tras crear `shared/data`, instalar `deploy/systemd-user/vexplorer.service` en `~/.config/systemd/user/`, revisar rutas y permisos, el futuro operador ejecutará `systemctl --user daemon-reload` y `systemctl --user enable --now vexplorer`. La unidad liga solo `127.0.0.1:18792`, usa un worker y permite escritura exclusivamente en `shared/data`.

El snippet `deploy/vps-vexplorer.caddy` se importa dentro del bloque existente `gex-dashboard.hopto.org`, antes de los catch-all. Primero se guarda una copia recuperable del Caddyfile, después se valida con `caddy validate --config /etc/caddy/Caddyfile` y solo entonces se recarga con `caddy reload --config /etc/caddy/Caddyfile`. Las comprobaciones son `curl http://127.0.0.1:18792/api/v1/health` y `curl https://gex-dashboard.hopto.org/vexplorer/api/v1/health`. Ningún paso debe detener ni reiniciar otras aplicaciones.

## Frontera de seguridad

- Caddy es el único servicio publicado (`80/tcp`, `443/tcp` y `443/udp`). La aplicación solo está en la red Docker interna.
- Caddy obtiene y renueva TLS para `VEXPLORER_HOSTNAME`. No use una IP ni el dominio de ejemplo.
- La aplicación corre como UID/GID `10001`, con filesystem raíz de solo lectura, capacidades eliminadas y un único worker Uvicorn. Mantener un solo worker hasta que las restricciones de trabajos y SQLite se rediseñen y prueben para multiproceso.
- En producción, todas las rutas salvo `GET /health` y `GET /api/v1/health` requieren HTTP Basic. La identidad autenticada es el actor de auditoría; el nombre enviado por el navegador no la sustituye.
- Las mutaciones con cabecera `Origin` solo aceptan los orígenes HTTPS declarados en `VEXPLORER_ALLOWED_ORIGINS`. Clientes de consola sin `Origin` siguen necesitando Basic Auth.
- El secreto de usuarios y el catálogo económico se montan como archivos de solo lectura; no se incluyen en la imagen ni en Git.
- `OPENAI_API_KEY` es opcional. Sin ella se opera en `geometry_only`; no se simula un proveedor.

## Preparación del operador

Requisitos: Docker Engine con Compose v2, un checkout de esta revisión, DNS y un correo ACME reales. Cree fuera del repositorio `/srv/vexplorer/{config,secrets,backups}` con acceso restringido. Copie `deploy/production.env.example` a `/srv/vexplorer/production.env` y reemplace todos los ejemplos.

El primer usuario se genera de forma interactiva; la contraseña nunca va en argv ni se imprime:

```console
python -m tools.manage_users --file /srv/vexplorer/secrets/users.json set operador
```

Para automatización controlada puede enviar una sola línea por stdin con `--password-stdin`; proteja también el origen de ese stdin. `list` solo muestra nombres. `delete` no permite eliminar el último usuario. El archivo usa hashes scrypt con sal aleatoria, no contraseñas reversibles.

El catálogo real debe ser un JSON `TableCostCatalog` con `synthetic: false`, `source`, `effective_date`, versión y tarifas con concepto, alcance y unidad válidos. Un ejemplo mínimo de estructura (las tarifas son marcadores y no deben copiarse como precios reales):

```json
{
  "schema_version": "0.6.0",
  "catalog_version": "erp-AAAA-MM",
  "source": "Identificador del extracto aprobado",
  "effective_date": "AAAA-MM-DD",
  "synthetic": false,
  "tariffs": []
}
```

Una lista vacía o un catálogo inválido debe impedir el arranque o el cálculo, nunca activar el catálogo demo silenciosamente. Obtenga el catálogo válido de compras/economía y guárdelo en la ruta `VEXPLORER_COST_CATALOG_HOST`.

Valide configuración, construya y arranque desde el checkout:

```console
docker compose --env-file /srv/vexplorer/production.env config --quiet
docker compose --env-file /srv/vexplorer/production.env build --pull
docker compose --env-file /srv/vexplorer/production.env up -d
docker compose --env-file /srv/vexplorer/production.env ps
curl --fail https://HOST_REAL/api/v1/health
curl --fail --user operador https://HOST_REAL/api/v1/config
```

No añada un `ports:` al servicio `app`. Configure firewall, actualizaciones del host y acceso SSH según las normas de la empresa. Los logs pueden contener IDs operativos: restrinja su lectura y retención.

## Datos, actualización y reinicio

`VEXPLORER_DATA_VOLUME` nombra el volumen persistente. Dentro guarda `/var/lib/vexplorer/data/vexplorer.sqlite3` y `documents/`; SQLite incluye runs, revisiones, trabajos, eventos, estimaciones y artefactos persistidos. `docker compose restart` y recrear contenedores no eliminan el volumen.

Antes de actualizar desde la base auditada o cualquier versión:

1. Cree y verifique una copia según la sección siguiente.
2. Registre la versión de imagen y el volumen actuales.
3. Construya la nueva imagen sin borrar la anterior.
4. Arranque contra una copia restaurada en un volumen nuevo y compruebe health, login, runs históricos, trabajos, exportaciones y artefactos.
5. Solo entonces cambie `VEXPLORER_DATA_VOLUME` al volumen validado. Conserve el volumen anterior para rollback.

Las migraciones de esquema pertenecen al backend. No edite SQLite manualmente ni dé por compatible una actualización porque el contenedor arranque: la aceptación exige lectura de datos previos, reinicio y nuevo backup/restore.

## Copia consistente

`tools.backup` usa la API online de backup de SQLite, ejecuta `PRAGMA integrity_check`, incluye documentos de upload y escribe un ZIP con manifiesto, tamaños y SHA-256. Los documentos gestionados por la aplicación son inmutables; si otro proceso puede modificarlos, detenga la aplicación durante la copia. El ZIP cubre exactamente:

- base SQLite: runs, revisiones, trabajos, eventos, estimaciones y artefactos almacenados;
- `documents/`: uploads conservados por la aplicación.

No cubre identidades, catálogo, claves de proveedor, configuración de Caddy ni certificados. Guarde `users.json`, el catálogo y `/srv/vexplorer/production.env` por separado en un almacén cifrado y con control de acceso. Deben restaurarse antes de iniciar el modo privado.

Prepare `/srv/vexplorer/backups` para UID `10001` y cree una ruta nueva en cada ejecución; el comando rechaza sobrescribir un ZIP existente:

```console
docker compose --env-file /srv/vexplorer/production.env run --rm --no-deps \
  -v /srv/vexplorer/backups:/backup \
  app python -m tools.backup create \
  --data-dir /var/lib/vexplorer/data \
  --output /backup/vexplorer-AAAA-MM-DDTHHMMSSZ.zip
```

Copie el ZIP a otro sistema y aplique retención. Un archivo que no se haya restaurado en un ensayo no cuenta como copia verificada.

## Restauración sin sobrescritura

La restauración rechaza rutas absolutas, `..`, formas de unidad Windows, miembros extra/duplicados, symlinks, tamaños o hashes incorrectos y SQLite corrupta. Solo publica un destino nuevo tras validar todo; nunca restaura encima de datos existentes.

```console
docker volume create vexplorer_data_restore_AAAAMMDD
docker run --rm --user 10001:10001 \
  -v vexplorer_data_restore_AAAAMMDD:/var/lib/vexplorer \
  -v /srv/vexplorer/backups:/backup:ro \
  vexplorer:local python -m tools.backup restore \
  --archive /backup/vexplorer-AAAA-MM-DDTHHMMSSZ.zip \
  --destination /var/lib/vexplorer/data
```

Restaure también usuarios, catálogo y env desde su custodia separada. Cambie `VEXPLORER_DATA_VOLUME=vexplorer_data_restore_AAAAMMDD`, ejecute `up -d`, y valide identidad, historial, trabajos, documentos y exportaciones. Si falla, vuelva al nombre del volumen anterior; no copie archivos parcialmente sobre él.

## Comprobaciones periódicas

- `docker compose ps` debe mostrar `app` saludable y `proxy` activo.
- Ambos health checks son deliberadamente públicos y no deben revelar configuración.
- Verifique login válido/inválido y que una mutación con `Origin` ajeno devuelve 403.
- Revise espacio del volumen, cola (`VEXPLORER_JOB_MAX_PENDING`, por defecto 8), expiración TLS y fecha/procedencia del catálogo.
- Ejecute un ensayo periódico de restauración en un volumen nuevo y compruebe runs, documentos, jobs y artefactos.
- No interprete health como validación industrial de resultados CAD o costes.
