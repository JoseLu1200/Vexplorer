# Integración de mejoras CAD y harness

Integración verificada, 14 de noviembre de 2026. Rama de trabajo: `feat/mounted-table-drawings`, sobre la demo de piezas separadas publicada en `main` (`164356b`). Los cambios de origen son de Pablo Loureiro en `origin/mejoras/cad-harness`; las adaptaciones las realizan agentes identificados en `team/`. El código final revisado es `5241a86`, con SHIP de GPT-6 Astra. Este documento distingue funciones adoptadas y exclusiones.

## Origen y decisión

Primer bloque: `e201506`, `2cb606c`, `1d4b747`, `2db9092`. Segundo bloque: `ccbad2a`, `c0d9db5`, `7bb29ae`, `26dbd15`, `d29fec7`. Ambos parten de un contrato anterior al flujo de mesa 0.5. No se aplican enteros sobre los archivos compartidos: A adapta ingesta/geometría; B mantiene la única definición Pydantic, API y harness; C conecta la interfaz. A y B acuerdan cualquier ampliación contractual antes de implementarla.

| Mejora de origen | Decisión inicial | Estado |
| --- | --- | --- |
| Tres vistas sin etiquetas por disposición | Solo cuando la asociación sea inequívoca; no aplicar a piezas separadas | Integrado y probado |
| Tipo de línea efectivo | Conserva transformaciones y controles de planitud actuales | Integrado y probado |
| Espesor por separaciones | Conservar evidencia geométrica y revisión; no incorporar el detector defectuoso del primer bloque | Detector antiguo excluido |
| Veta, cantos y lista de corte | CSV genérico por componentes/ocurrencias 0.5 con revisión/hash; veta y cantos desconocidos no se inventan | Integrado; edición individual de veta/cantos pendiente |
| Identificadores válidos en errores | Herramientas de los tres modos de entrada | Integrado y probado |
| Bloques, atributos, curvas, ordenadas y recuperación | Bloques acotados, círculos/arcos tipados, ELLIPSE/SPLINE aproximadas, ordenadas observadas y recuperación marcada | Integrado; HATCH/bulges excluidos |
| Filas de taladros y Sistema 32 | Evidencia geométrica neutral; catálogo no confirmado o datos incompletos mantienen unknown | Integrado y probado |
| Contexto compacto y respuestas acotadas | Listado paginado de evidencias, IDs de inspección limitados y hallazgos de taller acotados | Integrado; no se afirma compresión óptima general |
| Visión opcional | Herramienta nativa por vista del ledger; OFF por defecto, ON exige al menos una vista y máximo tres intentos | Integrado y probado con API real |
| Límite de salida configurable | 4096 por defecto; intervalo admitido 256–16384 | Integrado y probado |

## Evidencia disponible

La revisión aislada del primer bloque (`2db9092`) reprodujo 140 pruebas Python y 46 JavaScript correctas. También reprodujo dos defectos que esas pruebas no cubrían:

- Duplicar una línea de un solo lateral podía aparentar dos separaciones simétricas y producir una falsa observación de espesor.
- Repetir el identificador de un canto duplicaba su metraje en el CSV.

La geometría 0.5 ya distingue separaciones desde un borde y separaciones opuestas. El cálculo actual de cantos de mesa usa un alcance completo por ocurrencia, no la lista repetible del primer bloque. La integración debe conservar esas garantías y añadir regresiones donde se adopten las funciones nuevas.

La copia aislada del segundo bloque (`d29fec7`) también se verificó: 166 pruebas Python y 46 JavaScript pasan. La revisión adicional detectó límites tardíos de MINSERT, pérdida de plano Z/OCS, un falso `pass` de Sistema 32 y evidencia truncada sin acceso por páginas. Las adaptaciones se prueban sobre el contrato actual; el número de pruebas de origen no acredita su integración.

## Primer checkpoint integrado

Código `56f6f96`, 14 de noviembre de 2026: **287 pruebas Python y 81 JavaScript correctas**, `compileall` y `git diff --check` correctos. Auditoría HTTP de mesa: 26 comprobaciones correctas. GPT-6 Astra emite **SHIP incremental**, no cierre de toda la ampliación.

Este checkpoint incluye vistas montadas inferidas por disposición suficiente, tipo de línea efectivo, bloques anidados con iteración acotada, atributos, círculos/arcos tipados, lista de corte adaptada a 0.5, errores de referencias reparables, listado paginado de evidencia, salida configurable de 4096 tokens y plausibilidad de taller conservadora. La tarifa fija está en el catálogo y todas sus dependencias tarifarias resuelven. La geometría y las fuentes derivadas se validan en servidor.

El catálogo no confirmado produce `unknown`; no rellena dimensiones. El paquete wheel se construyó e instaló en un directorio aislado y se comprobó que carga su JSON de catálogo desde el paquete instalado. Siguen en preparación la ampliación restante de ingesta y el canal visual opcional; no se presentan como terminados en este checkpoint. Una prueba simulada del adaptador no acredita una llamada visual real.

## Cierre del segundo incremento

Código `5241a86`: **313 Python y 82 JavaScript**, 26 comprobaciones HTTP de geometría/revisión/exportación y 20 peticiones HTTP del ensayo live, todas correctas. El modelo llamó realmente a `visualizar_vista` para FRONT; la traza registra hash, cinco marcas y la propuesta posterior. Referencias y evidencias: [verificación final](VERIFICACION_MESA_CAD_2026-11-14.md).

La integración es selectiva. No se porta la lista repetible de cantos defectuosa ni el detector antiguo de espesor. Se excluyen HATCH/bulges/paperspace y ARC con orientación OCS negativa. La visión usa PNG contextuales derivados del ledger, no imágenes con respuestas ni medidas obtenidas por píxeles. No se cambia el stack ni se incorpora un framework de agentes.
