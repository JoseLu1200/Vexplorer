# Verificación del incremento privado y PR1

La base auditada fue `10da225`. La implementación revisada quedó en `d3d5e3a1e52aa6e91b43f3f44a63d288d92df791`; GPT-6 Astra emitió SHIP sobre ese SHA sin hallazgos concretos abiertos. Los implementadores fueron agentes GPT-6.1 Sol y el coordinador, con propiedad de archivos separada.

## Integración publicada

La [PR1](https://github.com/JoseLu1200/Vexplorer/pull/1) quedó merged el 2026-11-14 a las 02:44:40 UTC. El merge `9a7aeac` tiene como padres `d3d5e3a` y `0fe4be7`; su árbol es idéntico al revisado (`bf4645ab624cb93c97ff6e2da9c3f81747aacff8`). Se incorporaron primero las adaptaciones y después se unieron ambos historiales conservando ese árbol, según la [matriz de los 14 commits](INTEGRACION_PR1_2026-11-14.md). Main se actualizó por fast-forward y push normal, sin force push.

## Pruebas observadas

- Python integrado: **423 passed**, 57,89 s; un aviso conocido de deprecación de Starlette/TestClient con httpx.
- JavaScript integrado: **108 passed**.
- Compilación Python, `pip check`, construcción wheel y comprobación de whitespace correctas. El [CI final](https://github.com/JoseLu1200/Vexplorer/actions/runs/43548181609) pasó también pruebas, empaquetado y construcción Docker en Ubuntu 24.04 con el código integrado.
- Astra reprodujo los fallos corregidos y verificó además 18 pruebas focales de replay/reservas, 108 JavaScript y cinco casos de rollback CAS de Caddy.
- La auditoría inicial cubre los 495 commits accesibles al comenzar, Markdown y módulos propios: [informe](AUDITORIA_COMPLETA_2026-11-14.md).

Las correcciones incluyen reservas de grabación antes del proveedor, confirmaciones humanas con identidad única, catálogos vacíos rechazados, asignaciones de material a IDs inexistentes rechazadas, conservación de la referencia ante fallos de red y coste de autenticación equivalente para identidades existentes/inexistentes.

## Navegador local con prefijo

En `/vexplorer/` se cargó el fixture propio `mesa_demo_001.dxf`, se completó el job y se registró una revisión automática explícitamente sintética. Se generaron vistas generales, por componente y de despiece. La tapa conserva 1200 × 700 × 30 mm y los dos soportes 720 × 700 × 18 mm bajo las premisas aceptadas del ensayo.

El coste demo permaneció parcial con mano de obra/acabado sin resolver. Con exclusiones justificadas de ensayo produjo 198,32 EUR, dos horas y precio provisional 247,90 EUR al 20 % de margen. No son tarifas comerciales. Cambiar sólo la tapa a tarifa por volumen produjo 22,68 EUR para esa tapa y conservó 42,34 EUR de material para los soportes; el formulario recuperó la tarifa general y el override después de recargar.

Una respuesta de proxy HTML 404 y un 503 simulado conservaron la URL y el identificador local; “Reintentar” recuperó la revisión 2. Sólo un `404/run_not_found` confirmado o un identificador inválido descarta la referencia. Estos ensayos modificaron exclusivamente datos propios sintéticos.

## Infraestructura

El primer CI encontró que `ubuntu-latest` había pasado a Ubuntu 26.04, sin distribución de Python 3.14.2 en el manifiesto de Actions. El commit `40a7de0` fija Ubuntu 24.04, que sí dispone de esa distribución. No cambió las dependencias de la aplicación. Su ejecución CI terminó correctamente.

El primer intento de servicio en el VPS falló con `218/CAPABILITIES` antes de modificar Caddy. El ejecutor detuvo únicamente `vexplorer.service`; el Caddyfile conservó su hash previo y los endpoints ajenos conservaron sus códigos. El despliegue y sus comprobaciones finales se documentan cuando quedan observados, no a partir de este primer intento.

## Alcance de la aceptación

Se acepta el flujo privado de las familias soportadas, la trazabilidad de medidas/propuestas/revisiones, planos derivados, cálculo configurable y replay verificable. La [aceptación independiente local](ACEPTACION_PRODUCCION.md) conserva además el oráculo económico y los ensayos de preparación de datasets.

Las tarifas del despliegue inicial son demo. Siguen requiriéndose tarifas y planos representativos del equipo, validación con técnicos y medición de precisión/tiempo para afirmar utilidad industrial. No se certifican uniones, mecanizados, colisiones ni fabricación; no se afirma descomposición general de cualquier mueble o formato CAD.
