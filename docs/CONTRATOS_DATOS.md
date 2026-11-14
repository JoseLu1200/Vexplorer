# Contratos de datos — Vexplorer 0.1.0

> Estado documental (2026-11-14): este archivo conserva requisitos y checkpoints históricos; las frases sobre ausencia de aplicación o contratos pendientes no describen el estado vigente. Consulta [README](../README.md) y la auditoría completa. Las reglas de coordinación y arquitectura siguen aplicándose.

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

**Estado: propuesta 0.1.0 pendiente de acuerdo explícito A/B y aviso a C.** No existe backend implementado en este paquete. [CLAUDE.md](../CLAUDE.md) mantiene la autoridad de trabajo; esta especificación no acredita que el equipo haya aprobado estos campos. Las reglas semánticas viven en [VALIDACION.md](VALIDACION.md); los sobres HTTP/SSE, en [API_Y_EVENTOS.md](API_Y_EVENTOS.md).

## 1. Autoridad y versiones

Los **modelos Pydantic de `backend/app/contratos/modelos.py` serán la única fuente de verdad**. Tras el acuerdo A/B se implementarán allí campos, tipos, validadores y política `extra="forbid"`. Los JSON Schema de API y herramientas se generarán desde esos modelos; no se editarán como un segundo contrato independiente. Pydantic documenta la generación mediante [`model_json_schema()`](https://docs.pydantic.dev/latest/concepts/json_schema/).

La exportación de esquema podrá adaptarse al subconjunto del proveedor sin relajar la validación local. Una respuesta que supera el esquema del proveedor debe pasar Pydantic y las reglas deterministas del servidor. Este paquete solo aporta Markdown y ejemplos documentales; no contiene esos modelos ni un esquema ejecutable ya aprobado.

`schema_version="0.1.0"` aparece en mensajes canónicos. `candidate_revision` identifica el libro de evidencias congelado. Un cambio de entrada, conversor, configuración geométrica o versión del extractor invalida esa revisión. `result_revision` empieza en 1 y aumenta tras cada revisión humana. Los IDs no se prometen estables entre modificaciones arbitrarias del CAD.

Fuente de verdad: original y manifiesto → entidades normalizadas → evidencias y mediciones → candidatas → propuesta → validación → resultado. El agente no sustituye mediciones por nuevos números.

## 2. Inventario de tipos

| Tipo | Campos principales y responsabilidad |
|---|---|
| `SourceDocument` | Hash original y normalizado, formato, unidad original/efectiva, origen de la unidad y conversión |
| `SourceEntity` | ID, layout, handle, ruta de INSERT y transformación |
| `View` | Etiqueta de vista, estado de orientación, proyección y marco |
| `Contour` | Entidades de origen, vista y puntos métricos cuando existen unidades resueltas |
| `Evidence` | Hecho o asociación y referencias a entidades |
| `Measurement` | Valor en mm, origen, estado, marco y dependencias |
| `Observation` | Un contorno o conjunto de contornos observado en una vista |
| `PartCandidate` | Hipótesis de una ocurrencia física y sus observaciones |
| `EvidenceLedger` | Libro completo congelado, con marca `synthetic` |
| `Submission` | Propuesta estricta para validar y entregar |
| `ValidationReport` | Resultado de todas las comprobaciones aplicadas |
| `Result` | Piezas resueltas por el servidor, estados y revisión |
| `RunConfig` | Configuración permitida al cliente, sin permisos ni presupuestos libres |
| `DrawingPreview` | Geometría de presentación segura y mapeo de IDs al ledger |

## 3. Entidades, unidades y coordenadas

Una entidad expandida se identifica por hash del documento, layout, handle y ruta de inserciones. Un handle de definición de bloque no basta para distinguir sus apariciones. La transformación `source_to_document_transform` contiene 16 números, matriz afín 4×4 en orden por filas aplicada a vectores columna. Lleva coordenadas locales al marco del documento; la conversión de unidad del documento se aplica una vez después. Conservar la cadena original en el artefacto de ingesta para auditarla.

La unidad efectiva es `mm|cm|m|in|null`. `unit_scale_to_mm` es positiva o `null`; 1 m equivale a 1000 mm, 1 in a 25,4 mm. Si se desconoce la unidad, no crear `points_mm` ni mediciones métricas fingidas: devolver lectura parcial y `needs_review`. El original permanece disponible para una previsualización de coordenadas sin escala métrica afirmada.

`Contour.points_mm` usa el marco 2D de su vista; los marcos de vistas diferentes no son directamente comparables. Los puntos no repiten obligatoriamente el primero al cerrar; `closed` expresa cierre. El rango rectangular, orientación y planitud requieren comprobación geométrica independiente.

`SourceDocument.normalized_sha256` coincide con el original solo si los bytes no cambian. Para DWG convertido se guarda el hash del DXF resultante. El handle de ese DXF no se presenta como handle nativo DWG salvo que exista un mapeo comprobado.

## 4. Evidencias y mediciones

`Evidence.kind`: `geometry`, `dimension_annotation`, `metadata`, `view_association`, `user_confirmation`. Un texto de capa o nombre de archivo puede aportar contexto; su presencia no prueba una dimensión ni una clase. En evaluación ciega se ocultan metadatos que revelen la respuesta.

`Measurement` contiene:

| Campo | Regla |
|---|---|
| `id` | Único en el libro |
| `kind` | `length|width|thickness|diameter|offset|overall` |
| `value_mm` | Número finito no negativo; una dimensión de pieza debe ser estrictamente positiva |
| `origin` | `geometry|annotation|derived|user_confirmed` |
| `status` | `verified|provisional|conflict` |
| `frame_id` | Marco geométrico explícito; puede ser un marco local de candidata |
| `evidence_ids` | No vacío; referencias existentes |
| `dependency_ids` | Mediciones de las que depende el cálculo |
| `derivation` | `null` o operación determinista admitida |

`verified` describe una comprobación documentada del dato, no la exactitud física del objeto ni su aptitud para fabricación. Guardar en la evidencia y artefactos de extracción valor geométrico, valor almacenado, texto visible, tipo y factores aplicados. En Orla esas magnitudes pueden diferir; [DATASET.md](DATASET.md) recoge el ejemplo de handle `5319`.

Este modelo `Measurement.value_mm` solo admite magnitudes **lineales**. Una cota angular queda inventariada en la fuente con su unidad angular y fuera de `dimension_options`; nunca se fuerza a milímetros. El soporte tipado de ángulos requiere una ampliación acordada. `thickness` solo representa espesor cuando el contexto lo demuestra: el diámetro de un eje o la altura de una vista no lo sustituyen.

Derivaciones admitidas: `sum` con uno o más operandos; `difference` con exactamente dos, en ese orden; `multiply_constant` con un operando y constante finita. La constante es `null` en las otras operaciones. `dependency_ids` coincide con los operandos únicos; el grafo es acíclico. No evaluar expresiones Python ni código enviado por el modelo. Mantener precisión interna; redondear solo al presentar.

Una anotación incompatible con la geometría produce conflicto conservando ambas evidencias. Resolverlo exige una nueva evidencia autorizada; no reescribir una de las cifras para hacer pasar el test.

## 5. Candidata, observación y cantidad

`Observation` es una aparición dibujada en una vista. `PartCandidate` reúne observaciones que podrían describir una misma ocurrencia física. **Tres vistas de una pieza pueden producir una sola candidata.**

Campos adicionales de candidata:

- `entity_level`: `object|part|unknown`. Un sofá completo es objeto; un tablero identificado puede ser pieza.
- `identity_status`: `confirmed|ambiguous`.
- `identity_evidence_ids`: evidencias de la asociación entre vistas o de la ocurrencia física.
- `hypothesis_set_id`: alternativas excluyentes de interpretación de **una misma ocurrencia**, o `null`. P0 no expresa una alternativa de una pieza frente a varias piezas; requiere revisión y regeneración del ledger.
- `frame_id`: marco local para medidas.
- `dimension_options`: listas de referencias posibles para `length`, `width`, `thickness`; una lista vacía conserva lo desconocido.
- `placement`: `null` o transformación `schematic|assembled`. El modo esquemático no prueba posición montada.

La altura general de un objeto no es un espesor. Si el corpus solo permite medir la envolvente de un mueble, conservar esas cotas como `Measurement.kind=overall` y mostrar la lectura del plano; no construir piezas ficticias para llenar la tabla.

## 6. La herramienta final recibe referencias

`validar_borrador` y `entregar_despiece` reciben el mismo `Submission`:

```json
{
  "schema_version": "0.1.0",
  "candidate_revision": "rev-synthetic-panel-001",
  "pieces": [
    {
      "id": "piece-001",
      "name": "Panel rectangular",
      "entity_level": "part",
      "role": "unknown",
      "label_status": "unknown",
      "candidate_ids": ["cand-panel-001"],
      "quantity": 1,
      "dimension_refs": {
        "length": "m-length",
        "width": "m-width",
        "thickness": "m-thickness"
      },
      "source_contour_ids": ["cont-front", "cont-top", "cont-side"]
    }
  ],
  "dispositions": []
}
```

Es un **ejemplo documental sintético**. El libro completo y la propuesta están en [EJEMPLOS_CONTRATO.md](EJEMPLOS_CONTRATO.md): tres vistas describen un panel de 600×400×18 mm. Los hashes de ceros son marcadores, no hashes de un CAD real. No se ha generado ni leído ese DXF en esta entrega.

Roles de mobiliario propuestos: `side_panel|shelf|top_panel|base_panel|back_panel|door|divider|unknown`. `label_status`: `proposed|confirmed|unknown`. Solo un actor autorizado o una evidencia confirmada por el servidor puede utilizar `confirmed`; escribir esa palabra en una llamada LLM no confirma nada.

El nombre puede describir una pieza mecánica, pero no se le asigna un rol de mobiliario por semejanza: conservar `role=unknown`. Las tres dimensiones de este MVP describen paneles; una envolvente de una pieza mecánica no constituye automáticamente un despiece de fabricación. Ampliar la ontología requiere acuerdo A/B.

La cantidad solicitada se comprueba contra candidatas físicas distintas y confirmadas en el ámbito del conjunto. Identidad ambigua implica `quantity=null` y revisión. Un archivo de pieza aislada no demuestra cuántas unidades contiene un conjunto; el número de archivos o de sólidos no rellena ese dato. Si se agrupan candidatas, validar que todas respaldan las mismas dimensiones y las características necesarias; no basta comparar sus cajas.

Cada candidata aparece exactamente una vez: en una pieza o en `dispositions`. Las disposiciones son `rejected_alternative`, `not_a_part` o `needs_review`, con motivo y evidencias. Un objeto completo conserva `needs_review` para despiece; no se declara basura ni se omite del informe. Rechazar una alternativa requiere justificar qué hipótesis la sustituye.

Los números `largo/ancho/grosor` que pidió el equipo están en la salida resuelta del backend, no bajo autoridad de la propuesta LLM. Una referencia `null` se resuelve a valor `null` y estado `missing`.

## 7. Validación y resultado

`ValidationReport` tiene `schema_version`, `candidate_revision`, `outcome` y `checks`. Cada comprobación tiene `rule_id`, `result`, `severity`, `message`, `evidence_ids`, `candidate_ids`, `repairable_by_agent`.

| Comprobación | Consecuencia |
|---|---|
| `pass` o `not_applicable` | `severity=null` |
| `fail` con `error` | `outcome=fail` |
| `unknown` o `fail` con `review` | `outcome=needs_review` si no hay error |
| Aviso sin bloqueo | Puede conservar `outcome=pass` |

`Result.pieces` contiene `ResolvedPiece`: propuesta validada más `dimensions_mm`, `evidence_ids` y `field_states`. El backend rellena los valores mediante referencias, no mediante texto del agente. `Result.state` es `completed|needs_review`; un run fallido puede tener artefactos parciales sin presentarlos como resultado completo.

Una entrega `completed` exige al menos una pieza respaldada y ninguna incógnita obligatoria. Con ledger íntegro pero sin propuesta aceptable, el servidor puede construir una abstención: `pieces=[]` y una disposición `needs_review` por candidata, validarla y persistir revisión 1. Con cero candidatas las listas quedan vacías y R-018 registra `unknown/review`, motivo `no_supported_part_candidates`; no hay éxito por vacío. Un ledger con referencias rotas produce `failed/invalid_evidence_ledger`, sin inventar evidencia. Véase [HARNESS](HARNESS.md).

No confundir `ValidationCheck.result`, `ValidationReport.outcome`, `Run.state` y `Result.state`. Una revisión humana cambia la revisión del resultado, no el final histórico de la ejecución.

## 8. Configuración del run y fronteras HTTP

`RunConfig` admite exactamente:

```json
{
  "unit_override": null,
  "unit_override_reason": null,
  "metadata_mode": "blind",
  "view_assignments": []
}
```

Un override exige motivo y actor registrado. `metadata_mode=assisted` permite contexto del catálogo; `blind` oculta nombres, títulos, categorías y pistas equivalentes durante evaluación. Las asignaciones de vistas contienen `view_id`, `label` y `evidence_ids`, y deben referirse al documento del run. Estas decisiones entran en el fingerprint.

Presupuestos, credenciales, modelo habilitado, rutas de conversor y herramientas disponibles son configuración del servidor. No aceptarlos libremente desde el cliente o el texto CAD.

Los sobres API y eventos se proponen en [API_Y_EVENTOS.md](API_Y_EVENTOS.md). Las claves de caché incluyen hashes de entrada/conversión, versión geométrica, configuración, contrato, prompt y modelo. Los resultados grabados conservan origen y fecha.

## 9. Comprobaciones que el esquema no resuelve

Pydantic y sus esquemas generados comprueban estructura y restricciones locales. El servicio debe verificar referencias existentes, cobertura de candidatas, exclusión entre hipótesis, equivalencia de grupos, unidades/marcos, permisos de confirmación, cantidades, DAG de derivaciones y consistencia entre resultados y mediciones.

Estas reglas no se sustituyen con `strict=true` ni con otro LLM. Pruebas: [TEST_PLAN.md](TEST_PLAN.md). Los ejemplos del paquete solo demuestran coherencia documental y estructural hasta que exista implementación y oráculo geométrico independiente.

## 10. Plano para el frontend

Propuesta mínima de `DrawingPreview`, a concretar en los mismos modelos tras acuerdo A/B:

| Campo | Significado |
|---|---|
| `schema_version`, `candidate_revision` | Compatibilidad y asociación exacta con el ledger |
| `coordinate_unit` | `mm` si está resuelta; `source` si solo se muestran coordenadas originales |
| `source_unit`, `effective_unit` | Unidades registradas, admiten `null` |
| `views` | ID, marco, límites y etiqueta de cada vista de presentación |
| `paths` | ID, `view_id`, datos de path 2D generado por el backend, `source_entity_ids`, `contour_ids`, `evidence_ids` |
| `texts` | Texto y posición seguros, con IDs fuente; renderizado como texto, nunca HTML |
| `coverage` | Elementos representados, no soportados y razones |

Los paths son datos de presentación producidos por el servidor; no SVG arbitrario subido por el usuario. El frontend no descarga recursos externos ni ejecuta scripts de un dibujo. El mapa de IDs conserva el vínculo con entidades aunque aún no existan piezas. Las rutas de lectura y artefactos están en [API_Y_EVENTOS.md](API_Y_EVENTOS.md).

## 11. Ampliaciones que no entran implícitamente en 0.1.0

- Cadenas dimensionales generales: R-015 devuelve `not_applicable` en P0. P1 necesita una representación estructurada de miembros, eje, marco, signos, juntas y evidencia. No interpretar prosa como si fuera una restricción formal.
- PDF de entrada: necesita localizadores por archivo, página y región, referencias de BOM y cotas nominales; no inventar handles DXF. Véase [ADAPTACION_DATASET.md](ADAPTACION_DATASET.md).
- Ángulos, tolerancias mecánicas, radios y operaciones de mecanizado: tipado específico y unidades explícitas antes de publicar una ficha de fabricación mecánica.
- Hipótesis de cardinalidad variable o conjuntos anidados: un identificador plano de alternativas no basta.

Estas extensiones se registran como pendientes; ninguna cambia el contrato implementado sin el acuerdo requerido por `CLAUDE.md`.

## Límite de la corrección de identidad en P0

`RunConfig` y el endpoint de revisión propuestos no incorporan nuevas asociaciones físicas ni confirmaciones de ocurrencias de conjunto. La UI P0 permite escoger referencias, etiquetas y alternativas ya sustentadas; si la corrección necesita nueva evidencia de identidad, conserva `needs_review`. Repetir entrada y configuración sin cambios no resuelve esa incertidumbre en un motor determinista. El mecanismo autenticado para introducir tal evidencia, regenerar el ledger e incluirla en el fingerprint queda pendiente de acuerdo A/B y aviso C. Los cambios de unidades y etiquetas de vista sí siguen las entradas propuestas; no se equiparan a confirmar asociación física.

## Extensiones necesarias en T11–T12 (pendientes de acuerdo)

El inventario 0.1.0 anterior no basta para cumplir la transcripción. Antes de implementar, A/B deben acordar estas responsabilidades y avisar a C; los nombres siguientes son conceptuales, no un segundo esquema JSON:

| Modelo propuesto | Información necesaria |
|---|---|
| Escenario de descomposición | Componentes/secciones propuestos, regiones/vistas fuente, alternativas incompatibles, premisas y campos pendientes |
| Revisión de premisas | Actor, fecha, motivo, decisión, fuentes y relación con revisión anterior; regeneración de ledger/fingerprint |
| Proyecto histórico | Familia, dimensiones/unidades, materiales, acabados, costes/horas disponibles, moneda, fecha, alcance y procedencia |
| Comparable | Proyecto y versión, diferencias por atributo, método de recuperación, score y motivos verificables |
| Estimación | Revisión de despiece/escenario, comparables, conceptos, cantidades, factores/tarifas, operaciones, unidades, coste/horas y exclusiones |

Separar estados observados, derivados, hipotéticos y confirmados por humano por campo. No insertar componentes hipotéticos en `pieces` como si estuvieran medidos. No extender silenciosamente `Submission` con cifras libres: las herramientas resuelven referencias y cálculos con premisas autorizadas. Exportar hipótesis en una sección diferenciada. Acordar migración y versión antes de modificar consumidores; los ejemplos 0.1.0 siguen ilustrando solo el hito técnico.

## Referencia de PlankAssembly y contrato de producto

Los JSON de [PlankAssembly](PLANKASSEMBLY.md) son datos externos del evaluador, no `Submission`, `EvidenceLedger` ni un esquema alternativo de producto. El adaptador pendiente debe distinguir envolvente y tableros, conservar índices de `attach`, registrar mm y representar la ausencia de `normal`. No convertir esos datos privados en evidencia observada por el agente desde un plano pobre.

La procedencia de una futura vista debe conservar su transformación de escala y proyección. Campos específicos de preparación viven fuera del contrato público hasta el acuerdo correspondiente; esta actualización no añade campos a 0.1.0. Material, acabado, coste y tiempo permanecen desconocidos sin otra fuente.
