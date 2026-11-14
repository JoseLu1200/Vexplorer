# Agente UX despliegue

## Identidad y alcance

- Identidad: agente delegado `deploy_prepare`.
- Alcance: inspección, preparación, ensayo aislado, activación autorizada, verificación y limpieza del despliegue privado.
- No realizado: cambios en Caddy, otras aplicaciones, backend/frontend, commit o push.

## Estado observado — 2026-11-14

- URL real: `https://gex-dashboard.hopto.org/vexplorer/`.
- Release remoto activo: `a61f97a89a86-treec58bbe42140dd03c`.
- `vexplorer.service`: activo y habilitado; escucha exclusivamente en `127.0.0.1:18792`.
- Health público: HTTP 200. Raíz sin credenciales: HTTP 401.
- Configuración privada y usuarios: presencia confirmada sin leer contenido; `production.env` tiene modo 0600.
- Copia de aceptación documentada: presencia confirmada.
- Espacio: 8.129.785.856 bytes libres; volumen al 95 %. Es suficiente para un paquete de código y un ensayo pequeño, pero no autoriza borrar releases, copias ni datos de otras aplicaciones.

## Preparación realizada

- `.runtime/deploy-prep/build-release.ps1` empaqueta un release completo desde el árbol aprobado.
- El gate rechaza cambios no confirmados en `backend/app` o `tools`; permite snapshot del frontend final tras QA.
- El paquete usa lista blanca, manifiesto SHA-256 y no incluye secretos, datos, pruebas, documentación, `.runtime` ni datasets.
- La eliminación del staging valida ruta absoluta dentro de `.runtime/deploy-prep`, dentro del output autorizado y nombre `stage-*`, tanto antes de crear como inmediatamente antes de eliminar.
- Actualización ordinaria: release inmutable + `current` + reinicio exclusivo de `vexplorer.service`; Caddy no cambia.
- El corte exige sesión, config y lectura de un run histórico con Basic Auth antes y después de activar; un fallo de reinicio, health o smoke autenticado revierte `current` y reinicia solo el servicio propio.

## Credenciales QA

- No hay `storageState`, netrc ni credencial Basic recuperable en los artefactos locales de producción/QA inspeccionados.
- `.env` solo declara el nombre `OPENAI_API_KEY`; no se leyó ni registró su valor.
- El archivo remoto `shared/secrets/users.json` es 0600 y contiene un objeto con una entrada `username -> hash string`; ese hash no permite autenticarse.
- La identidad temporal no secreta `qa-vexplorer-20261114` se creó primero en una copia separada y después se instaló solo durante la aceptación pública.
- Tras la aceptación se eliminó mediante `tools.manage_users`, se reinició únicamente Vexplorer y la credencial anterior devolvió 401.
- El SHA-256 de `shared/secrets/users.json` vuelve a coincidir exactamente con el backup pre-QA; queda una sola identidad original y su hash no cambió.
- Se eliminaron netrc, users candidato, clave/cert TLS efímeros y secreto local. No quedan listeners de candidato ni túnel.

## Riesgos de compatibilidad

- El frontend actual requiere el backend nuevo: mobiliario general, ingesta DXF/DWG/PDF e histórico/escenarios.
- El backend añade `general_furniture.sqlite3` e `history.sqlite3` dentro de `shared/data` por defecto. La copia v2 los autodetecta cuando existen.
- La configuración del host ya documenta límites del crítico general. DWG no debe activarse hasta smoke genuino; el binario preparado no equivale a soporte validado.
- El release previo, backups y restauraciones se conservan para recuperación; no se borraron datos ni artefactos.

## Cierre observado

- Payload tree SHA-256: `c58bbe42140dd03c7f5154a93868613e8f1f18fffab68c3af46de944ebcc58e5`.
- Archivo transferido SHA-256: `ed367c28920af79111350f68ae72580bbf975c7b09b09045b621cc6f988b05b6`; hashes local y remoto idénticos.
- Gates previos comunicados por coordinación: 596 pruebas Python, 162 JavaScript, 17 backend focales, Lighthouse 100 y revisor final SHIP.
- Rehearsal sobre restauración: manifiesto, `pip check`, health, auth, config y lectura del run histórico correctos.
- Playwright candidato: hashes de assets/fuentes, R2 restaurada, breakpoints, foco, tema y consola/red sin errores.
- Ensayo Linux adicional sobre restauración: upload DXF 201, job 202, `geometry_only` R1 y piezas esperadas (tapa 1200 × 700 × 30 mm; dos soportes 720 × 700 × 18 mm). El primer 403 fue la protección de origen local; se repitió con TLS efímero HTTPS sin relajar el guard de producción.
- Playwright público: release exacto, R2, assets, 1440/1100/390, tema y drawer correctos; cero errores JavaScript/HTTP.
- Estado final: `vexplorer.service` activo y habilitado, `127.0.0.1:18792`, health público 200, raíz anónima 401, `current` en el release nuevo y QA temporal ya retirada.
