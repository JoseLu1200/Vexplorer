# Vexplorer — del plano al despiece y presupuesto revisables

**Estado: documentación, plan y herramienta de preparación del dataset. La aplicación todavía no está implementada.**

El [piloto del dataset](docs/PILOTO_DATASET.md) ya se ha generado: 14 DXF y 3 casos PDF de vistas 2D, con referencias separadas y un ZIP independiente por caso. Incluye comandos y verificaciones reproducibles.

Vexplorer ayuda a interpretar planos de mobiliario: localiza elementos, extrae medidas con código determinista, propone nombres y agrupaciones y presenta un despiece revisable cuando la evidencia permite obtenerlo. La selección de una pieza enlaza con los contornos que la justifican. Lo desconocido permanece visible; una medida no aparece por la suposición de un modelo.

La arquitectura acordada usa **Python 3.11+, FastAPI, Pydantic, ezdxf, tool use nativo, un bucle propio, HTTP/SSE y frontend JS/HTML con three.js**. El detalle propuesto para implementar está en estos documentos y requiere el acuerdo de contrato indicado en `CLAUDE.md`.

El objetivo completo, según la [transcripción](transcripcion-contexto-poc.md), es **inferir piezas y secciones desde planos 2D pobres y estimar costes y tiempos con muebles históricos similares**. El plan original del ZIP cubría sobre todo extracción; se amplía en T11–T13 con hipótesis separadas de hechos, un corpus de entrada/referencia sin fugas y comparables explicados. Véase [CASO_DE_USO_Y_EVALUACION](docs/CASO_DE_USO_Y_EVALUACION.md).

## Dataset de trabajo actual

Se adopta **`engineering-drawings-harness.zip` como corpus auxiliar de pruebas técnicas**, pendiente de admitir cada caso para el comportamiento que realmente evalúe. Sustituye al corpus anterior de bloques de mobiliario, descartado por no aportar despiece y cotas de componentes.

| Subcolección | Contenido comprobado | Uso propuesto |
|---|---|---|
| OrlaMechCAD-Nano | 14 piezas individuales, cada una con DXF, DWG, PDF y STEP; registros estructurados de cotas | Extracción CAD y trazabilidad de medidas. No son 14 conjuntos despiezados. |
| Mechanical Bench Vise | Un conjunto en PDF con BOM de 12 referencias y 22 unidades; 9 planos individuales | Piloto de asociación conjunto–pieza. La referencia dimensional revisada es Jaw Pad. |
| Julius de Waal | 50 paquetes PDF de conjuntos, 158 páginas | Ampliar variedad de listas de piezas, detalles y cotas tras anotación. |

El ZIP tiene 422 archivos. La evidencia concreta, el alcance de la auditoría y la procedencia están en [DATASET.md](docs/DATASET.md). Sus planos son mecánicos: permiten probar capacidades transferibles, pero **no validan por sí solos un despiece de muebles**.

El plano Jaw Pad muestra **69,85 × 44,45 × 5 mm**; la cantidad **2** procede de la BOM del conjunto. Se verificaron esos documentos visualmente. Las demás dimensiones de la referencia Bench Vise permanecen sin revisar. No se confunde cantidad de vistas con cantidad de piezas.

## Primer hito técnico (T1–T10)

1. Abrir un DXF admitido, resolver unidades y mostrar geometría y cotas con su origen.
2. Generar candidatas y conservar su identidad y campos desconocidos.
3. Permitir al agente inspeccionar evidencia, proponer nombres y entregar mediante `entregar_despiece`.
4. Validar, persistir y mostrar tabla, traza y selección bidireccional con el plano.
5. Exportar JSON/CSV y representar cajas esquemáticas únicamente con dimensiones justificadas.

El recorrido de despiece de paneles se verifica con un **fixture propio, explícitamente sintético y revisado**. El nuevo corpus aporta pruebas reales de CAD. El conjunto Bench Vise permite preparar un piloto PDF P1; no se declara compatible con el lector DXF. [ADAPTACION_DATASET.md](docs/ADAPTACION_DATASET.md) explica la separación y qué exigir para ampliar el alcance.

## Prueba de concepto de negocio (T11–T13)

Preparar planos pobres de mobiliario con despiece de referencia reservado al evaluador; proponer componentes y alternativas revisables; recuperar proyectos históricos por atributos y embeddings; calcular una estimación provisional con ajustes documentados de dimensiones, materiales y acabados. La ficha exportada distingue medidas observadas, cálculos, hipótesis y confirmaciones humanas. Faltan referencias reales de mobiliario e histórico económico para validar este objetivo; los fixtures sintéticos solo prueban el mecanismo.

## Orden de lectura

| Documento | Propósito |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Instrucciones del equipo, stack y permisos de edición |
| [initial-plan.md](initial-plan.md) | Objetivo, arquitectura inicial y decisiones de alcance |
| [docs/DATASET.md](docs/DATASET.md) | Auditoría del dataset y límites de sus referencias |
| [docs/CONTRATOS_DATOS.md](docs/CONTRATOS_DATOS.md) | Propuesta de modelos; acuerdo A/B pendiente, aviso C |
| [ORGANIZACION.md](ORGANIZACION.md) | Reparto, dependencias e integración |
| [PLAN.md](PLAN.md) | Tareas concretas, rutas futuras y criterios de aceptación |

## Documentación técnica

| Archivo | Contenido |
|---|---|
| [ARQUITECTURA](docs/ARQUITECTURA.md) | Componentes, flujo, estados y límites |
| [GEOMETRIA_Y_PLANOS](docs/GEOMETRIA_Y_PLANOS.md) | Unidades, transformaciones, contornos, cotas y vistas |
| [SEMANTICA](docs/SEMANTICA.md) | Significado, similitud, identidad y agrupación |
| [HARNESS](docs/HARNESS.md) | Herramientas, bucle, reparación, límites y contingencias |
| [VALIDACION](docs/VALIDACION.md) | Comprobaciones deterministas y abstención |
| [API_Y_EVENTOS](docs/API_Y_EVENTOS.md) | API, geometría para el visor, SSE y revisión |
| [EJEMPLOS_CONTRATO](docs/EJEMPLOS_CONTRATO.md) | Ejemplo documental de tres vistas y una pieza |
| [TDD](docs/TDD.md) | Desarrollo por comportamiento con oráculos independientes |
| [TEST_PLAN](docs/TEST_PLAN.md) | Casos positivos, negativos y criterios de evaluación |
| [DEMO_Y_OPERACION](docs/DEMO_Y_OPERACION.md) | Guion, operación y modos de contingencia |
| [FUENTES_Y_DECISIONES](docs/FUENTES_Y_DECISIONES.md) | Fuentes primarias y registro de decisiones |
| [team/README](team/README.md) y [plantilla](team/_TEMPLATE.md) | Coordinación sin identidades ni reservas ficticias |
| [AGENTS](AGENTS.md) | Guía de navegación subordinada a `CLAUDE.md` |

**Pydantic será la única fuente de verdad del formato JSON.** El esquema que ve el proveedor se generará desde los modelos; estos Markdown son una propuesta previa. No se entrega un segundo esquema mantenido a mano ni se afirma un acuerdo A/B que no se ha producido.

## Primera hora

A y B revisan el contrato y registran su acuerdo; C recibe las interfaces del plano y del resultado. D, si existe, selecciona un caso CAD de desarrollo y registra las medidas esperadas fuera del sistema. Cada integrante se identifica y designa su archivo personal antes de editar código, conforme a `CLAUDE.md`.

La primera integración debe mostrar una medida con su evidencia de origen. La siguiente añade revisión y resultado persistido. La IA y el visor 3D se incorporan sobre ese recorrido comprobable.

## Criterio de éxito

Una persona carga un plano pobre admitido, revisa propuestas de piezas y secciones, consulta muebles históricos similares y exporta una ficha de despiece y estimación con procedencia y supuestos. La evaluación compara con despieces reservados y presupuestos/horas de referencia donde existan, además de medir la corrección humana necesaria. Si faltan datos, sabe cuáles faltan. `completed` describe el resultado de las comprobaciones implementadas, no una certificación de fabricación.

La auditoría de archivos y las pruebas del preparador del dataset se han ejecutado; las pruebas de la aplicación siguen **pendientes de implementar**. Los CAD de terceros y las respuestas de referencia no se incluyen en este paquete Markdown. Fecha: **13 de noviembre de 2026, UTC**.
