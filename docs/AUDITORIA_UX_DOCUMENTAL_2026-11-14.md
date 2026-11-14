# Auditoría UX documental — 14 de noviembre de 2026

## Alcance y precedencia

Se inventariaron y abrieron completos 94 Markdown propios de Vexplorer, excluidos `.git`, `node_modules` y vendor. La transcripción literal define el problema empresarial; el README y `VERIFICACION_TRANSCRIPCION_2026-11-14.md` describen el producto vigente; `MUEBLE_GENERAL`, `HISTORICO_REAL` y los modelos Pydantic concretan el comportamiento actual. Los contratos 0.1, planes iniciales y frases de «pendiente de implementar» son historia del diseño, no estado presente. Los cierres 0.4/0.5 siguen siendo autoridad de sus recorridos especializados, pero no sustituyen la ampliación general 0.6.

La referencia visual de `trace-pay` se consultó solo en su documentación frontend y tokens: consola sobria, tipografía Geist/mono para datos, lienzo gris-marfil, tinta de alto contraste, foco cobalto, estados cromáticos reservados y scroll de documento o panel deliberado. No se debe copiar su radio de shell de 20 px: el plan UX vigente de Vexplorer pide 10–12 px para shell, 6–8 px para controles y píldoras solo para estados/etiquetas.

## Intención de producto vigente

El recorrido principal es: plano pobre DXF/DWG/PDF → evidencia geométrica/visual → propuesta P1 → crítica separada → reparación P2 opcional → auto-revisión → BOM/planos/esquema provisionales → comparables → escenarios de coste y horas. La edición humana existe como corrección opcional y versionada, no como puerta obligatoria. El objetivo de cada pantalla es resolver la siguiente incertidumbre respaldada, no llenar todos los campos.

El plano 2D y su procedencia son la evidencia principal. El 3D, los embeddings y los costes son ayudas subordinadas: no añaden certeza geométrica, identidad de pieza, cantidad, equivalencia de fabricación ni aprobación comercial.

## Mapa de recorridos y aceptación

| Recorrido | Secuencia visible necesaria | Criterios de aceptación UX |
|---|---|---|
| General | Cargar DXF/DWG/PDF → preparar fuente → live o geometría → P1/crítica/P2 → derivados → histórico/escenarios | Actor de máquina, modelo y fase visibles; P1/P2 inmutables; checks `accepted/rejected/conflict/abstained`; hipótesis auto-revisadas siguen siendo hipótesis; edición humana ofrecida sin bloquear la salida provisional. |
| Mesa montada | Elegir baseline o programa live → ledger W/D/H → programa/componentes/premisas → láminas/3D/coste | Baseline rotulada catálogo, no inferencia; bindings `copy/add/subtract` explicables; programa, componentes y premisas tienen decisiones separadas; slots desconocidos y conflictos bloqueantes visibles; perfil limitado a tapa + 2 laterales o 4 patas. |
| Piezas separadas | Abrir vistas `PART` → asociar FRONT/TOP/SIDE → cantidad `QTY` → revisar roles/montaje → escena/biblioteca | Tres vistas no son tres piezas; cantidad procede de `QTY` o confirmación trazable; K2/K3 no revelan función; escena y posición de baldas se rotulan esquemáticas; sin asociación no se fuerza montaje. |
| PDF | Cargar → elegir página → confirmar escala opcional con motivo → crear documento hijo → propuesta visual | Sin escala: «Unidad sin resolver», sin mm; PDF ráster permite contexto visual, no medir píxeles; `DO NOT SCALE`/conflictos y procedencia padre/página permanecen visibles. |
| Histórico | Importar/listar → filtrar origen → comparar por atributos o embeddings → seleccionar comparables | Distinguir `actual`, `published`, `synthetic`; mostrar fuente y fecha; `cost_basis` separa `actual`, `quote`, `budget`; el score no es probabilidad ni equivalencia; sintéticos opt-in y desactivados por defecto. |
| Costes y horas | Elegir scopes → calcular conceptos compatibles → ver faltantes/exclusiones → exportar snapshot | Moneda, fecha, scopes de coste y horas separados; fijos una vez, variables por driver; horas no derivadas de euros; subtotal parcial no es total/precio; margen y exclusiones explícitos; escenario condicional no es cotización. |
| Traza | Abrir cajón → seguir secuencia/fases → detectar huecos/reconexión → exportar | Acciones, evidencia, resultado y telemetría segura; nunca razonamiento interno, prompt completo o secretos; secuencia monótona, duplicados descartables y huecos visibles; run/revisión/snapshot identificables. |
| Procedencia | Cabecera de documento/run → campo/pieza → artefacto → coste/histórico | Archivo/documento/página, modo, revisión, unidad, evidencia, estado y actor recuperables. No basta un badge global; cada cifra importante conserva origen y premisas. |
| Desconocidos/conflictos | Mostrar fuente aunque falte inferencia → explicar dato faltante → permitir corrección autorizada | `null` se presenta como «Desconocido», nunca cero, guion aislado o valor típico; `conflict` conserva ambas evidencias; ausencia de propuestas no oculta el plano; acciones imposibles quedan deshabilitadas con causa. |

## Nomenclatura obligatoria

La UI debe mantener separadas estas dos dimensiones:

- Estado factual: `observed/observado`, `derived/calculado`, `hypothesis/hipótesis`, `confirmed/confirmado por persona`, `unknown/desconocido`, `conflict/conflicto`.
- Estado de proceso: `unreviewed`, `auto_reviewed`, `human_reviewed`.

«Auto-revisado» no significa «confirmado». Un valor calculado tampoco es una confirmación humana. `verified` valida una comprobación documentada, no exactitud física ni fabricabilidad. «Completado» describe cobertura contractual, no certificado de fabricación. «Publicado» es una fuente externa, no dato empresarial ejecutado. «Presupuesto» no es coste real; «precio provisional» no es valor de mercado.

Las ocurrencias deben distinguirse como `physical_occurrence_ids` y `scenario_occurrence_ids`. Una cantidad hipotética auto-revisada solo crea ocurrencias provisionales. `furniture_quantity` significa muebles terminados del encargo y no suma piezas. Vistas, entidades, contornos, componentes y ocurrencias no son sinónimos.

## Diferencias entre documentos históricos y estado actual

| Histórico | Vigente |
|---|---|
| 0.1 proponía servicio, SSE y revisión humana futura. | Existe producto 0.6 con jobs durables, snapshots, general furniture, auto-crítica y despliegue privado; los nombres exactos vienen de Pydantic/API. |
| UX 0.2 centraba estantería y «Decisión técnica» humana. | Mueble general es el recorrido principal; la persona corrige opcionalmente después de la revisión automática. |
| Parts 0.4 parte de vistas separadas con etiquetas explícitas. | Sigue disponible como recorrido especializado; no debe usarse para explicar la inferencia general desde plano pobre. |
| Mesa 0.5 exige aceptar programa/premisas/componentes para materializar. | Sigue vigente para mesa; no se debe proyectar ese gate al recorrido general provisional. |
| Catálogos y comparables eran sintéticos. | Hay fuentes `published/budget` además de `actual` y `synthetic`; continúan sin ser ERP ni validación empresarial. |
| La revisión humana podía elevar resultado a `completed`. | La auto-revisión permite salida provisional sin humano, pero nunca promueve hipótesis a hecho. |
| SSE se describía como vivo. | La UI debe consumir el transporte realmente publicado y seguir mostrando historial, gaps y recuperación sin afirmar streaming si no existe. |

## Hallazgos de interfaz a comprobar

1. El marcado actual titula el panel `review` como «Decisión humana» y usa vacíos como «Confirma un montaje». En mueble general esto puede comunicar un gate obligatorio contrario al README vigente; el copy debe adaptarse por recorrido y ofrecer corrección opcional.
2. La leyenda visible usa «Confirmado». Debe especificar «Confirmado por persona» o mostrar actor/fuente para evitar confundirlo con auto-revisión.
3. El HTML base de `#history-provenance` contiene `actual` y `synthetic`, pero no `published`. Verificar que el JS siempre materializa `published`, que restauración lo conserva y que una fuente académica no aparece como «Datos reales verificados».
4. `document-provenance` parte de «Fuente pendiente»; ya existe un hallazgo previo donde permanece así al restaurar un run. La fuente cargada debe rehidratarse con documento/página/conversión.
5. La densidad no puede resolverse ocultando unidad, estado, fuente, premisa o exclusión. El detalle puede plegarse, pero el resumen decisional debe conservar esas señales.
6. En baja altura, móvil y zoom 200 %, deben alcanzarse últimas filas y acciones con rueda y teclado. Ningún `overflow:hidden` de shell puede convertir un panel alto en contenido inaccesible.
7. El 3D debe reaccionar al ancho real del contenedor y a ocultar/mostrar panel, sin perder selección; el arreglo con `ResizeObserver` documentado por el agente del visor requiere QA integrado.

## Semánticas que no se pueden simplificar

- No convertir ausencia de unidad en mm ni coordenadas fuente en medidas métricas.
- No sustituir espesor, cantidad, material, acabado, tarifa u horas ausentes por valores típicos.
- No contar vistas como cantidades ni escenas provisionales como piezas físicas.
- No mezclar propuestas incompatibles, monedas, scopes, revisiones o versiones de descriptor.
- No presentar embeddings/coseno como confianza, probabilidad o justificación económica.
- No presentar una caja 3D, envolvente rectangular o SVG derivado como geometría certificada.
- No llamar «real» a `published/budget`; mostrar origen y base juntos.
- No hacer que la falta de humano bloquee el resultado provisional general ni que la auto-revisión borre la posibilidad de corrección humana.
- No ocultar abstenciones, checks conflictivos, campos desconocidos o fallos de proveedor bajo un estado global exitoso.

## Criterio de cierre UX

La reparación queda documentalmente alineada cuando un usuario puede recorrer general, mesa, piezas, PDF, biblioteca, coste y traza; llegar a todas las acciones; distinguir hechos, cálculos, hipótesis y revisiones; recuperar fuente/unidad/revisión de cada cifra; entender por qué una acción no está disponible; y obtener una salida provisional honesta sin que una revisión automática, un comparable o una visualización se presente como confirmación industrial.
