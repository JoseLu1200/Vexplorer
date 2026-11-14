# Operación privada de Vexplorer

Vexplorer está desplegado como producto privado de un solo equipo en `https://gex-dashboard.hopto.org/vexplorer/`. No es un diseño SaaS multiempresa. El release activo es `cd57f4f4ac3dca81b82a2d520057dfe3261b07be`; incluye PR1, integrado previamente en `9a7aeac`, y la CI del release terminó correctamente en el run `43549417513`. En este host se usa un venv y un servicio `systemd --user` por su menor huella y porque `kripta` no accede al socket Docker.

### Nota sobre `gex-dashboard.hopto.org`

La inspección inicial del 2026-11-14 encontró Caddy y TLS operativos, varios servicios bajo el mismo dominio y `/api/*` reservado por otra aplicación. La integración observada liga Uvicorn exclusivamente a `127.0.0.1:18792`; Caddy publica `/vexplorer/*` antes del catch-all existente. No se debe arrancar el servicio `proxy` de Compose en este host porque competiría por 80/443.

Frontend y backend admiten `VEXPLORER_ROOT_PATH=/vexplorer`: los assets son relativos al documento, el cliente antepone el base path y los enlaces de artefactos lo conservan. El snippet `deploy/vps-vexplorer.caddy` usa `handle_path /vexplorer/*` para retirar el prefijo antes del proxy; la API interna sigue siendo `/api/v1` y no captura el `/api` existente del host. Limita cada body a 21 MiB antes de FastAPI, protegiendo `/tmp`; la app limita cada DXF a 20 MiB y el total de documentos mediante `VEXPLORER_MAX_STORAGE_BYTES` (1 GiB por defecto).

El snapshot posterior al release registró 8.179.417.088 bytes libres; el disco sigue cerca del 95% usado y debe vigilarse. `kripta` es propietario del Caddyfile, el admin Caddy local está accesible y `caddy reload` no requiere sudo. No se debe pedir ni registrar una contraseña sudo.

Python 3.12.3, el venv y sus dependencias están instalados en `/home/kripta/apps/vexplorer`. `vexplorer.service` está activo y habilitado en el gestor de usuario; `Linger=yes` permite que persista tras logout y reinicio. Caddy 2.11.7 sirve la ruta pública con TLS. El snapshot observado muestra el listener loopback ocupado por la aplicación, health público `200` y la raíz privada `/vexplorer/` protegida con `401` sin credenciales.

### Instalación venv observada en el VPS

El bootstrap de dependencias existe en `/home/kripta/apps/vexplorer/venv`: se transfirió solo `deploy/requirements-runtime.txt`, coincidió su SHA-256 local/remoto, la instalación Python 3.12.3 terminó y `pip check` no encontró incompatibilidades. El código vive en releases inmutables y `current` apunta al release activo.

La instalación usa esta estructura privada:

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

`shared/production.env` (0600) declara, sin documentar valores secretos:

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

La clave de proveedor está en el env privado; no se pasa en argv ni se copia al release. La unidad instalada liga solo `127.0.0.1:18792`, usa un worker y permite escritura persistente exclusivamente en `shared/data`; `PrivateTmp=yes` proporciona además un `/tmp` efímero y aislado. En el gestor de usuario systemd 255 de este host se omiten deliberadamente `PrivateDevices=yes` y `ProtectKernelModules=yes`: ambas fallan por separado con `status=218/CAPABILITIES`. El resto de directivas de endurecimiento se probó conjuntamente y la unidad arrancó correctamente.

El snippet `deploy/vps-vexplorer.caddy` quedó insertado dentro del bloque existente `gex-dashboard.hopto.org`, inmediatamente después del import estable `casinosantiago.caddy` y antes de los catch-all. El Caddyfile activo tiene SHA-256 `c297ea0be19686a5e0a0539e0a9220383f5170c7f4dfa086ddd14c37dab835d4`; la copia anterior recuperable está en `/home/kripta/apps/vexplorer/rollback/Caddyfile.before-vexplorer-06deea06fb25`. Los ocho endpoints preexistentes conservaron sus códigos tras la recarga. No se debe detener ni reiniciar otras aplicaciones al operar Vexplorer.

### Aceptación observada

La aceptación remota guardada fuera de Git terminó con estado `passed`:

- una ejecución `geometry_only` completó ingesta, geometría, revisión, cuatro láminas SVG/DXF, costes parciales y exportaciones;
- el coste se identifica como `synthetic:true` y `partial`: prueba la integración, no tarifas empresariales ni precisión industrial;
- una ejecución real `live` con `gpt-6.1-sol` terminó correctamente;
- el replay de su grabación terminó en modo `recorded_replay` y conserva procedencia, fingerprint y hash del transcript;
- health público, autenticación, prefijo `/vexplorer`, persistencia y aislamiento de los endpoints existentes quedaron comprobados.
- se reinició únicamente `vexplorer.service`; continuó habilitado, con linger activo y bind `127.0.0.1:18792`;
- 18 respuestas GET conservaron código y SHA-256 de cuerpo tras el reinicio y al abrir una restauración con la aplicación local;
- live y replay devolvieron el mismo resultado salvo los campos esperados `run_id` y `created_at`.

La copia de aceptación observada es `/home/kripta/apps/vexplorer/shared/backups/accepted-20261114T030644Z.zip`, SHA-256 `5baff7999f687a9fa2f8189eebc45836f9dd19404b0758e2075c8bf5e9eea836`. Se descargó, se restauró a un destino nuevo y SQLite devolvió `integrity_check=ok`; contenía tres runs, cuatro jobs, una grabación, cero reservas pendientes, cuatro revisiones, una estimación de coste y ocho artefactos de planos. Esta es evidencia puntual, no una programación automática de copias.

Esta evidencia no sustituye revisión técnica de cada resultado. Las credenciales, claves y transcripciones no deben copiarse a documentación ni logs. El despliegue no configura copias automáticas: las copias y ensayos de restauración siguen siendo tareas explícitas del operador.

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

## Preparación del operador para la alternativa Docker

Esta sección no describe el host activo, sino la alternativa para un servidor dedicado. Requiere Docker Engine con Compose v2, un checkout de la revisión, DNS y un correo ACME reales. Cree fuera del repositorio `/srv/vexplorer/{config,secrets,backups}` con acceso restringido. Copie `deploy/production.env.example` a `/srv/vexplorer/production.env` y reemplace todos los ejemplos.

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

En el host activo, los datos persistentes están en `/home/kripta/apps/vexplorer/shared/data`: contiene `vexplorer.sqlite3`, `documents/` y los artefactos gestionados. Cambiar el enlace `current` o reiniciar `vexplorer.service` no elimina ese directorio. En la alternativa Docker, `VEXPLORER_DATA_VOLUME` nombra el volumen que se monta como `/var/lib/vexplorer/data`.

Antes de actualizar el host venv activo:

1. Cree y verifique una copia según la sección siguiente; restaure esa copia a un destino nuevo.
2. Instale la nueva versión en un directorio inmutable `releases/<revision>` y compruebe que el venv satisface sus dependencias. No sobrescriba el release actual.
3. Ejecute la nueva versión contra los datos restaurados y compruebe compatibilidad de esquema, health, login, runs históricos, trabajos, exportaciones y artefactos.
4. Registre el destino anterior de `current`, cambie el enlace al release validado y reinicie únicamente `vexplorer.service`. No modifique ni recargue Caddy para una actualización ordinaria de la aplicación.
5. Repita las comprobaciones externas. Si fallan y el esquema sigue siendo compatible con el release anterior, restaure `current` y reinicie solo el servicio propio. Si una migración rompió esa compatibilidad, conserve los datos actuales y restaure la copia en otra ruta antes de volver a la versión anterior; no ejecute código antiguo sobre un esquema incompatible. Conserve ambos releases y la copia hasta cerrar la aceptación.

Para la alternativa Docker, cree y verifique una copia, registre imagen y volumen actuales, construya la nueva imagen sin borrar la anterior y pruébela contra un volumen restaurado nuevo. Solo tras validar compatibilidad cambie `VEXPLORER_DATA_VOLUME`; conserve imagen y volumen anteriores para rollback.

Las migraciones de esquema pertenecen al backend. No edite SQLite manualmente ni dé por compatible una actualización porque el proceso o contenedor arranque: la aceptación exige lectura de datos previos, reinicio y nuevo backup/restore.

## Copia consistente

`tools.backup` usa la API online de backup de SQLite, ejecuta `PRAGMA integrity_check`, incluye documentos de upload y escribe un ZIP con manifiesto, tamaños y SHA-256. Los documentos gestionados por la aplicación son inmutables; si otro proceso puede modificarlos, detenga la aplicación durante la copia. El ZIP cubre exactamente:

- base SQLite: runs, revisiones, trabajos, eventos, estimaciones y artefactos almacenados;
- `documents/`: uploads conservados por la aplicación.

No cubre identidades, catálogo, claves de proveedor, configuración de Caddy ni certificados. En el host activo, custodie por separado `/home/kripta/apps/vexplorer/shared/secrets/users.json`, `/home/kripta/apps/vexplorer/shared/config/cost-catalog.json` y `/home/kripta/apps/vexplorer/shared/production.env`. En la alternativa Docker, custodie los archivos equivalentes y `/srv/vexplorer/production.env`. Guárdelos en un almacén cifrado con control de acceso y restáurelos antes de iniciar el modo privado.

En el host venv activo, cree un nombre nuevo en cada ejecución; el comando rechaza sobrescribir un ZIP existente:

```console
cd /home/kripta/apps/vexplorer/current
PYTHONPATH=/home/kripta/apps/vexplorer/current \
  /home/kripta/apps/vexplorer/venv/bin/python -m tools.backup create \
  --data-dir /home/kripta/apps/vexplorer/shared/data \
  --output /home/kripta/apps/vexplorer/shared/backups/vexplorer-AAAA-MM-DDTHHMMSSZ.zip
```

Para la alternativa Docker, prepare `/srv/vexplorer/backups` para UID `10001` y use:

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

En el host activo, restaure siempre a un directorio nuevo y no cambie `shared/data` hasta validar el resultado:

```console
cd /home/kripta/apps/vexplorer/current
PYTHONPATH=/home/kripta/apps/vexplorer/current \
  /home/kripta/apps/vexplorer/venv/bin/python -m tools.backup restore \
  --archive /home/kripta/apps/vexplorer/shared/backups/vexplorer-AAAA-MM-DDTHHMMSSZ.zip \
  --destination /home/kripta/apps/vexplorer/shared/restores/restore-AAAA-MM-DDTHHMMSSZ
```

La alternativa Docker puede restaurar de igual forma a un volumen nuevo montado en una ruta de destino vacía.

Restaure también usuarios, catálogo y env desde su custodia separada. Valide identidad, historial, trabajos, documentos y exportaciones antes de cambiar la ruta activa. En Docker, cambie `VEXPLORER_DATA_VOLUME` solo tras validar el volumen nuevo. Si falla, conserve la ruta o volumen anterior; no copie archivos parcialmente sobre ellos.

## Comprobaciones periódicas

- `systemctl --user is-active vexplorer.service` debe devolver `active`; `ss` debe mostrar `127.0.0.1:18792`, nunca un bind público.
- `GET https://gex-dashboard.hopto.org/vexplorer/api/v1/health` debe devolver 200 y una ruta privada sin Basic debe devolver 401.
- Ambos health checks son deliberadamente públicos y no deben revelar configuración.
- Verifique login válido/inválido y que una mutación con `Origin` ajeno devuelve 403.
- Revise espacio del volumen, cola (`VEXPLORER_JOB_MAX_PENDING`, por defecto 8), expiración TLS y fecha/procedencia del catálogo.
- Ejecute copias manuales con retención externa y un ensayo periódico de restauración en una ruta nueva; compruebe runs, documentos, jobs y artefactos.
- No interprete health como validación industrial de resultados CAD o costes.
