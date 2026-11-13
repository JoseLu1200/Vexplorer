# Semántica, asociaciones y cantidades

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

Estado: especificación futura y propuesta `schema_version=0.1.0`, pendiente de acuerdo A/B y aviso a C. Pydantic en `backend/app/contratos/` será la única autoridad futura del JSON. Se interpreta evidencia geométrica ya calculada; no se entrega aplicación ejecutable ni se han pasado pruebas de producto. El corpus mecánico auxiliar, 14 componentes CAD y 51 paquetes de conjuntos PDF, está descrito en [DATASET.md](DATASET.md); la referencia de mobiliario descargada está en [PLANKASSEMBLY](PLANKASSEMBLY.md). Véanse [CONTRATOS_DATOS.md](CONTRATOS_DATOS.md), [GEOMETRIA_Y_PLANOS.md](GEOMETRIA_Y_PLANOS.md) y [VALIDACION.md](VALIDACION.md).

## Separar observación, hipótesis y ocurrencia

Una entidad es una primitiva CAD. Un contorno es una construcción geométrica trazable. Una observación es una representación en una vista. Un candidato propone una ocurrencia física, y una pieza de la tabla puede agrupar varias ocurrencias confirmadas compatibles. Así se evita contar vistas como tableros.

`PartCandidate` mantendrá `observation_ids`, `hypothesis_set_id`, `identity_status`, `frame_id`, `identity_evidence_ids`, `dimension_options` y `placement` conforme a la propuesta de esquema. `identity_status=confirmed` significa que la identidad física tiene soporte; no que un rol propuesto por el modelo esté confirmado. Las opciones de dimensiones son referencias a mediciones existentes. Una alternativa comparte `hypothesis_set_id` con sus competidoras y no se suma a ellas.

En P0, un conjunto de hipótesis contiene alternativas de interpretación de **una misma ocurrencia física**. No representa alternativas de cardinalidad «una pieza frente a tres piezas». Ejemplo sintético: observaciones `800×400`, `800×18` y `400×18` pueden sustentar distintas asociaciones de ejes para una ocurrencia; elegir una exige evidencia y coherencia. Si la duda es si las vistas pertenecen a una o varias ocurrencias, se conserva `needs_review` y se regenera el ledger tras resolver la identidad. No se fuerza esa duda dentro de `hypothesis_set_id` ni se introduce una cantidad inventada.

## Uso semántico del corpus mecánico auxiliar

Los 14 casos Orla son soportes, placas, ejes, casquillos y otras piezas mecánicas aisladas. Sus distintas vistas no son distintas ocurrencias. Sirven para extracción DXF lineal/rectangular seleccionada, procedencia, cotas y abstención; no demuestran cantidades de paneles o roles de mobiliario. Los 51 paquetes de conjuntos son PDF y quedan fuera de la entrada P0. Bench Vise se propone como piloto PDF P1 con BOM de 12 referencias y 22 unidades y dimensiones revisadas solo de Jaw Pad; requiere evidencia por página/región y acuerdo de adaptación, sin introducir PDF ahora.

El despiece P0 de mobiliario se evaluará con fixtures propios de paneles y BOM manual revisada. STEP y sidecars que revelen la respuesta permanecerán ocultos al agente en la evaluación 2D. No interpretar una envolvente STEP como largo/ancho/espesor de carpintería. [DATASET.md](DATASET.md) separa entrada, referencias derivadas y oráculos revisados.

## Evidencia y mediciones

Cada `Evidence` tiene `id`, `kind`, `source_entity_ids` y `description`. Debe permitir volver a las entidades resaltadas en el visor 2D, incluida la ocurrencia de bloque. El texto del dibujo es contenido no confiable: «ignora las reglas» seguirá siendo texto CAD y nunca alterará las instrucciones del harness. Las descripciones distinguirán una observación («rótulo próximo: lateral») de una conclusión («se propone lateral»).

Para las longitudes resueltas, cada `Measurement` conserva `id`, `kind`, `value_mm`, `origin`, `status`, `frame_id`, `evidence_ids`, `dependency_ids` y `derivation`. Las 14 cotas angulares del corpus requieren conservar tipo y grados fuera de `value_mm`; los once DXF unitless no autorizan una conversión por defecto. Los valores de longitud serán finitos y no negativos; una dimensión de pieza deberá ser estrictamente positiva. `origin` será `geometry`, `annotation`, `derived` o `user_confirmed`; `status` será `verified`, `provisional` o `conflict`. La evidencia no será vacía. `derivation` será `null` salvo para derivadas; estas usarán `operation`, `operand_ids` y `constant`. `sum` suma operandos, `difference` resta exactamente dos y `multiply_constant` multiplica un operando por una constante finita; en las otras operaciones, `constant=null`. Las dependencias serán acíclicas y coherentes con `dependency_ids`. No se evaluará código del modelo.

El ledger será inmutable. Corregir una asociación significa seleccionar otra referencia justificada, conservar el conflicto y producir una nueva revisión de resultado; no editar el valor de una medición. Cambiar fuente, unidades o configuración de vistas exige nueva ejecución/revisión de candidatos. La revisión humana no inventará mediciones de origen CAD. El estado `user_confirmed` como origen no permite que el LLM se atribuya confirmación humana.

Un espesor sin evidencia permanecerá `null`. No se deducirá `18 mm` de costumbre comercial, del nombre de una capa o del grosor de línea. Una nota explícita y asociada podrá generar una opción de medición de origen `annotation`; si contradice la geometría se conservará el conflicto.

## Extracción de características y asociaciones

Los módulos futuros `backend/app/agente/semantica/caracteristicas.py`, `similitud.py` y `relaciones.py` prepararán datos para herramientas. El backend calculará dimensiones observadas, relación de aspecto, orientación, vecindad, rótulos, capas, inserciones y características soportadas. No se enviará todo el DXF como texto al modelo.

La asociación de vistas seguirá tres pasos. Primero, producirá pares posibles por dimensiones compatibles en un eje físico compartido y por región de vistas. Segundo, añadirá evidencia de identidad: identificadores explícitos, marcas de pieza, correspondencia de detalle o confirmación de configuración. Tercero, comprobará contradicciones de ejes, espesores y características. Si faltan pruebas de identidad, la puntuación solo ordenará sugerencias; no convertirá semejanza en certeza.

Las cotas aportarán dimensiones, sin demostrar relaciones físicas. El contacto 2D puede pertenecer a planos distintos. Un círculo podrá representar característica, anotación o detalle; se conservará su procedencia sin inferir profundidad de taladro.

Las relaciones entre piezas —por ejemplo un estante entre dos laterales— necesitarán evidencia de disposición y eje. El rol `shelf` no autoriza por sí solo a restar espesores al ancho total. Una cadena dimensional general requeriría extremos, eje, miembros, huecos y solapes estructurados; queda en P1 hasta acordar ese modelo. En P0 no se infiere montaje a partir del rol y `R-015=not_applicable`.

## Papel del agente nativo

El primer adaptador previsto será tool use nativo de Claude, con ID de modelo configurable. El modelo propondrá `name`, `role`, agrupaciones y referencias; no tendrá shell, red libre ni permiso de cambiar geometría. No se requiere LangChain. El ciclo y los presupuestos están en [HARNESS.md](HARNESS.md).

| Herramienta | Utilidad semántica |
|---|---|
| `inspeccionar_candidata` | Consultar observaciones, opciones de dimensión y estado de identidad. |
| `obtener_evidencias` | Leer procedencia y contexto de evidencia existente. |
| `comparar_candidatas` | Comparar medidas y características calculadas, con contradicciones explícitas. |
| `visualizar_vista` | Obtener una vista identificada y trazable para inspección. |
| `validar_borrador` | Contrastar una `Submission` con reglas deterministas. |
| `entregar_despiece` | Presentar la misma estructura para validar y persistir terminalmente. |

Los roles permitidos serán `side_panel`, `shelf`, `top_panel`, `base_panel`, `back_panel`, `door`, `divider` y `unknown`. `label_status=proposed` identifica una propuesta del modelo; `confirmed` requiere autorización del servidor basada en confirmación humana o fuente admisible. `unknown` es una salida válida y visible; una placa mecánica no se convierte en `back_panel` por parecido. El nombre seguirá `proposed` cuando lo sugiera el modelo. Un nombre no confirma dimensiones. Ampliar roles a mecánica requiere acuerdo A/B y aviso a C, no una adaptación silenciosa.

## Agrupar piezas y calcular cantidad

Cada `Piece` propuesta llevará `candidate_ids` únicos no vacíos, `quantity`, `dimension_refs` y `source_contour_ids` únicos no vacíos, además de su identidad y etiqueta canónicas. Las referencias de dimensiones deberán pertenecer a opciones justificadas por los candidatos agrupados; no basta con que exista en el ledger una medición con el número deseado.

Para candidatos distintos de identidad confirmada y compatibilidad comprobada, el backend comprobará:

`quantity = número de candidate_ids distintos confirmados como ocurrencias del conjunto evaluado de esa pieza`.

Si alguno tiene identidad ambigua, la cantidad será `null` y habrá revisión. No se aceptarán multiplicadores escritos por el modelo, conteos de entidades, número de vistas ni una cifra extraída de una nota sin asociarla a ocurrencias. Dos laterales iguales pueden agruparse como cantidad dos si están demostradas ambas ocurrencias; tres observaciones de uno mantienen cantidad uno.

Agrupar exige dimensiones, orientación física y características compatibles. La igualdad de caja rectangular no demuestra intercambiabilidad. Variantes espejadas, taladradas o con mecanizados distintos se mantendrán separadas. Si falta información para esa decisión, la agrupación requerirá revisión; no se certificará corte o fabricación.

## Cobertura, alternativas y revisión

Cada candidato de la revisión actual aparecerá exactamente en una pieza o en una `Disposition`. Los estados permitidos de disposición son `rejected_alternative`, `not_a_part` y `needs_review`, con `reason` y `evidence_ids`. Rechazar una alternativa exige un hermano elegido y evidencia; excluir una anotación como `not_a_part` exige evidencia. Un candidato no puede aparecer en dos filas ni desaparecer porque complique el resultado.

La cobertura vacía no acredita extracción: con cero candidatas soportadas, `R-018` exige `needs_review` y razón `no_supported_part_candidates`, nunca `completed`. Una abstención del servidor solo puede construir `pieces=[]` y una disposición `needs_review` por cada candidata válida del ledger, usando el mismo validador y persistencia. No rescata filas inválidas de una entrega rechazada. Si el ledger es inválido, la ejecución termina `failed` y no se construye abstención. Resolver identidad o cardinalidad exige regenerar el ledger y conservar revisión previa.

La UI mostrará dimensiones del backend, estados por campo y evidencia: [API_Y_EVENTOS.md](API_Y_EVENTOS.md). Las cajas serán esquemáticas, sin aportar montaje ni espesor inexistente. Los casos futuros de [TEST_PLAN.md](TEST_PLAN.md) cubrirán vistas múltiples, hipótesis exclusivas, espejados y espesores ausentes; no se han ejecutado.

## Ámbito de cantidad y límites de revisión P0

Identificar un diseño de pieza o asociar sus vistas no confirma cuántas ocurrencias tiene en un conjunto. La cantidad cuenta únicamente candidatas distintas respaldadas como ocurrencias del conjunto evaluado. Un DXF Orla de pieza aislada no aporta por sí solo una BOM con cantidad 1: conservar cantidad de conjunto desconocida y revisión, o una disposición, conforme al contrato.

La UI P0 revisa referencias, etiquetas y alternativas que ya están respaldadas en el ledger. No existe aún una entrada acordada para confirmar nuevas asociaciones físicas o descomposiciones: se conservan en `needs_review`. Un futuro mecanismo autenticado deberá registrar esa evidencia, afectar al fingerprint y regenerar el ledger, con acuerdo A/B y aviso C. Repetir el mismo archivo/configuración determinista no resuelve la identidad por sí solo.

## Descomposición e histórico más allá del contrato técnico

T11 debe representar alternativas de componentes y secciones del mueble completo, incluyendo una pieza frente a varias, fuera de los grupos 0.1.0 limitados a una ocurrencia. Estas propuestas se vinculan a regiones y observaciones, conservan supuestos y se someten a revisión; no se publican como piezas medidas por carecer de contorno propio. Se mantiene la prohibición de sumar alternativas incompatibles o inferir cantidades contando vistas.

La similitud entre candidatas del mismo plano no satisface la búsqueda histórica de la transcripción. T12 compara muebles de proyectos distintos por dimensiones, materiales, acabados y contenido semántico permitido. Contrastar baseline de atributos con embeddings; devolver diferencias verificables y campos ausentes, no solo score. El parecido sugiere comparables, pero no demuestra igual construcción, precio o tiempo. El ajuste económico corresponde al motor determinista y conserva sus premisas.

## Semántica de la referencia de mobiliario

En [PlankAssembly](PLANKASSEMBLY.md), la envolvente inicial no cuenta como pieza. Las filas posteriores representan ocurrencias de tableros en el modelo de referencia; varias proyecciones no multiplican esa cantidad. Igualdad de dimensiones no demuestra igualdad de material, mecanizado o función. Los nombres «balda», «puerta» o «lateral» requieren etiquetado o hipótesis explícita.

Las asociaciones privadas ayudan a puntuar reconstrucción, pero no prueban por sí solas el tipo de unión, herraje ni orden real de montaje. Algunos JSON no contienen normales; cualquier interpretación de dirección debe registrar su origen. Una entrada pobre puede admitir varias descomposiciones compatibles: comparar con la referencia sin tratarla como única solución físicamente posible.
