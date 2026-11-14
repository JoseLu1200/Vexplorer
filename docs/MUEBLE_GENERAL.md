# Mueble general: propuesta y critica multimodal con evidencia

## Alcance real

El flujo `general_furniture` interpreta un `DrawingExtraction` sin exigir que el mueble encaje en los perfiles de mesa o estantería. El motor determinista publica cotas anotadas y medidas geométricas de contornos (`measurement:<id>`). El modelo puede proponer componentes de panel, perfiles lineales, herrajes o elementos desconocidos y asignar esas medidas mediante operaciones `copy`, `add` y `subtract`.

Una medida geométrica es una observación del dibujo; su asignación a largo, ancho o espesor de un componente sigue siendo una **hipótesis**. El resultado no acredita uniones, mecanizados, tolerancias, veta, cantos, colocaciones ni aptitud de fabricación. Curvas y formas arbitrarias se conservan como evidencia de origen, pero los planos derivados actuales solo representan envolventes rectangulares esquemáticas.

## Entrada y ejecución

Para DXF, DWG normalizado o una página PDF vectorial normalizada, se crea un run con:

```json
{
  "document_id": "doc-...",
  "mode": "live",
  "input_kind": "general_furniture",
  "proposal_mode": "model_generated"
}
```

En producción se usa `POST /api/v1/jobs` con `Idempotency-Key`; `POST /api/v1/runs` queda solo para local. El endpoint directo `POST /api/v1/runs/{run_id}/general/proposals` no permite `mode=live` en producción: el proveedor debe ejecutarse mediante el trabajo durable y acotado.

Para PDF se selecciona primero una página con `POST /api/v1/documents/{document_id}/pdf-pages/{page_number}/normalize`. Una escala métrica solo se acepta si una persona autorizada aporta `mm_per_pdf_point`; sin ella, las unidades y los milímetros permanecen desconocidos. En páginas raster, la imagen seleccionada puede darse al modelo como contexto visual, pero no autoriza medir píxeles. Es válido proponer componentes visuales con dimensiones desconocidas y referencias `document:<id>:page:<n>`.

## API de propuesta y revisión

El trabajo durable ejecuta dos papeles separados: un proponente y un critico multimodal. El critico recibe imagenes CAD/PDF reales, marcas enlazadas a contornos y entidades, medidas del ledger y candidatos geometricos ambiguos; no recibe el razonamiento interno del proponente. Puede aceptar, rechazar, declarar conflicto o abstenerse por campo. Si detecta un error corregible, dispone de una sola reparacion semantica: crea una propuesta P2 completa con bindings cerrados contra el mismo ledger y vuelve a criticarla. P1 y P2 permanecen inmutables; agotar el bucle nunca convierte incertidumbre en aprobacion.

Las respuestas JSON usan el envelope `{ "schema_version": "0.6.0", "data": ... }`.

- `GET /api/v1/runs/{run_id}/general` devuelve propuesta, borrador efectivo y última revisión.
- `POST /api/v1/runs/{run_id}/general/proposals` admite propuesta manual con `mode="manual"`, `base_proposal_revision` y `proposal_origin="human"`. El ledger debe coincidir con el run. El CAS evita sobrescrituras concurrentes.
- `POST /api/v1/runs/{run_id}/general/reviews` recibe `base_proposal_revision`, `base_review_revision`, autor, motivo, operaciones y el snapshot final de componentes.
- `POST /api/v1/runs/{run_id}/general/auto-review` re-verifica un snapshot exacto cuando esta conectado a la cola durable. La ejecucion directa esta deshabilitada por defecto (`409 general_auto_review_requires_durable_job`) para no eludir cuotas, idempotencia ni auditoria.

Las operaciones son `replace`, `split`, `merge` y `drop`, con `source_component_ids`, `result_component_ids` y motivo. Cada revisión debe cubrir todos los componentes vigentes. La segunda revisión y siguientes operan sobre los IDs de `review.components` de la revisión anterior, no sobre el borrador original. El servidor conserva snapshots inmutables por `(run_id, proposal_revision, review_revision)` y estampa la procedencia humana desde el actor autenticado.

Las vistas nunca se cuentan como unidades fisicas. Una cantidad visual puede proponerse como `hypothesis` si cita una premisa y grupos de instancias distintos; el critico exige checks `quantity_basis` y `duplicate_scan`. Eso crea solo `scenario_occurrences` provisionales, nunca `occurrence_ids` fisicos ni base de coste fiable. Solo cantidades `observed`, `derived` o `confirmed` validadas generan ocurrencias fisicas. La interfaz puede mostrar "hipotesis - auto-revisada" sin convertirla en hecho. La revision manual sigue disponible como correccion opcional, no como paso obligatorio.

`furniture_quantity` es independiente: representa el numero de muebles terminados del encargo, no la suma de piezas, y queda desconocido hasta evidencia fiable o confirmacion explicita. `currency`, `required_cost_scope` y `required_hours_scope` son decisiones explicitas; nunca se infieren del historico ni de componentes.

## Derivados e histórico

`GET /api/v1/runs/{run_id}/general/derived?proposal_revision=P&review_revision=R` devuelve el paquete exacto revisado:

- filas BOM con estados y fuentes por campo, separando ocurrencias fisicas de escenario;
- CSV y JSON con `quantity_state`, `occurrence_status`, `physical_occurrence_ids` y `scenario_occurrence_ids` explicitos;
- SVG y DXF esquemáticos, con DXF en milímetros, cotas/estados, cantidad y una figura por ocurrencia validada;
- escena 3D sin colocación inventada (`schematic_unplaced`);
- base de coste por área/volumen y datos ausentes.

Los artefactos se descargan con snapshot explícito:

`GET /api/v1/runs/{run_id}/general/artifacts/{artifact_id}?proposal_revision=P&review_revision=R`

El `historical_target` se construye en servidor. Área, longitud, volumen, material y acabado solo se publican cuando **todos** los componentes incluidos tienen cobertura compatible `confirmed|derived`; no se presenta un subtotal parcial como total. `quantity` solo procede de `furniture_quantity`. Moneda, familia y atributos ausentes permanecen `null`. La recuperación semántica encuentra comparables, pero no prueba equivalencia de fabricación ni autoriza un precio.

## Auditoría y límites

El modo live registra herramienta, fase (propuesta, critica, reparacion, revision), resultado breve, IDs de respuesta/call, modelo, duracion y tokens; no registra razonamiento interno ni secretos. Hay limites de llamadas, una reparacion semantica, reparaciones de JSON, tiempo, imagenes, componentes, cantidades, ocurrencias, revisiones y tamano de base de datos. Si falta evidencia, el comportamiento correcto es conservar `unknown` o abstenerse automaticamente, no completar con valores tipicos ni exigir una revision humana.

Este pipeline es extensible a familias de paneles, pero no es un reconstructor industrial universal. Produce escenarios trazables, auto-criticados y honestos sobre sus huecos. Una persona puede corregirlos opcionalmente, pero su ausencia no bloquea una salida provisional marcada como tal.
