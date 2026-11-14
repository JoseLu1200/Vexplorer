# Recibo de predespliegue de similitud y Biblioteca

Fecha de rehearsal y activación: 2026-11-14. El candidato se activó después de superar el CAS, la restauración aislada y el smoke previo.

## Artefacto congelado

- Candidato: `d0ea7a85e787-tree1c7572fa8efee982`.
- Base Git declarada: `d0ea7a85e787f4358ab4dbb05ea0250395f2083b` (`feat/cad-completion`).
- Archivo local/remoto: `d0ea7a85e787-tree1c7572fa8efee982.tar.gz`.
- SHA-256 del archivo: `15cd6c2474df368ff4716f881b38062995c593c55f633097effd756b7651005e`.
- SHA-256 del árbol runtime: `1c7572fa8efee982c825c6d73b0884b7e6b75f76ff568af2b65dd7f5f43cac67`.
- 147 miembros tar, 146 entradas de manifiesto; nombres, tamaños y hashes internos verificados.
- SHA-256 remoto de `MANIFEST.sha256`: `ea887ba5648e81ace2b501082a6eae4a58d9e8d15d9c579c05ff1d63e6479b6b`.
- SHA-256 remoto de `RELEASE.json`: `1266ef626dc2b5348fe78226e879200b367dab1de175e83fea108801ca81a62a`.

Comparación con el release activo `cad-d0ea7a85e787`: cero rutas eliminadas, diez añadidas y nueve modificadas. Conserva `frontend/api/client.js`, `tools/backup_rotate.py`, las tres unidades systemd, sus dos documentos de despliegue y todos los módulos CAD/reconstrucción activos.

## Copia y restauración aislada

- Release activo/rollback capturado: `/home/kripta/apps/vexplorer/releases/cad-d0ea7a85e787`.
- Copia v2: `/home/kripta/apps/vexplorer/shared/backups/predeploy-d0ea7a85e787-tree1c7572fa8efee982-20261114T123904Z.zip`.
- Tamaño: 314.801 bytes.
- SHA-256: `673784cbd73bf00c04a9fe4573837ef20e665f8860643fffffefdbaa414f68f8`.
- Restauración nueva: `/home/kripta/apps/vexplorer/shared/restores/predeploy-d0ea7a85e787-tree1c7572fa8efee982-20261114T123904Z`.
- `integrity_check=ok` en `vexplorer.sqlite3`, `history.sqlite3` y `general_furniture.sqlite3` tanto en activo como restaurado.
- Todos los conteos por tabla del snapshot restaurado coinciden con el activo.
- Biblioteca: 0 registros; caché de embeddings: 0; histórico económico: 0. No se importaron demos, fixtures ni históricos.

La primera comprobación esperaba incorrectamente cero propuestas generales y se detuvo: producción ya contenía una propuesta y una revisión reales del flujo CAD. Se sustituyó esa expectativa por igualdad exacta entre todos los conteos activo/restaurado. El candidato se detuvo mediante trap y nunca tocó datos activos.

## Rehearsal del candidato

- Release extraído e inmutable: `/home/kripta/apps/vexplorer/releases/d0ea7a85e787-tree1c7572fa8efee982`.
- Dependencias: `pip check` correcto; import de `backend.app.main` y `tools.backup_rotate` correcto.
- Proceso temporal: un worker, solo `127.0.0.1:18793`, contra la restauración; detenido al terminar.
- Health, raíz pública, sesión anónima, config y lectura del run histórico: correctos.
- Biblioteca pública: HTTP correcto con `items=[]`, `design_count=0`, `record_count=0` y `duplicate_record_count=0`.
- Semántica: proveedor configurado, 256 dimensiones, cero registros indexados y generación pública bloqueada por autenticación; similitud geométrica offline disponible.
- Assets CAD/operativos comprobados: `frontend/api/client.js`, `frontend/core/similarity-ui.js`, `frontend/components/ReconstructionPanel.js`, `frontend/reconstruction.html` y `tools/backup_rotate.py`.
- Log final: `/home/kripta/apps/vexplorer/incoming/d0ea7a85e787-tree1c7572fa8efee982-rehearsal-final-20261114T124013Z.log`.

Al cierre del rehearsal, solo `127.0.0.1:18792` permanecía escuchando, `current` seguía en `cad-d0ea7a85e787`, el servicio continuaba activo con PID `463263` y no se modificó Caddy.

## Activación y verificación posterior

- GO explícito recibido de coordinación para el candidato y hash de este recibo.
- CAS inmediatamente anterior: `current=/home/kripta/apps/vexplorer/releases/cad-d0ea7a85e787`, servicio activo y cero jobs `queued` o `running`.
- Cambio realizado mediante symlink temporal y `mv -T` atómico.
- Se reinició únicamente `vexplorer.service`; quedó `active`, PID `513354`.
- `current` final: `/home/kripta/apps/vexplorer/releases/d0ea7a85e787-tree1c7572fa8efee982`.
- Rollback conservado: `/home/kripta/apps/vexplorer/releases/cad-d0ea7a85e787`.
- HTTP 200 público en health, raíz, sesión, config, Biblioteca y los cuatro assets CAD/operativos del rehearsal.
- Config pública: `library_requires_real_reviewed=true`; lectura, búsqueda geométrica y guardado offline disponibles; generación semántica pública de pago exige autenticación.
- Biblioteca pública vacía, coherente con la política: cero muebles reales revisados elegibles.
- Tras el reinicio: cero jobs activos; `integrity_check=ok` en las tres SQLite; Biblioteca y caché semántica en cero; histórico y embeddings históricos en cero.
- No se cambió Caddy ni otro servicio y no se importaron demos, fixtures o históricos.

La copia exacta recuperable es `/home/kripta/apps/vexplorer/shared/backups/predeploy-d0ea7a85e787-tree1c7572fa8efee982-20261114T123904Z.zip`; la restauración validada es `/home/kripta/apps/vexplorer/shared/restores/predeploy-d0ea7a85e787-tree1c7572fa8efee982-20261114T123904Z`. Si una verificación posterior exige rollback, se debe apuntar `current` atómicamente al release CAD anterior y reiniciar solo `vexplorer.service`.

## Parche UI final V4

V4 sustituyó a V3 y corrige exclusivamente la presentación del proveedor semántico configurado pero no disponible para generación pública, y la carga del histórico oculto.

- Candidato: `d0ea7a85e787-tree518ad7d881403b9b`.
- SHA-256 del archivo: `a86eb821494c529384daa294eaf27179d6947cbed4eee9b9f9d70e6fd0dd37b6`.
- SHA-256 del árbol runtime: `518ad7d881403b9b411a9389d7f83af3cc830d318ad4ceb26bcbff37b21dfd90`.
- 147 miembros tar y 146 entradas de manifiesto; hashes y tamaños verificados tras extraer.
- Delta exacto frente a V2: `frontend/app.js`, `frontend/core/ui.js` y `RELEASE.json`; sin cambios backend, de datos, CAD u operación.
- CAS inmediatamente anterior: `current` apuntaba exactamente a V2, cero jobs activos, las tres SQLite íntegras y todos los conteos idénticos a la restauración validada. Por ello se reutilizó la copia verificada sin crear otra copia redundante.
- Switch atómico y reinicio exclusivo de `vexplorer.service`; estado `active`, PID `525249`.
- `current` final: `/home/kripta/apps/vexplorer/releases/d0ea7a85e787-tree518ad7d881403b9b`.
- Rollback inmediato conservado: `/home/kripta/apps/vexplorer/releases/d0ea7a85e787-tree1c7572fa8efee982`.
- HTTP 200 público en health, raíz, sesión, config, Biblioteca, `app.js`, `core/ui.js` y assets CAD.
- Hash público de `app.js`: `99212a84950d27c720d2d765626d5e85544e1b707d9c60004230cb282b08c0c0`.
- Hash público de `core/ui.js`: `af86f8abc14f9cb0888935f61cc6895ff8df377e3b48b6a415a98cc2cc775823`.
- Post-smoke: cero jobs, Biblioteca, caché semántica, histórico y embeddings históricos; `integrity_check=ok` en las tres SQLite.
- QA de navegador público final: proveedor `text-embedding-3-small`, 256 dimensiones, cero indexados y búsqueda semántica no disponible sin autenticación; Biblioteca visible con conteos `0/0/0`; histórico y costes ocultos; cero errores de consola.
- Captura de evidencia: `.runtime/similarity-repair/public-library-final.png`.
- Caddy, otros servicios y datos no se modificaron; no hubo importaciones.
