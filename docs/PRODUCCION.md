# Operación privada de Vexplorer

Este despliegue está preparado para un único servidor privado del equipo. No es un diseño SaaS multiempresa. El destino autorizado es `https://gex-dashboard.hopto.org/vexplorer/`; DNS, TLS y Caddy ya existen. En este host se elige un venv y servicio `systemd --user` por su menor huella y porque `kripta` no accede al socket Docker. La ejecución del release, servicio y ruta Caddy espera únicamente que terminen la integración PR1 y la revisión final en curso; no falta autorización del usuario.

### Nota sobre `gex-dashboard.hopto.org`

La inspección de solo lectura del 2026-11-14 encontró Caddy y TLS operativos, varios servicios bajo el mismo dominio, `/api/*` reservado por otra aplicación y el puerto loopback `18792` libre. No se debe arrancar el servicio `proxy` de Compose allí porque competiría por 80/443. La integración elegida liga Uvicorn exclusivamente a `127.0.0.1:18792` y añade handles Caddy `/vexplorer/*` antes del catch-all existente.

Frontend y backend admiten `VEXPLORER_ROOT_PATH=/vexplorer`: los assets son relativos al documento, el cliente antepone el base path y los enlaces de artefactos lo conservan. El snippet `deploy/vps-vexplorer.caddy` usa `handle_path /vexplorer/*` para retirar el prefijo antes del proxy; la API interna sigue siendo `/api/v1` y no captura el `/api` existente del host. Limita cada body a 21 MiB antes de FastAPI, protegiendo `/tmp`; la app limita cada DXF a 20 MiB y el total de documentos mediante `VEXPLORER_MAX_STORAGE_BYTES` (1 GiB por defecto).

El baseline fresco tiene 8,19 GB libres (95% usado), 3,41 GB de RAM disponible y swap en uso. La vía venv evita transferir una imagen pesada; aun así se debe vigilar espacio. `kripta` es propietario del Caddyfile, el admin Caddy local está accesible y `caddy reload` no requiere sudo. No se debe pedir ni registrar una contraseña sudo.

Python 3.12.3, pip y `venv` están disponibles; el home de `kripta` es escribible, Caddy 2.11.7 y su admin local 2019 están activos. `Linger=yes`, de modo que el futuro servicio `systemd --user` persistirá tras logout/reboot. El venv ya existe y fue verificado; el servicio, release, secretos y ruta Caddy todavía no se han instalado.

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
VEXPLORER_RECORDING_MAX_COUNT=1000
VEXPLORER_RECORDING_MAX_BYTES=268435456
OPENAI_MODEL=gpt-6.1-sol
OPENAI_MAX_OUTPUT_TOKENS=4096
OPENAI_VISION_ENABLED=false
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=256
```

La clave de proveedor, si se habilita live, se añade al env privado; no se pasa en argv ni se copia al release. Tras crear `shared/data`, instalar `deploy/systemd-user/vexplorer.service` en `~/.config/systemd/user/`, revisar rutas y permisos, el futuro operador ejecutará `systemctl --user daemon-reload` y `systemctl --user enable --now vexplorer`. La unidad liga solo `127.0.0.1:18792`, usa un worker y permite escritura exclusivamente en `shared/data`.

El snippet `deploy/vps-vexplorer.caddy` se inserta dentro del bloque existente `gex-dashboard.hopto.org`, inmediatamente después del import estable `casinosantiago.caddy` y antes de los catch-all. Primero se guarda una copia recuperable del Caddyfile. `caddy validate` como `kripta` no puede abrir un log preexistente de otra aplicación; el cierre ejecuta `caddy adapt` sobre el candidato exacto y `caddy validate` sobre una copia equivalente que cambia únicamente ese writer por `/tmp`. Después vuelve a comprobar el hash original y recarga el candidato exacto mediante el admin Caddy. Las comprobaciones son `curl http://127.0.0.1:18792/api/v1/health` y `curl https://gex-dashboard.hopto.org/vexplorer/api/v1/health`. Ningún paso debe detener ni reiniciar otras aplicaciones.

### Ejecutor de cierre

`.runtime/production/deploy_vps.py` está ignorado por Git y es inerte sin `--apply`. El dry-run captura hash Caddy, puerto, unidad, release, disco y los códigos de las rutas existentes; no usa PM2 ni escribe en el host:

```console
C:\Users\Álvaro Schwiedop\Desktop\KriptaStudios\1hack\Vexplorer\.venv\Scripts\python.exe .runtime/production/deploy_vps.py
```

Coordinación preparará fuera de Git:

- `.runtime/production/vps-access.json`, con `username` exactamente `operador-inicial`, `password` y `api_key` opcional;
- un catálogo JSON configurado. Mientras no haya tarifas empresariales se admite el catálogo demo existente solo con `synthetic:true`, rotulado como demo y usando `--allow-demo-catalog`; no se inventan tarifas reales;
- `.runtime/production/credentials.txt` para entrega privada al usuario, nunca como entrada del proceso ni salida de logs.

La interfaz preparada para el GO final es:

```console
C:\Users\Álvaro Schwiedop\Desktop\KriptaStudios\1hack\Vexplorer\.venv\Scripts\python.exe .runtime/production/deploy_vps.py \
  --revision SHA_COMPLETO_REVISADO \
  --cost-catalog RUTA_CATALOGO_JSON \
  --access-file .runtime/production/vps-access.json \
  --allow-demo-catalog \
  --confirm SHA_COMPLETO_REVISADO \
  --apply
```

El script exige que la revisión sea `HEAD` y que los archivos runtime/build/despliegue estén limpios. Ejecuta `npm ci` y prepara el vendor local fijado, comprueba que el venv remoto corresponde al mismo `requirements-runtime.txt`, y empaqueta solo `backend/app`, frontend runtime/vendor y las herramientas operativas, con manifiesto y SHA-256. Transfiere los secretos por stdin (no argv), fija permisos 0600, liga 18792, prueba health interno, prepara un candidato Caddy desde el hash esperado, ejecuta `caddy adapt` y `caddy validate`, vuelve a comprobar el hash justo antes de escribir y hace `caddy reload`. Si falla, restaura el Caddyfile byte a byte y el release/unidad anterior. Tras el reload compara todos los códigos baseline ajenos a Vexplorer; cualquier cambio provoca rollback.

## Frontera de seguridad

- Caddy existente es el único servicio público; Uvicorn liga solo `127.0.0.1:18792`.
- La unidad de usuario aplica `NoNewPrivileges`, filesystem protegido, tmp privado y escritura solo en `shared/data`.
- Se usa un único worker Uvicorn hasta que trabajos y SQLite se rediseñen y prueben para multiproceso.
- En producción, todas las rutas salvo `GET /health` y `GET /api/v1/health` requieren HTTP Basic. La identidad autenticada es el actor de auditoría; el nombre enviado por el navegador no la sustituye.
- Las mutaciones con cabecera `Origin` solo aceptan los orígenes HTTPS declarados en `VEXPLORER_ALLOWED_ORIGINS`. Clientes de consola sin `Origin` siguen necesitando Basic Auth.
- El secreto de usuarios y el catálogo económico se montan como archivos de solo lectura; no se incluyen en la imagen ni en Git.
- `OPENAI_API_KEY` es opcional. Sin ella se opera en `geometry_only`; no se simula un proveedor.

## Docker como alternativa

Los artefactos Docker siguientes están verificados para un host dedicado, pero no son la vía elegida en `gex-dashboard.hopto.org`. Allí competirían con Caddy existente y exigirían privilegios Docker que `kripta` no tiene.

## Preparación del operador

Requisitos: Docker Engine con Compose v2, un checkout de esta revisión, DNS y un correo ACME reales. Cree fuera del repositorio `/srv/vexplorer/{config,secrets,backups}` con acceso restringido. Copie `deploy/production.env.example` a `/srv/vexplorer/production.env` y reemplace todos los ejemplos.

El primer usuario se genera de forma interactiva; la contraseña nunca va en argv ni se imprime:

```console
python -m tools.manage_users --file /srv/vexplorer/secrets/users.json set operador
```

Para automatización controlada puede enviar una sola línea por stdin con `--password-stdin`; proteja también el origen de ese stdin. `list` solo muestra nombres. `delete` no permite eliminar el último usuario. El archivo usa hashes scrypt con sal aleatoria, no contraseñas reversibles.

El catálogo configurado debe ser un JSON `TableCostCatalog` con versión y tarifas con concepto, alcance y unidad válidos. Un catálogo empresarial usa `synthetic:false`, `source` y `effective_date`. Hasta recibirlo, puede montarse el catálogo demo existente con `synthetic:true`; la UI y exportaciones deben seguir rotulándolo como demo. Un ejemplo mínimo de estructura real (los marcadores no deben copiarse como tarifas):

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

Una lista vacía o un catálogo inválido debe impedir el arranque o el cálculo, nunca activar el demo silenciosamente. Cuando compras/economía entregue tarifas reales, sustituya de forma explícita el archivo en `VEXPLORER_COST_CATALOG_HOST` y conserve su procedencia/fecha.

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

Las grabaciones live tienen una política separada de los límites por ejecución: por defecto, 1000 grabaciones y 256 MiB de transcripts, configurables con `VEXPLORER_RECORDING_MAX_COUNT` y `VEXPLORER_RECORDING_MAX_BYTES`. Antes de llamar al proveedor se reserva atómicamente un puesto y hasta 4 MiB; la persistencia convierte esa reserva en el tamaño real del transcript. Una reserva agotada impide la llamada pagada. El límite de 15 llamadas del agente sigue aplicándose a cada ejecución, no al historial del equipo.

No se borran grabaciones automáticamente: pueden estar referenciadas por replays y auditorías. Al alcanzar capacidad, las ejecuciones geométricas y replays existentes continúan disponibles; el operador debe respaldar los datos y revisar el presupuesto antes de aumentar estos límites. La cuota de transcripts no incluye el resto de SQLite, los documentos ni las copias: revisar también el espacio real del disco. El perfil soportado mantiene un único proceso de aplicación; el arranque recupera las reservas interrumpidas junto con los trabajos sin reintentar llamadas pagadas.

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
