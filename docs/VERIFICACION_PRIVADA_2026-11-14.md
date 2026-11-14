# Verificación del incremento privado y PR1

La base auditada fue `10da225`. La implementación revisada quedó en `d3d5e3a1e52aa6e91b43f3f44a63d288d92df791`; GPT-6 Astra emitió SHIP sobre ese SHA sin hallazgos concretos abiertos. Los implementadores fueron agentes GPT-6.1 Sol y el coordinador, con propiedad de archivos separada.

## Integración publicada

La [PR1](https://github.com/JoseLu1200/Vexplorer/pull/1) quedó merged el 2026-11-14 a las 02:44:40 UTC. El merge `9a7aeac` tiene como padres `d3d5e3a` y `0fe4be7`; su árbol es idéntico al revisado (`bf4645ab624cb93c97ff6e2da9c3f81747aacff8`). Se incorporaron primero las adaptaciones y después se unieron ambos historiales conservando ese árbol, según la [matriz de los 14 commits](INTEGRACION_PR1_2026-11-14.md). Main se actualizó por fast-forward y push normal, sin force push.

## Pruebas observadas

- Python integrado: **423 passed**, 57,89 s; un aviso conocido de deprecación de Starlette/TestClient con httpx.
- JavaScript integrado: **108 passed**.
- Compilación Python, `pip check`, construcción wheel y comprobación de whitespace correctas. El [CI del release desplegado](https://github.com/JoseLu1200/Vexplorer/actions/runs/43549417513) pasó también pruebas, empaquetado y construcción Docker en Ubuntu 24.04 sobre `cd57f4f`.
- Astra reprodujo los fallos corregidos y verificó además 18 pruebas focales de replay/reservas, 108 JavaScript y cinco casos de rollback CAS de Caddy.
- La auditoría inicial cubre los 495 commits accesibles al comenzar, Markdown y módulos propios: [informe](AUDITORIA_COMPLETA_2026-11-14.md).

Las correcciones incluyen reservas de grabación antes del proveedor, confirmaciones humanas con identidad única, catálogos vacíos rechazados, asignaciones de material a IDs inexistentes rechazadas, conservación de la referencia ante fallos de red y coste de autenticación equivalente para identidades existentes/inexistentes.

## Navegador local con prefijo

En `/vexplorer/` se cargó el fixture propio `mesa_demo_001.dxf`, se completó el job y se registró una revisión automática explícitamente sintética. Se generaron vistas generales, por componente y de despiece. La tapa conserva 1200 × 700 × 30 mm y los dos soportes 720 × 700 × 18 mm bajo las premisas aceptadas del ensayo.

El coste demo permaneció parcial con mano de obra/acabado sin resolver. Con exclusiones justificadas de ensayo produjo 198,32 EUR, dos horas y precio provisional 247,90 EUR al 20 % de margen. No son tarifas comerciales. Cambiar sólo la tapa a tarifa por volumen produjo 22,68 EUR para esa tapa y conservó 42,34 EUR de material para los soportes; el formulario recuperó la tarifa general y el override después de recargar.

Una respuesta de proxy HTML 404 y un 503 simulado conservaron la URL y el identificador local; “Reintentar” recuperó la revisión 2. Sólo un `404/run_not_found` confirmado o un identificador inválido descarta la referencia. Estos ensayos modificaron exclusivamente datos propios sintéticos.

## Infraestructura

El primer CI encontró que `ubuntu-latest` había pasado a Ubuntu 26.04, sin distribución de Python 3.14.2 en el manifiesto de Actions. El commit `40a7de0` fija Ubuntu 24.04, que sí dispone de esa distribución. No cambió las dependencias de la aplicación. Su ejecución CI terminó correctamente.

El primer intento de servicio en el VPS falló con `218/CAPABILITIES` antes de modificar Caddy. Se reprodujo el problema por separado con `PrivateDevices=yes` y `ProtectKernelModules=yes` en el gestor de usuario de este host. `06deea0` elimina únicamente esas dos directivas; el resto de restricciones funciona conjuntamente. Astra revisó esta adaptación antes de instalarla.

La primera prueba real del proveedor detectó un esquema JSON incompatible: una tupla de dos IDs emitía `prefixItems` sin `items`. `cd57f4f` expresa la lista homogénea con `items: string` y longitud exacta de dos; conserva IDs distintos y revisión vigente. La regresión y 16 pruebas focales pasaron; Astra dio GO y el CI completo pasó. La ejecución real posterior terminó correctamente.

## Despliegue observado

Disponible en **[https://gex-dashboard.hopto.org/vexplorer/](https://gex-dashboard.hopto.org/vexplorer/)**, con autenticación individual y almacenamiento persistente. Release runtime `cd57f4f4ac3dca81b82a2d520057dfe3261b07be`; SHA-256 del paquete transferido `b7f193a6c7fa223884c85ed1b11087ef8ef3f28155b5351c10b9f5fcf2f0fcf8`. Se verificaron los hashes de los 77 archivos runtime del manifiesto. Los commits documentales posteriores no cambian ese runtime.

`vexplorer.service` está activo y habilitado en `systemd --user`, con `Linger=yes`, un worker y escucha exclusiva en `127.0.0.1:18792`. Código en `/home/kripta/apps/vexplorer/releases/<revision>`, enlace `current`, datos en `shared/data` y configuración/credenciales en archivos privados separados del release. No se reiniciaron servicios de otras aplicaciones.

La nueva ruta Caddy conserva el `/api` existente y los catch-all. El backup previo es `/home/kripta/apps/vexplorer/rollback/Caddyfile.before-vexplorer-06deea06fb25`; SHA-256 previo `c7606114e72108d54e4003ed2e4d0bad0e6e691879f4f51dde319a58805218cd`, final `c297ea0be19686a5e0a0539e0a9220383f5170c7f4dfa086ddd14c37dab835d4`. La aplicación del proxy y su rollback comprueban el hash actual antes de escribir para conservar cambios concurrentes.

Las ocho rutas ajenas conservaron sus códigos antes del despliegue, después de la actualización y tras el reinicio de Vexplorer:

| Ruta | Antes/después |
| --- | --- |
| `/` | 200 |
| `/nexia/` | 200 |
| `/carta/` | 404 |
| `/evocon/` | 200 |
| `/altare/` | 200 |
| `/j-aautomation/` | 308 |
| `/webmail/` | 404 |
| `/api/` | 404 |

Estos checks comprueban continuidad HTTP, no sustituyen pruebas funcionales internas de esas aplicaciones. En Vexplorer, health responde 200 sin credenciales; aplicación y sesión responden 401 anónimas y 200 autenticadas. Un POST con origen ajeno devuelve 403. Navegador real: sesión del servidor visible, revisión 2 recuperada y SVG general acotado cargado y ampliado correctamente.

## Flujo real, replay y recuperación

El job geométrico sobre `mesa_demo_001.dxf` terminó, conservó la identidad del servidor al revisar y generó cuatro láminas: general, tipos de componente y despiece. Se descargaron los ocho SVG/DXF y las exportaciones JSON/CSV. El coste demo permaneció parcial sin convertir conceptos pendientes en cero. Run de ensayo `run-1d40a113cc57402393f6576269689be4`.

El job live con `gpt-6.1-sol` produjo `run-1d168234c2a64c579589ce40bc8f2994`; el replay produjo `run-3342ea2ed6774a08a1d306fed3aa96b9`. Ambos finalizaron `succeeded`. La grabación conserva dos respuestas del proveedor y transcript SHA-256 `88e46885ff6a0ffdead95aa43f693e853c03f85384bbc47b663528b482846d8c`. Se compararon por GET ambos resultados JSON: iguales salvo `run_id` y `created_at`. Replay usa exclusivamente el proveedor de grabación, valida solicitudes por turno y exige el hash canónico exacto de la salida; Astra confirmó que no hay una nueva llamada al proveedor ni importación de decisiones humanas.

El 2026-11-14 a las 03:06 UTC se reinició únicamente `vexplorer.service`, comprobando cambio de PID, servicio habilitado, linger y escucha loopback. Los cuerpos de 18 GET (runs, jobs, manifiesto, costes, SVG/DXF y exportaciones) conservaron sus SHA-256 tras el reinicio. Caddy no cambió y las ocho rutas anteriores conservaron su respuesta.

Se creó una copia online consistente en `/home/kripta/apps/vexplorer/shared/backups/accepted-20261114T030644Z.zip`, SHA-256 `5baff7999f687a9fa2f8189eebc45836f9dd19404b0758e2075c8bf5e9eea836`. La copia descargada coincidió con ese hash; se restauró en un directorio local nuevo, validando manifiesto, hashes de cada archivo y `PRAGMA integrity_check = ok`. El servidor local sobre la restauración devolvió los mismos cuerpos para los 18 GET. Contiene tres runs, cuatro jobs (incluido el fallo previo del proveedor), cuatro revisiones, una grabación, cero reservas pendientes, una estimación y ocho artefactos.

Las evidencias de ejecución y credenciales quedan fuera de Git en `.runtime/production/`. Esta prueba acredita copia y recuperación manuales de datos. No configura una política automática de copias externas ni incluye secretos/configuración en el ZIP; su custodia se describe en [PRODUCCION](PRODUCCION.md).

GPT-6 Astra revisó por separado el cierre operativo, el script y sus reportes; recalculó el hash de la copia, su integridad y los conteos restaurados. Emitió GO/PASS para `cd57f4f` sin hallazgos técnicos abiertos.

## Alcance de la aceptación

Se acepta el flujo privado de las familias soportadas, la trazabilidad de medidas/propuestas/revisiones, planos derivados, cálculo configurable y replay verificable. La [aceptación independiente local](ACEPTACION_PRODUCCION.md) conserva además el oráculo económico y los ensayos de preparación de datasets.

Las tarifas del despliegue inicial son demo. Siguen requiriéndose tarifas y planos representativos del equipo, validación con técnicos y medición de precisión/tiempo para afirmar utilidad industrial. No se certifican uniones, mecanizados, colisiones ni fabricación; no se afirma descomposición general de cualquier mueble o formato CAD.
