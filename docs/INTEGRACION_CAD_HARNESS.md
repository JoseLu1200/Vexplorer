# Integración de mejoras CAD y harness

Trabajo en curso, 14 de noviembre de 2026. Rama de integración: `feat/mounted-table-drawings`, sobre la demo de piezas separadas publicada en `main` (`164356b`). Los cambios de origen son de Pablo Loureiro en `origin/mejoras/cad-harness`; las adaptaciones las realizan agentes identificados en `team/`. Este documento distingue decisiones de integración de capacidades verificadas.

## Origen y decisión

Primer bloque: `e201506`, `2cb606c`, `1d4b747`, `2db9092`. Segundo bloque: `ccbad2a`, `c0d9db5`, `7bb29ae`, `26dbd15`, `d29fec7`. Ambos parten de un contrato anterior al flujo de mesa 0.5. No se aplican enteros sobre los archivos compartidos: A adapta ingesta/geometría; B mantiene la única definición Pydantic, API y harness; C conecta la interfaz. A y B acuerdan cualquier ampliación contractual antes de implementarla.

| Mejora de origen | Decisión inicial | Estado |
| --- | --- | --- |
| Tres vistas sin etiquetas por disposición | Adoptar solo cuando la asociación sea inequívoca; no aplicar a piezas separadas | Pendiente de integración |
| Tipo de línea efectivo | Adoptar conservando transformaciones y controles de planitud actuales | Pendiente de integración |
| Espesor por separaciones | Conservar evidencia geométrica y revisión; no incorporar el detector defectuoso del primer bloque | Detector antiguo excluido |
| Veta, cantos y lista de corte | Evaluar adaptación a componentes y ocurrencias 0.5, con revisión/hash e incógnitas explícitas | En evaluación |
| Identificadores válidos en errores | Adaptar a las herramientas de los tres modos de entrada | Pendiente de integración |
| Bloques, atributos, curvas, tramas, ordenadas y recuperación | Revisar aproximaciones, unidades, límites y procedencia antes de adoptar | En revisión |
| Filas de taladros y Sistema 32 | Revisar condiciones geométricas y conservación de desconocidos | En revisión |
| Contexto compacto y respuestas acotadas | Adaptar sin perder evidencia ni permitir números aportados por el modelo | En revisión |
| Visión opcional | Mantener desactivada por defecto; verificar el contenido visual entregado al proveedor | Sin prueba live de esta integración |
| Límite de salida configurable | Adoptar un valor predeterminado de 4096 y validar configuración | Pendiente de integración |

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
