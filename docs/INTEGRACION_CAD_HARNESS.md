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

Las 166 pruebas comunicadas para el segundo bloque son un resultado de su autor, todavía no una verificación de esta integración. Una prueba simulada del adaptador tampoco acredita una llamada visual real. Los resultados finales y las exclusiones se actualizarán tras integrar y ejecutar las pruebas.
