# Organización del equipo

**Estado:** reparto propuesto para tres o cuatro personas. No se presupone quién integra el equipo. Las reglas de [CLAUDE.md](CLAUDE.md) son obligatorias: identidad explícita, archivo propio designado, alcance y reservas comprobadas antes de editar código. [team/README.md](team/README.md) y [team/_TEMPLATE.md](team/_TEMPLATE.md) preparan ese registro sin inventar integrantes.

## 1. Responsabilidad por flujo

| Persona | Propiedad principal | Entrega que recibe otra persona |
|---|---|---|
| A — geometría | Ingesta, unidades, bloques, cotas, vistas y candidatas | `EvidenceLedger` congelado y artefacto de plano seleccionable |
| B — harness | Contratos, adaptador de proveedor, herramientas, validación y persistencia | `Result`, `ValidationReport` y eventos de ejecución |
| C — interfaz | Carga, plano 2D, tabla, selección, traza, revisión, cajas y exportación | Recorrido visible completo y prueba E2E |
| D — datos y demo, si existe | Selección/etiquetado, controles independientes, contingencias, vídeo | Fixtures revisados, manifiesto y ensayo reproducible |

Con tres personas, A y B comparten etiquetado; C prepara el guion y B los modos de contingencia. La validación de un resultado requiere una segunda lectura de alguien distinto de quien escribió el extractor.

## 2. Acuerdo de la primera hora

Leer [CONTRATOS_DATOS](docs/CONTRATOS_DATOS.md) juntos. Congelar nombres, enums, dimensiones en mm, referencias y estados. El documento contiene una propuesta de `Submission`, no un acuerdo ya alcanzado. A y B deben aprobar explícitamente los campos y avisar a C; después se implementan los modelos Pydantic como única fuente y se generan sus esquemas JSON.

Decisiones imprescindibles:

1. El primer caso real de desarrollo y qué información respalda.
2. Un fixture positivo propio con dimensiones y cantidad conocidas.
3. Qué elemento es observación, objeto o pieza; cómo se representan alternativas.
4. Cómo expone A las entidades y contornos para que C los resalte.
5. Qué campos puede proponer el LLM y cuáles solo puede resolver el backend.
6. Qué se enseña cuando falta espesor o no existe evidencia de despiece.

El nuevo corpus contiene 14 piezas mecánicas DXF; los conjuntos están en PDF. Seleccionar un caso CAD para cotas y un fixture propio de paneles para despiece. El piloto PDF es P1, sujeto a los contratos de página/región y referencias del conjunto. No poner el conversor DWG en la ruta crítica. Si ODA está instalado, comprobar un par DXF/DWG conocido; si no, la implementación P0 sigue con DXF. No utilizar el reservado para elegir la demo.

## 3. Dependencias de integración

| Entregable | Responsable | Depende de | Consumidores |
|---|---|---|---|
| Contrato y ejemplos aceptados | B con A/C | Lectura de documentos y datos | Todo el equipo |
| Ingesta y plano normalizado | A | Contrato | C y extracción |
| Evidencias y candidatas | A | Ingesta | B y C |
| Validador | B con A | Libro y oráculo | Harness, revisión, exportación |
| HTTP, almacenamiento y SSE | B | Contrato | C |
| Plano y hover | C | Entidades y contornos | Demo |
| Agente acotado | B | Herramientas y validador | Demo |
| Resultado exportable | B/C | Validador y persistencia | Usuario final |

La interfaz puede empezar contra los ejemplos sintéticos etiquetados como tales. No presentar esa integración como lectura real hasta conectar la ingesta y comprobar la correspondencia fuente→resaltado.

## 4. Secuencia orientativa

Las horas son una propuesta de planificación, no una estimación validada del equipo.

| Ventana | Hito | Recorte si se retrasa |
|---|---|---|
| H0–H1 | Contrato, selección y primer DXF inspeccionado | DXF directo; mantener ODA fuera del camino |
| H1–H4 | Lectura, unidades, cotas y plano seleccionable | Priorizar cotas y referencias; revisión manual de vistas |
| H4–H7 | Candidatas, identidad y validación | Reducir tipos geométricos admitidos con aviso explícito |
| H7–H10 | Herramientas, API, tabla y ciclo agéntico | Agente con menos herramientas; conservar geometría pura |
| H10–H13 | Revisiones, exportación y pruebas de integración | CSV/JSON; PDF para después |
| H13–H16 | Casos de error, ensayo y documentación operativa | Congelar funcionalidades; corregir recorrido principal |

Si queda menos tiempo, el orden de [PLAN](PLAN.md) sigue siendo válido: entregar un recorrido parcial honesto antes que ampliar reconocimiento sin validación.

## 5. Trabajo paralelo y cambios de contrato

Usar ramas cortas por tarea; integrar al terminar un entregable que pasa sus pruebas. B coordina la integración en `backend/app/contratos/modelos.py`, con acuerdo explícito A/B y aviso C; la API sigue el mismo contrato. El esquema se genera, no se edita como autoridad independiente. Antes de renombrar un campo, actualizar productor, consumidor, ejemplo y prueba de contrato en el mismo cambio.

Toda propuesta de cambio debe indicar motivo, consumidores afectados y migración. Este borrador 0.1.0 sigue pendiente de aceptación; las revisiones documentales no conceden permiso para cambiar código compartido. Una vez aprobado, tras acordarlo y usarlo en datos persistidos, incrementar versión cuando cambie compatibilidad.

Una entrega entre compañeros incluye: rutas cambiadas, interfaz, fixture usado, comandos ejecutados y su resultado, limitaciones observadas y siguiente dependencia desbloqueada. «Funciona en mi máquina» no es evidencia suficiente.

## 6. Archivo personal y reservas

Cada persona mantiene su propio `team/<nombre>.md` al terminar un bloque, no solo al cerrar sesión. El archivo enumera rutas reservadas, tarea, estado, decisiones, bloqueos y dependencias. Una sesión debe leer los archivos del resto para detectar solapes, sin editarlos. Si falta identidad o designación explícita, se aplica el procedimiento de `CLAUDE.md` antes de tocar código.

Una asignación sugerida en esta tabla no equivale a reserva ni autorización. No crear carpetas vacías por anticipado; la estructura de aplicación aparece cuando se implementa cada tarea. La documentación solicitada puede prepararse sin atribuir una identidad a su solicitante.

## 7. Definición de terminado

- El comportamiento acordado tiene una prueba significativa que se vio fallar antes de implementarlo.
- El test específico y la suite afectada pasan; el informe distingue pruebas ejecutadas y pendientes.
- Los errores y desconocidos conservan sus estados.
- No se fabricaron dimensiones, cantidades, permisos o evidencias.
- La interfaz sigue el contrato y muestra procedencia.
- Otro compañero pudo reproducir el caso.
- La documentación operativa refleja la limitación que quede.

No exigir pruebas nuevas para corregir una errata en Markdown. Reservar TDD para el comportamiento del producto y las fronteras que pueden fallar.

## 8. Orden de decisiones cuando falta tiempo

Prioridad: unidades correctas → trazabilidad → identidad/cantidad → medidas → revisión → exportación → semántica más rica → vista 3D más elaborada. MCP y más proveedores quedan al final. Un cambio de etiqueta nunca autoriza cambiar una medida.

El vídeo y cualquier envío del proyecto son trabajo posterior del equipo. Este paquete no crea repositorio externo ni realiza envíos.

## Responsabilidades para completar el objetivo de negocio

El orden anterior es el del hito técnico. Antes de pulir el visor 3D, priorizar T11–T13: corpus de mobiliario emparejado, propuestas desde planos pobres, revisión, comparables y estimación. A y D (si existe) preparan entradas/referencias y anotaciones; A/B diseñan inferencia y contratos; B coordina histórico y cálculo determinista; C presenta diferencias, supuestos y ficha de compras. Con tres personas, A/B comparten datos y C coordina el ensayo. Son responsabilidades propuestas, no identidades ni reservas.

Seleccionar desde el inicio mobiliario con referencia completa e histórico económico utilizable. Registrar su ausencia como límite de validación. Revisar con el técnico los criterios de [CASO_DE_USO_Y_EVALUACION](docs/CASO_DE_USO_Y_EVALUACION.md) antes de evaluar; no fijar tolerancias después de ver el resultado. T10 no cierra por sí sola el objetivo completo.
