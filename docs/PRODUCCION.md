# Operación de Vexplorer

Vexplorer está desplegado para un solo equipo en `https://gex-dashboard.hopto.org/vexplorer/`; no es un diseño SaaS multiempresa. El release `cd57f4f4ac3dca81b82a2d520057dfe3261b07be` y la aceptación privada asociada son antecedentes históricos. El candidato UX posterior `a61f97a89a86-treec58bbe42140dd03c` también se verificó primero con autenticación. El estado operativo más reciente es `/home/kripta/apps/vexplorer/releases/public-access-20261114-071821`, con `VEXPLORER_AUTH_ENABLED=false` por solicitud explícita del propietario. En este host se usa un venv y un servicio `systemd --user` por su menor huella y porque `kripta` no accede al socket Docker.

### Nota sobre `gex-dashboard.hopto.org`

La inspección inicial del 2026-11-14 encontró Caddy y TLS operativos, varios servicios bajo el mismo dominio y `/api/*` reservado por otra aplicación. La integración observada liga Uvicorn exclusivamente a `127.0.0.1:18792`; Caddy publica `/vexplorer/*` antes del catch-all existente. No se debe arrancar el servicio `proxy` de Compose en este host porque competiría por 80/443.

Frontend y backend admiten `VEXPLORER_ROOT_PATH=/vexplorer`: los assets son relativos al documento, el cliente antepone el base path y los enlaces de artefactos lo conservan. El snippet `deploy/vps-vexplorer.caddy` usa `handle_path /vexplorer/*` para retirar el prefijo antes del proxy; la API interna sigue siendo `/api/v1` y no captura el `/api` existente del host. Limita cada body a 21 MiB antes de FastAPI, protegiendo `/tmp`; la app limita cada DXF a 20 MiB y el total de documentos mediante `VEXPLORER_MAX_STORAGE_BYTES` (1 GiB por defecto).

El snapshot posterior al release registró 8.179.417.088 bytes libres; el disco sigue cerca del 95% usado y debe vigilarse. `kripta` es propietario del Caddyfile, el admin Caddy local está accesible y `caddy reload` no requiere sudo. No se debe pedir ni registrar una contraseña sudo.

Python 3.12.3, el venv y sus dependencias están instalados en `/home/kripta/apps/vexplorer`. `vexplorer.service` está activo y habilitado en el gestor de usuario; `Linger=yes` permite que persista tras logout y reinicio. Caddy 2.11.7 sirve la ruta pública con TLS. En la comprobación más reciente, health y la raíz anónima devolvieron `200`. El `401` sin credenciales registrado en las aceptaciones anteriores describe aquellos releases autenticados, no el estado actual.

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
VEXPLORER_AUTH_ENABLED=false
# Con VEXPLORER_AUTH_ENABLED=true:
# VEXPLORER_USERS_FILE=/home/kripta/apps/vexplorer/shared/secrets/users.json
VEXPLORER_COST_CATALOG=/home/kripta/apps/vexplorer/shared/config/cost-catalog.json
VEXPLORER_ALLOWED_ORIGINS=https://gex-dashboard.hopto.org
VEXPLORER_ROOT_PATH=/vexplorer
VEXPLORER_JOB_MAX_PENDING=8
VEXPLORER_MAX_STORAGE_BYTES=1073741824
VEXPLORER_RECORDING_MAX_COUNT=1000
VEXPLORER_RECORDING_MAX_BYTES=268435456
OPENAI_MODEL=gpt-6.1-sol
OPENAI_MAX_OUTPUT_TOKENS=16384
OPENAI_VISION_ENABLED=false
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=256
VEXPLORER_GENERAL_REVIEW_MODEL=gpt-6-astra
VEXPLORER_GENERAL_REVIEW_MAX_OUTPUT_TOKENS=16384
VEXPLORER_GENERAL_REVIEW_MAX_CALLS=5
VEXPLORER_GENERAL_REVIEW_MAX_REPAIRS=2
VEXPLORER_GENERAL_JOB_TIMEOUT_SECONDS=300
```

La clave de proveedor está en el env privado; no se pasa en argv ni se copia al release. La unidad instalada liga solo `127.0.0.1:18792`, usa un worker y permite escritura persistente exclusivamente en `shared/data`; `PrivateTmp=yes` proporciona además un `/tmp` efímero y aislado. En el gestor de usuario systemd 255 de este host se omiten deliberadamente `PrivateDevices=yes` y `ProtectKernelModules=yes`: ambas fallan por separado con `status=218/CAPABILITIES`. El resto de directivas de endurecimiento se probó conjuntamente y la unidad arrancó correctamente.

El snippet `deploy/vps-vexplorer.caddy` quedó insertado dentro del bloque existente `gex-dashboard.hopto.org`, inmediatamente después del import estable `casinosantiago.caddy` y antes de los catch-all. El Caddyfile activo tiene SHA-256 `c297ea0be19686a5e0a0539e0a9220383f5170c7f4dfa086ddd14c37dab835d4`; la copia anterior recuperable está en `/home/kripta/apps/vexplorer/rollback/Caddyfile.before-vexplorer-06deea06fb25`. Los ocho endpoints preexistentes conservaron sus códigos tras la recarga. No se debe detener ni reiniciar otras aplicaciones al operar Vexplorer.

### Aceptación privada histórica observada

La aceptación remota guardada fuera de Git terminó con estado `passed`:

- una ejecución `geometry_only` completó ingesta, geometría, revisión, cuatro láminas SVG/DXF, costes parciales y exportaciones;
- el coste se identifica como `synthetic:true` y `partial`: prueba la integración, no tarifas empresariales ni precisión industrial;
- una ejecución real `live` con `gpt-6.1-sol` terminó correctamente;
- el replay de su grabación terminó en modo `recorded_replay` y conserva procedencia, fingerprint y hash del transcript;
- health público, autenticación, prefijo `/vexplorer`, persistencia y aislamiento de los endpoints existentes quedaron comprobados para aquel release autenticado;
- se reinició únicamente `vexplorer.service`; continuó habilitado, con linger activo y bind `127.0.0.1:18792`;
- 18 respuestas GET conservaron código y SHA-256 de cuerpo tras el reinicio y al abrir una restauración con la aplicación local;
- live y replay devolvieron el mismo resultado salvo los campos esperados `run_id` y `created_at`.

La copia de aceptación observada es `/home/kripta/apps/vexplorer/shared/backups/accepted-20261114T030644Z.zip`, SHA-256 `5baff7999f687a9fa2f8189eebc45836f9dd19404b0758e2075c8bf5e9eea836`. Se descargó, se restauró a un destino nuevo y SQLite devolvió `integrity_check=ok`; contenía tres runs, cuatro jobs, una grabación, cero reservas pendientes, cuatro revisiones, una estimación de coste y ocho artefactos de planos. Esta es evidencia puntual, no una programación automática de copias.

Esta evidencia no sustituye revisión técnica de cada resultado. Las credenciales, claves y transcripciones no deben copiarse a documentación ni logs. El despliegue no configura copias automáticas: las copias y ensayos de restauración siguen siendo tareas explícitas del operador.

## Frontera de seguridad

- Caddy existente es el único servicio público; Uvicorn liga solo `127.0.0.1:18792`.
- La unidad de usuario aplica `NoNewPrivileges`, filesystem protegido, tmp privado y escritura solo en `shared/data`.
- Se usa un único worker Uvicorn hasta que trabajos y SQLite se rediseñen y prueben para multiproceso.
- Con `VEXPLORER_AUTH_ENABLED=true` (valor por defecto), todas las rutas salvo `GET /health` y `GET /api/v1/health` requieren HTTP Basic. La identidad autenticada es el actor de auditoría; el nombre enviado por el navegador no la sustituye.
- Con `VEXPLORER_AUTH_ENABLED=false`, no se carga el archivo de usuarios y el nombre revisor es manual. Este modo no aporta identidad autenticada ni aislamiento entre usuarios.
- En ambos modos, las mutaciones que incluyen cabecera `Origin` solo aceptan los orígenes HTTPS declarados en `VEXPLORER_ALLOWED_ORIGINS`. Los clientes sin `Origin` no quedan cubiertos por esa comprobación; en modo público deben considerarse no autenticados.
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

En el host activo, los datos persistentes están en `/home/kripta/apps/vexplorer/shared/data`: contiene `vexplorer.sqlite3`, `general_furniture.sqlite3`, `history.sqlite3`, `documents/` y los artefactos gestionados. Las bases opcionales aparecen cuando se usan sus módulos. Cambiar el enlace `current` o reiniciar `vexplorer.service` no elimina ese directorio. En la alternativa Docker, `VEXPLORER_DATA_VOLUME` nombra el volumen que se monta como `/var/lib/vexplorer/data`.

Antes de actualizar el host venv activo:

1. Cree y verifique una copia según la sección siguiente; restaure esa copia a un destino nuevo.
2. Instale la nueva versión en un directorio inmutable `releases/<revision>` y compruebe que el venv satisface sus dependencias. No sobrescriba el release actual.
3. Ejecute la nueva versión contra los datos restaurados y compruebe compatibilidad de esquema, health, el modo de acceso configurado, runs históricos, trabajos, exportaciones y artefactos.
4. Registre el destino anterior de `current`, cambie el enlace al release validado y reinicie únicamente `vexplorer.service`. No modifique ni recargue Caddy para una actualización ordinaria de la aplicación.
5. Repita las comprobaciones externas. Si fallan y el esquema sigue siendo compatible con el release anterior, restaure `current` y reinicie solo el servicio propio. Si una migración rompió esa compatibilidad, conserve los datos actuales y restaure la copia en otra ruta antes de volver a la versión anterior; no ejecute código antiguo sobre un esquema incompatible. Conserve ambos releases y la copia hasta cerrar la aceptación.

Para la alternativa Docker, cree y verifique una copia, registre imagen y volumen actuales, construya la nueva imagen sin borrar la anterior y pruébela contra un volumen restaurado nuevo. Solo tras validar compatibilidad cambie `VEXPLORER_DATA_VOLUME`; conserve imagen y volumen anteriores para rollback.

Las migraciones de esquema pertenecen al backend. No edite SQLite manualmente ni dé por compatible una actualización porque el proceso o contenedor arranque: la aceptación exige lectura de datos previos, reinicio y nuevo backup/restore.

## Copia consistente

`tools.backup` usa la API online de backup para cada SQLite, ejecuta `PRAGMA integrity_check`, incluye documentos de upload y escribe un ZIP v2 con manifiesto, tamaños y SHA-256. La restauración conserva compatibilidad con los ZIP v1 del release anterior. Los documentos gestionados por la aplicación son inmutables; si otro proceso puede modificarlos, detenga la aplicación durante la copia. El ZIP cubre exactamente:

- `vexplorer.sqlite3`: runs, revisiones, trabajos, eventos, estimaciones y artefactos existentes;
- `general_furniture.sqlite3`, si existe: propuestas, revisiones y derivados del recorrido general;
- `history.sqlite3`, si existe: registros históricos, comparables e información económica importada;
- `documents/` recursivo: originales DXF/DWG/PDF, normalizados, previews y metadatos/manifiestos de conversión conservados por la aplicación.

Si `VEXPLORER_HISTORY_DB` apunta fuera de `VEXPLORER_DATA_DIR`, la copia debe declararlo de forma explícita con `--database history=/ruta/real/history.sqlite3`. Los alias solo admiten nombres seguros y dos alias no pueden apuntar al mismo archivo. No copie una SQLite activa ni sus ficheros WAL con `cp`: esa operación no sustituye la API online ni la verificación de integridad.

No cubre identidades, catálogo, claves de proveedor, configuración de Caddy ni certificados. En el host activo, custodie por separado `/home/kripta/apps/vexplorer/shared/secrets/users.json`, `/home/kripta/apps/vexplorer/shared/config/cost-catalog.json` y `/home/kripta/apps/vexplorer/shared/production.env`. En la alternativa Docker, custodie los archivos equivalentes y `/srv/vexplorer/production.env`. Guárdelos en un almacén cifrado con control de acceso y restáurelos antes de iniciar el modo privado.

En el host venv activo, cree un nombre nuevo en cada ejecución; el comando rechaza sobrescribir un ZIP existente:

```console
cd /home/kripta/apps/vexplorer/current
PYTHONPATH=/home/kripta/apps/vexplorer/current \
  /home/kripta/apps/vexplorer/venv/bin/python -m tools.backup create \
  --data-dir /home/kripta/apps/vexplorer/shared/data \
  --output /home/kripta/apps/vexplorer/shared/backups/vexplorer-AAAA-MM-DDTHHMMSSZ.zip
```

Con un histórico externo, añada al mismo comando:

```console
  --database history=/ruta/real/history.sqlite3
```

La restauración segura coloca ese alias como `DESTINO/history.sqlite3`; valide la copia allí y apunte `VEXPLORER_HISTORY_DB` a la ruta restaurada solo durante el ensayo. No sobrescriba el histórico externo activo.

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

Restaure también usuarios, catálogo y env desde su custodia separada. Consulte con SQLite datos reales en `vexplorer.sqlite3`, `general_furniture.sqlite3` y `history.sqlite3` cuando estén presentes; valide además identidad, historial, trabajos, originales, previews, conversiones y exportaciones antes de cambiar la ruta activa. En Docker, cambie `VEXPLORER_DATA_VOLUME` solo tras validar el volumen nuevo. Si falla, conserve la ruta o volumen anterior; no copie archivos parcialmente sobre ellos.

## Preparación DWG

El runtime selecciona `VEXPLORER_DWG_CONVERTER=libredwg|oda|auto`. Para GNU LibreDWG configure también la ruta absoluta `VEXPLORER_DWG2DXF_EXECUTABLE`; para ODA use `VEXPLORER_ODA_EXECUTABLE`. Una variable configurada no acredita soporte DWG. Antes de habilitar un proveedor, operaciones debe comprobar que el binario es ejecutable por la unidad endurecida y ejecutar un smoke con un DWG genuino autorizado. El smoke debe conservar original, DXF normalizado, hashes y manifiesto, y el DXF debe superar el lector real. Un ejecutable falso o un fixture que simule la frontera solo prueba manejo de errores.

La descarga comunitaria de ODA File Converter está limitada por ODA a usos no comerciales para no miembros. No se incluye en el release ni se instala automáticamente. Sin licencia aprobada y smoke genuino, el estado operativo correcto es `conversion_unavailable` y solicitar DXF; no sustituya ODA por otro binario bajo el mismo nombre sin adaptar y validar su contrato de proceso.

GNU LibreDWG 0.14 es GPLv3 y su `dwg2dxf` es un proceso externo. El candidato debe fijar versión y SHA-256, conservar su licencia y avisos, y validar cada salida con el lector DXF del producto. La comprobación operativa compara unidades, clases de entidades y límites contra un DXF emparejado, pero no demuestra fidelidad universal de DWG: amplíe el corpus y mantenga `conversion_unavailable` si el binario no está instalado.

En el host privado se preparó, sin activar el servicio, LibreDWG 0.14 bajo `/home/kripta/apps/vexplorer/tools/libredwg-0.14`; el ejecutable configurable es `/home/kripta/apps/vexplorer/tools/libredwg-0.14/bin/dwg2dxf`. La activación del siguiente release debe añadir `VEXPLORER_DWG_CONVERTER=libredwg` y `VEXPLORER_DWG2DXF_EXECUTABLE` al env solo después del backup/restore y smoke del release candidato. El binario preparado no altera el release actual ni demuestra por sí solo que su API esté montada.

## Comprobaciones periódicas

- `systemctl --user is-active vexplorer.service` debe devolver `active`; `ss` debe mostrar `127.0.0.1:18792`, nunca un bind público.
- `GET https://gex-dashboard.hopto.org/vexplorer/api/v1/health` debe devolver 200. Con auth habilitada, la raíz sin Basic debe devolver 401; con el modo público activo debe devolver 200 sin `WWW-Authenticate`.
- Ambos health checks son deliberadamente públicos y no deben revelar configuración.
- Verifique el modo de acceso esperado y que una mutación con `Origin` ajeno devuelve 403.
- Revise espacio del volumen, cola (`VEXPLORER_JOB_MAX_PENDING`, por defecto 8), expiración TLS y fecha/procedencia del catálogo.
- Ejecute copias manuales con retención externa y un ensayo periódico de restauración en una ruta nueva; compruebe runs, documentos, jobs y artefactos.
- No interprete health como validación industrial de resultados CAD o costes.


## Acceso público opcional (2026-11-14)

Por petición del propietario, el VPS actual usa `VEXPLORER_AUTH_ENABLED=false`. Esto permite acceder a la interfaz y API sin usuario ni contraseña. `VEXPLORER_ENV=production` conserva las comprobaciones de origen HTTPS, límites y ejecución por jobs. La autenticación sigue activada por defecto en nuevos despliegues; un valor distinto de `true` o `false` impide arrancar. En modo público no se carga el archivo de usuarios y la revisión usa identidad manual. Localhost sigue sin autenticación y escucha solamente en loopback. La verificación read-only de cierre observó HTTP 200 en raíz y health; no realizó un nuevo despliegue.

## Empaquetado reproducible local

`python -m tools.build_release --output .runtime/release-build` genera un snapshot determinista del runtime allowlisted. Incluye backend, frontend servido, fuentes locales, `frontend/core/ui.js`, herramientas operativas y manifiestos de dependencias Python/Node; excluye secretos, env, bases de datos, datasets, referencias privadas, pruebas y `.runtime`. Falla si falta una entrada esencial. `RELEASE.json` identifica el commit base y el SHA-256 del árbol de payload; `MANIFEST.sha256` permite verificar cada entrada. El archivo no contiene una fecha variable y normaliza tiempos, propietarios y modos de tar/gzip.

El comando no transfiere ni activa el resultado. Antes de promover un candidato, ejecútelo dos veces sobre el árbol integrado, compruebe igualdad de `candidate_id`, `payload_tree_sha256` y SHA-256 del archivo, y después siga el flujo de backup, restauración y smoke anterior. El `git_head` de un snapshot con cambios locales solo identifica su base; el hash de payload identifica los bytes empaquetados. Para un cierre completamente trazable, integre primero y vuelva a generar el candidato desde el commit definitivo.
