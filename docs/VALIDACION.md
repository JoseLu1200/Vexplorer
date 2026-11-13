# Validación determinista y reparación

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

Estado: especificación futura, propuesta de contrato `0.1.0` pendiente de acuerdo explícito A/B y aviso a C. Pydantic en `backend/app/contratos/` será la única autoridad del JSON; [CONTRATOS_DATOS.md](CONTRATOS_DATOS.md) es propuesta documental, no contrato implementado. El validador y sus pruebas son trabajo futuro. [DATASET.md](DATASET.md) distingue las auditorías de datos de las pruebas de producto aún no ejecutadas.

## Responsabilidad y orden

`validar_borrador` y `entregar_despiece` utilizarán exactamente el mismo servicio determinista previsto en `backend/app/validador/servicio.py` y `reglas.py`. La entrega solo podrá terminar con éxito después de validar y persistir idempotentemente. Una respuesta convincente del agente o un JSON bien formado no equivalen a interpretación correcta.

Se comprobarán esquema/revisión, referencias/procedencia, cobertura/identidad, dimensiones/agrupación y restricciones aplicables, en ese orden. El backend construirá números finales desde referencias validadas; el modelo no introducirá dimensiones resueltas paralelas.

Cada `ValidationCheck` tendrá `rule_id`, `result`, `severity`, `message`, `evidence_ids`, `candidate_ids` y `repairable_by_agent`. `result` será `pass`, `fail`, `unknown` o `not_applicable`: cumplimiento comprobado, contradicción, evidencia insuficiente o condición no aplicable. `severity` será `null` para `pass`/`not_applicable`, o `error`, `review`, `warning` para incidencias. Una identidad desconocida exige revisión.

`ValidationReport` contiene exactamente `schema_version`, `candidate_revision`, `outcome` y `checks`. `outcome=fail` si existe `fail/error`; en su ausencia, `unknown/review` o `fail/review` produce `needs_review`; sin bloqueos, `pass`. Las advertencias no bloquean. No existe un campo `issues` adicional ni razonamiento interno oculto. Las traducciones de UI no cambian enums.

## Tolerancias de comparación

Los valores iniciales configurables serán `abs_tol_mm=0.1` y `rel_tol=1e-6`. Son tolerancias de cómputo, no tolerancias de fabricación. Antes de comparar se verificarán unidades resueltas, tipo de magnitud, marco y eje compatibles. Para dos longitudes finitas `a` y `b`, en milímetros:

`close(a,b) ⇔ |a-b| ≤ max(abs_tol_mm, rel_tol × max(|a|,|b|))`.

La comparación no verifica valores provisionales ni resuelve conflictos mediante redondeo. La presentación podrá redondear sin modificar el ledger.

## Catálogo de reglas

Estos identificadores serán estables. Cambiar una regla versionará la configuración y su huella.

| Regla | Comprobación y resolución prevista |
|---|---|
| `R-001` | `schema_version`, estructura, tipos y enums admitidos. Un incumplimiento es `fail/error`; corregible por nueva Submission válida. |
| `R-002` | `candidate_revision` corresponde al ledger actual. Revisión obsoleta: `fail/error`; recargar evidencia, sin migrar IDs por parecido. |
| `R-003` | Cada ID existe, pertenece a la ejecución y tiene el tipo esperado. ID inventado o cruzado: `fail/error`. |
| `R-004` | Valores fuente y mediciones conservan integridad. Intento de mutación: `fail/error`; el agente no puede repararlo escribiendo un nuevo número. |
| `R-005` | Unidades y marcos necesarios están resueltos. Ausencia: `unknown/review`; no suponer mm. |
| `R-006` | Cada candidato aparece exactamente en una pieza o disposición; no hay IDs repetidos. Omisión o doble uso: `fail/error`. |
| `R-007` | Alternativas competidoras son exclusivas; un rechazo tiene hermano seleccionado y evidencia. Contradicción: `fail/error`; elección indeterminada: `unknown/review`. |
| `R-008` | `not_a_part` tiene justificación trazable; `needs_review` conserva razón y evidencia disponible. Exclusión injustificada: `fail/error`. |
| `R-009` | Dimensiones referidas están entre las opciones respaldadas de los candidatos, sin conflicto y con valor positivo. Referencia impropia o valor no positivo: `fail/error`; evidencia insuficiente: `unknown/review`. |
| `R-010` | Largo, ancho y espesor necesarios están disponibles. Un ausente permanece `null` y produce `unknown/review`, incluido el espesor. |
| `R-011` | Cantidad coincide con ocurrencias confirmadas distintas. Cifra inconsistente: `fail/error`; identidad ambigua requiere cantidad `null` y `unknown/review`. |
| `R-012` | Agrupación conserva dimensiones y características compatibles. Diferencia demostrada: `fail/error`; equivalencia no demostrada: `unknown/review`. |
| `R-013` | `source_contour_ids` y evidencia corresponden a candidatos y observaciones de la pieza; no atribuir contornos ajenos. Violación: `fail/error`. |
| `R-014` | `label_status=confirmed` procede de autorización del servidor. Autoafirmación del modelo: `fail/error`; una etiqueta `proposed` puede conservarse visiblemente. |
| `R-015` | Cadenas dimensionales generales: `not_applicable` en P0. P1 exige acordar primero un modelo estructurado de cadena, marco, eje, extremos, miembros, huecos y solapes. |
| `R-016` | Colisiones físicas: `not_applicable` en P0. Las cajas esquemáticas y solapes 2D no acreditan colocación ni colisión. |
| `R-017` | Derivación admitida, dependencias existentes, acíclicas y compatibles en magnitud/marco, y resultado recalculado coincidente. Incumplimiento: `fail/error`. |
| `R-018` | Cobertura positiva: cero candidatas soportadas produce `unknown/review`, `needs_review` y razón `no_supported_part_candidates`, nunca `completed`. No basta el cumplimiento vacuo de `R-006`. Ledger inválido: ejecución `failed`, sin construir abstención que lo oculte. |

La selección de una medición `conflict` no producirá una dimensión aceptada. Se reportará la contradicción y se conservarán sus alternativas para revisión. Una medición `provisional` sin corroboración suficiente no se promoverá por insistencia del agente. La política de completitud impedirá cerrar automáticamente dimensiones o identidades desconocidas.

## Restricciones geométricas con premisas explícitas

La distancia plana será `d=√((x₂−x₁)²+(y₂−y₁)²)`. Largo y ancho procederán de los ejes locales del rectángulo verificado. Una caja envolvente no demuestra rectangularidad; el validador comprobará el vínculo al resultado de extracción y sus evidencias.

En P1, tras acordar su representación estructurada, una cadena axial confirmada podría expresar:

`D_total = Σ d_i + Σ g_j − Σ o_k`,

donde `d_i` son tramos sobre el mismo eje, `g_j` huecos y `o_k` solapes conocidos. Deben estar fijados el inicio, final, orden, marco y correspondencia de cada tramo. No se sumarán las longitudes de todos los tableros para compararlas con el ancho del mueble: un lateral vertical y una balda horizontal no integran la misma cadena.

Ejemplo sintético P1, no comprobación P0, aplicable únicamente si está confirmado que una balda queda entre dos laterales y sin holguras: `W_exterior=t_izquierdo+W_balda+t_derecho`. Con `18+564+18=600 mm`, la ecuación puede pasar. Si se desconoce un espesor o existe holgura sin medir, su resultado será `unknown/review`. Si no existe evidencia de ese montaje, la ecuación será `not_applicable`. No se deducirá la relación desde el nombre «balda».

El volumen `V=L×W×T` podrá calcularse solo para una caja rectangular con tres dimensiones conocidas; no es volumen mecanizado ni prueba de manufacturabilidad. Con `T=null`, el volumen permanecerá desconocido. El volumen o la visualización nunca completarán el espesor.

Las proyecciones ortográficas se superponen normalmente. Un cruce 2D o una caja de presentación superpuesta no demuestra choque. Con colocación 3D fiable, el solape AABB sigue siendo solo fase amplia; confirmar choque requiere sólidos y criterio de contacto. P0 reportará `R-016=not_applicable`; las cajas esquemáticas no aportan evidencia física.

## Qué demuestra la auditoría del corpus mecánico

Se abrieron 14 DXF Orla; once declaran unidad desconocida y tres mm. El cotejo por handle confirma 370 `DIMENSION` en JSON, pero cuatro `ARC_DIMENSION` adicionales no están cubiertas allí. Hay 14 cotas angulares, que no son mm, y 50 sobrescrituras. Las verificaciones del ZIP y los sidecars no son pruebas aprobadas de `R-001` a `R-018` ni oráculos semánticos independientes. DWG solo se inspeccionó por header y STEP por texto, sin kernel.

El caso `drawing_1b796…:5319` separa medición geométrica aproximada `67`, `actual_measurement` y `raw_measurement≈44.6666666667`, factor `2/3` y texto `45`. El producto deberá preservar esas diferencias; ni considerar raw como geometría ni volver a escalarlo automáticamente. Cada comparación necesita una magnitud, unidad, marco y representación declarados. Los datos mecánicos no prueban despiece de muebles; la baseline P0 usa fixtures propios de mobiliario con BOM manual revisada.

Los 51 paquetes de conjuntos son PDF y no forman parte de la entrada actual. El piloto Bench Vise es P1: la BOM revisada tiene 12 referencias y 22 unidades, con cotas revisadas solo de Jaw Pad. STEP es referencia separada y oculta al agente en la evaluación 2D, no una fuente de respuestas añadida silenciosamente. Véase [DATASET.md](DATASET.md).

## Reparación, revisión y estado final

El harness entregará al modelo incidencias concretas con IDs y evidencia disponible. Podrá corregir estructura, referencias, agrupaciones o disposiciones usando el ledger existente y repetir validación. Los límites serán `max_model_calls=15`, incluyendo intentos y reintentos del proveedor, `max_tool_calls=30`, `max_validation_repairs=2` y `run_timeout_s=120` para la fase agente. El plazo será monotónico; cancelar detendrá nuevas llamadas. Los detalles operativos están en [HARNESS.md](HARNESS.md).

Un `unknown` causado por falta de evidencia debe pasar a revisión inmediatamente. No se gastarán dos reparaciones intentando adivinar espesores, unidades o identidad. Un error con evidencia resoluble permite reparación dentro del presupuesto. Una Submission inválida no se persiste como resultado válido ni se rescata conservando solo sus filas correctas. Si el ledger es válido, el servidor puede construir una nueva abstención con `pieces=[]` y una disposición `needs_review` por cada candidata válida, conservando el borrador rechazado para auditoría; la nueva Submission pasa por el mismo validador y persistencia. Un ledger inválido termina `failed`; la abstención no lo sanea. Fallos de infraestructura, plazo y cancelación usarán sus estados correspondientes.

Con cero candidatas soportadas, `R-018` fija `needs_review`/`no_supported_part_candidates`; un ledger vacío válido no justifica éxito. `completed` exigirá cobertura positiva y pasar las comprobaciones automáticas aplicables sin errores ni incógnitas obligatorias pendientes. Las etiquetas semánticas propuestas seguirán marcadas `proposed`; completar no es emitir un certificado de fabricación. `needs_review` conservará piezas parciales, dimensiones `null`, disposiciones e incidencias visibles. La revisión autenticada creará una revisión de resultado y revalidará; mantendrá el original y no sobrescribirá mediciones. Un cambio de unidades, fuente o configuración de vistas requiere otra ejecución.

Los ensayos previstos cubrirán conflictos de cotas, IDs falsos, revisiones obsoletas, inmutabilidad, exclusión de alternativas de una misma ocurrencia, cobertura positiva, unidades y solapes de proyección; las cadenas estructuradas se reservan a P1, además de finalización idempotente. Su definición está en [TEST_PLAN.md](TEST_PLAN.md) y [TDD.md](TDD.md). No se presentan aquí como pruebas ejecutadas ni aprobadas.

## Precisiones del ámbito P0

En R-011, «ocurrencias confirmadas» significa ocurrencias del **conjunto evaluado**, con evidencia de ese ámbito. Confirmar que tres vistas representan un diseño de pieza no demuestra cantidad de conjunto; un componente Orla aislado conserva ese campo desconocido. La cardinalidad de candidatas no constituye una BOM sin esa premisa.

La revisión humana P0 selecciona referencias y alternativas existentes y confirma etiquetas dentro de su autoridad. No añade asociaciones físicas nuevas al ledger. Cuando resolver una incidencia requiere esa asociación, el estado sigue en revisión hasta disponer de una entrada autenticada acordada A/B que regenere evidencias y fingerprint. La repetición de un run idéntico no se ofrece como resolución de la ambigüedad.

## Validación adicional de propuestas y presupuestos

En T11 separar «hipótesis coherente» de «pieza respaldada por evidencia». La primera puede mostrarse para revisión sin elevarse a hecho. Las confirmaciones humanas crean premisas nuevas con autor/fuente y revisión; el libro original no se sobrescribe. R-015 continúa pendiente de modelo estructurado: proponer una unión no equivale a validar su cadena dimensional.

T12 exige cálculos reproducibles, comparables permitidos, unidades/moneda/fecha compatibles, conceptos sin doble contabilización y factores identificados. Ausencia de tarifa, desglose o comparable deja el importe desconocido o el escenario explícitamente provisional. Separar validez aritmética, incertidumbre económica y aprobación humana. Ninguna de ellas convierte una propuesta en orden de compra o certificación de fabricación.

## Auditoría de referencia frente a validación del agente

La descarga de [PlankAssembly](PLANKASSEMBLY.md) pasó hash, CRC y comprobaciones de extracción. Eso no implica que el futuro agente haya recuperado piezas correctas. El evaluador debe excluir la envolvente global del recuento, conservar índices de asociaciones y distinguir normales ausentes de coordenadas inválidas.

Comprobar dimensiones del cuboide por código, pero no llamar a esas extensiones planos de fabricación. Revisar unidades tras proyección, identidad entre vistas y ambigüedad del caso. Una alternativa coherente puede diferir de la referencia reservada; documentar el criterio de correspondencia antes de puntuar. No hay validaciones de inferencia ejecutadas sobre este corpus.
