# Fuentes y decisiones de diseño

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

**Fecha de revisión: 13 de noviembre de 2026.** Las capacidades de una librería o los campos de un dataset no demuestran que Vexplorer los haya implementado. El paquete contiene documentación y referencias contrastadas, no resultados de una aplicación desplegada.

## Evidencia recibida y comprobación local

La fuente del corpus actual es el ZIP aportado por el usuario, `engineering-drawings-harness.zip`, identificado por SHA-256 en [DATASET.md](DATASET.md). Se leyeron sus índices, manifiestos, referencias y registros; se abrieron 14 DXF, se contrastaron handles y unidades y se revisaron visualmente los PDF de conjunto Bench Vise y detalle Jaw Pad.

`verification.json` describe comprobaciones del preparador del paquete; no se atribuyen automáticamente a esta revisión. Los PDF Julius conservan planos fuente sin anotaciones completas por pieza. DWG se inspeccionó por encabezado y STEP por texto/sidecars, sin lector DWG ni kernel geométrico independiente. Las filas Parquet no se abrieron en esta auditoría.

El `CLAUDE.md` y la arquitectura inicial son instrucciones aportadas por el equipo. Los nombres de integrantes, aprobaciones A/B y reservas personales no se conocen ni se inventan. Los demás documentos desarrollan una propuesta técnica para revisarla e implementarla.

## Fuentes técnicas primarias

| ID | Fuente | Uso en esta especificación |
|---|---|---|
| F1 | [ezdxf: unidades](https://ezdxf.readthedocs.io/en/stable/concepts/units.html) | Contexto de unidades de dibujo y bloques |
| F2 | [ezdxf: DIMENSION](https://ezdxf.readthedocs.io/en/stable/dxfentities/dimension.html) | Tipos de cota, valor opcional, texto y medición |
| F3 | [ezdxf: INSERT](https://ezdxf.readthedocs.io/en/stable/blocks/insert.html) | Instancias, transformaciones y límites de entidades virtuales |
| F4 | [ezdxf: ODA](https://ezdxf.readthedocs.io/en/stable/addons/odafc.html) | Conversor externo e integración DWG/DXF |
| F5 | [Open Design Alliance: conversor](https://www.opendesign.com/guestfiles/oda_file_converter) | Binario de conversión y plataforma |
| F6 | [Pydantic: JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/) | Generar esquemas desde modelos; única autoridad de contratos |
| F7 | [Claude: definir herramientas](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools) | Nombres, descripciones y esquemas nativos |
| F8 | [Claude: gestionar llamadas](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls) | Correlación de `tool_use` y `tool_result` |
| F9 | [FastAPI: tareas de fondo](https://fastapi.tiangolo.com/tutorial/background-tasks/) | Delimitar ejecución de trabajo pesado |
| F10 | [FastAPI: respuestas personalizadas](https://fastapi.tiangolo.com/advanced/custom-response/) | Transporte de respuestas en streaming |
| F11 | [WHATWG: Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html) | Formato, IDs y reconexión SSE |

Las URLs pueden corresponder a versiones posteriores a las instaladas. La auditoría CAD de esta entrega utilizó ezdxf 1.4.4; la documentación estable consultada se anunciaba como 1.4.5. Fijar y registrar dependencias compatibles en `pyproject.toml` al implementar. No afirmar que una actualización de documentación cambia la versión ya usada.

## Procedencia pública de las subcolecciones

| Fuente | Relación con el paquete |
|---|---|
| [OrlaLabs / OrlaMechCAD-Nano](https://huggingface.co/datasets/OrlaLabs/OrlaMechCAD-Nano) | Ficha del publicador: componentes emparejados, sidecars y licencia declarada |
| [Amir-souhail / Mechanical-Bench-Vise](https://github.com/Amir-souhail/Mechanical-Bench-Vise) | Repositorio del autor: conjunto, dibujos y README conservado |
| [Catálogo Julius de Waal](https://non-bin.github.io/juliusDeWaal/) | Catálogo del recopilador; los dibujos y sus avisos son la fuente de contenido |

Las condiciones por subcolección se registran en [DATASET.md](DATASET.md). Los datos se conservan como fuentes de desarrollo; esta entrega no redistribuye el ZIP ni cambia sus condiciones. Las referencias de medidas del ejemplo sintético de panel son propias de la documentación, sin atribuirlas al corpus.

## Registro de decisiones

| ID | Decisión propuesta | Motivo y condición de revisión |
|---|---|---|
| ADR-01 | DXF P0; DWG con ODA P1 | Los 14 componentes ya tienen DXF; el conversor externo no bloquea el primer recorrido |
| ADR-02 | Geometría antes del agente | Toda interpretación necesita hechos medibles y procedencia |
| ADR-03 | Bucle propio y tool use nativo | Control directo de límites, fallos y entrega |
| ADR-04 | Referencias de medidas en Submission | El servidor resuelve los valores; el LLM no los reescribe |
| ADR-05 | Pydantic como única autoridad | Generar esquemas, evitar contratos divergentes y respetar `CLAUDE.md` |
| ADR-06 | Identidad separada de similitud | Vistas repetidas y variantes pueden compartir geometría |
| ADR-07 | Validar restricciones con premisas | R-015 y colisiones físicas son `not_applicable` en P0 hasta tener datos suficientes |
| ADR-08 | Cajas 3D identificadas como esquema | Una envolvente no demuestra ensamblaje ni mecanizado |
| ADR-09 | Corpus separado por tarea | 14 piezas CAD no son 14 conjuntos; PDF requiere otro adaptador |
| ADR-10 | Fixture propio para despiece de paneles | Los mecanismos no prueban todavía semántica de mobiliario |
| ADR-11 | Fuente y oráculo separados | No dar las respuestas JSON o STEP al agente de la evaluación solo plano |
| ADR-12 | Particiones por diseño/familia | Mantener juntos formatos, vistas, detalles y revisiones |
| ADR-13 | Abstención persistida y revisión versionada | La falta de evidencia debe producir un resultado revisable, sin promover borradores inválidos |
| ADR-14 | Replay y geometría sin API visibles | Conservar procedencia y una demo honesta ante fallos del proveedor |
| ADR-15 | PDF Bench Vise como piloto P1 | Conjunto y detalle permiten un objetivo acotado; requiere acuerdo A/B de procedencia y semántica |
| ADR-16 | MCP y entrenamiento fuera del recorrido inicial | Reutilizar herramientas después de demostrar utilidad con datos suficientes |

Los detalles de campos, presupuestos y API son propuestas pendientes del acuerdo indicado en `CLAUDE.md`. No existe evidencia de que el equipo ya haya aprobado los cambios detallados.

## Hipótesis que aún requieren validación

- La ficha trazable reduce el trabajo del técnico en un plano real de mobiliario.
- El subconjunto geométrico P0 cubre la muestra elegida para la demo.
- Un fixture propio detecta los fallos básicos de medidas y cantidad, aunque no estime generalización.
- La revisión humana es lo bastante rápida y clara para aportar utilidad incluso con abstenciones.
- La asociación conjunto–detalle de Bench Vise es implementable dentro del tiempo restante si se prioriza P1.

No se ha medido ahorro de tiempo, precisión semántica, despiece correcto de muebles ni viabilidad de fabricación. Una evaluación posterior deberá publicar protocolo, denominadores, discrepancias y límites observados.

## Ajuste de alcance a la transcripción del usuario

Fuente primaria de requisitos: [transcripcion-contexto-poc.md](../transcripcion-contexto-poc.md). El paquete extraído cubría extracción y revisión técnica, pero no desarrollaba recuperación histórica, estimación económica ni una evaluación completa desde planos pobres. Se añaden T11–T13 y [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md) para cubrir esas necesidades.

Decisión documental: conservar el alcance técnico 0.1.0 como primer hito y exigir inferencia, histórico y estimación para la prueba de concepto completa. No se declara código implementado, dataset nuevo descargado ni contratos aprobados. La transcripción se conserva sin corregir sus errores de reconocimiento para no alterar la fuente.

## Investigación y admisión de nuevos datos

La [comparación actualizada de investigación y datasets](INVESTIGACION_Y_DATASETS.md) registra fuentes primarias, cifras, límites y acceso comprobado. El [protocolo de cuatro métodos](COMPARATIVA_METODOS.md) separa reglas, visión directa, herramientas e histórico. Son propuestas de evaluación; no resultados ejecutados.
