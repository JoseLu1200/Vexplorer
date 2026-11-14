# Histórico económico: importación y estimación

Este módulo permite cargar registros empresariales sin incluir ningún dato empresarial en el repositorio. Los fixtures y demos deben usar `origin: synthetic`; disponer del importador no acredita precisión económica hasta validarlo con registros reales compatibles.

La fuente de verdad del formato son los modelos Pydantic de `backend/app/historico/models.py`. Los campos desconocidos se rechazan y los valores ausentes permanecen ausentes.

## Persistencia y montaje

- Construcción: `HistoricalStore(db_path, embedding_provider=None)`.
- Router: `create_history_router(store)`; se monta con `app.include_router(...)`.
- Producción: integración configura `VEXPLORER_HISTORY_DB`, con un valor predeterminado dentro de `VEXPLORER_DATA_DIR`. La SQLite separada debe incluirse en copias y restauraciones.
- El middleware global de la aplicación mantiene autenticación y auditoría. Si existe `request.state.actor`, prevalece sobre cualquier `provenance.imported_by` enviado por el cliente.

## Registro JSON

```json
{
  "record_id": "wo-2026-0042",
  "project_id": "project-17",
  "revision": "r3",
  "family": "rectangular_table",
  "width_mm": 1200,
  "depth_mm": 600,
  "height_mm": 750,
  "area_mm2": 2800000,
  "length_mm": 8400,
  "volume_mm3": 50400000,
  "quantity": 3,
  "material": "oak veneer",
  "finish": "clear lacquer",
  "currency": "EUR",
  "actual_cost": 450,
  "cost_basis": "actual",
  "manufacturing_hours": 15,
  "origin": "actual",
  "provenance": {
    "source": "ERP work order WO-42",
    "source_date": "2026-10-31",
    "notes": "Closed production order"
  },
  "included_scope": ["material", "labor"],
  "cost_scope": ["material", "labor"],
  "hours_scope": ["material", "labor"],
  "components": [
    {"component_id": "top", "kind": "panel", "quantity": 1, "length_mm": 1200, "width_mm": 600, "material": "oak veneer", "finish": "clear lacquer"}
  ],
  "concepts": [
    {
      "concept_id": "material",
      "kind": "material",
      "driver": "area",
      "cost": 300,
      "hours": 3,
      "material": "oak veneer"
    },
    {
      "concept_id": "assembly",
      "kind": "labor",
      "driver": "item",
      "cost": 150,
      "hours": 12
    }
  ]
}
```

`origin` distingue registros empresariales (`actual`), fuentes públicas externas (`published`) y fixtures (`synthetic`). Un presupuesto académico publicado usa `published`, nunca `actual`. Por defecto la recuperación incluye `actual` y `published`, y excluye `synthetic`. `cost_basis` distingue coste ejecutado (`actual`), oferta (`quote`) y presupuesto (`budget`); no se mezclan estos conceptos.

`cost_scope` y `hours_scope` son obligatorios cuando existe su total y se mantienen separados: un concepto puede aportar solo coste o solo horas. `included_scope` es la unión documental. Los identificadores son extensibles (`material`, `labor`, `machining`, `finish`, `fixed`, `published_budget`, `upcycling`, etc.) y deben coincidir exactamente con el alcance requerido; no se infieren desde un comparable.

Si se declaran conceptos, la suma de sus costes y horas debe coincidir con los totales publicados. El coste exige moneda ISO 4217 de tres letras. Un registro puede tener solo coste o solo horas, pero no puede carecer de ambos.

`quantity` es el número de muebles o unidades terminadas del lote, nunca la suma de componentes de la BOM. `area_mm2`, `length_mm` y `volume_mm3` son consumos totales del lote. Si el número de muebles no está respaldado pero el consumo total sí, el cálculo usa directamente la razón entre consumos totales y deja sin resolver los conceptos cuyo driver sea `item`.

## CSV

`POST /api/v1/history/imports` y su alias `/api/v1/history/import/csv` reciben `multipart/form-data`, campo `file`, UTF-8/UTF-8-BOM. `dry_run=true` valida sin escribir.

Columnas admitidas:

```text
record_id,project_id,revision,family,width_mm,depth_mm,height_mm,length_mm,area_mm2,volume_mm3,quantity,material,finish,currency,actual_cost,cost_basis,manufacturing_hours,included_scope,cost_scope,hours_scope,origin,source,source_date,imported_by,notes
```

El CSV representa totales sin desglose por conceptos. La estimación derivada será una analogía global de evidencia baja. Para cálculo por conceptos debe usarse JSON. Cada fila CSV se valida por separado y la respuesta incluye `accepted`, `unchanged`, `rejected` y errores con número de fila.

La importación es inmutable por `record_id`: repetir el mismo payload cuenta como `unchanged`; reutilizar el ID con otros datos se rechaza. Revisiones distintas necesitan IDs de registro distintos y conservan `project_id` común.

## API

- `POST /api/v1/history/import/json?dry_run=false`: cuerpo `{"records": [...]}`.
- `POST /api/v1/history/imports?dry_run=false`: CSV multipart.
- `GET /api/v1/history?limit=50&offset=0&origin=actual`: listado paginado; alias `/records`.
- `POST /api/v1/history/comparables`: cuerpo `{"target": ..., "limit": 5, "retrieval_method": "attribute", "include_synthetic": false}`.
- `POST /api/v1/history/estimate`: cuerpo `{"target": ..., "comparable_ids": [...], "include_synthetic": false}`.
- `POST /api/v1/history/scenarios`: cuerpo `{"run_id": ..., "proposal_revision": 2, "review_revision": 1, "limit": 3, "retrieval_method": "attribute"}`. El servidor carga el snapshot exacto mediante callback; nunca acepta BOM ni snapshot del cliente.

El target declara `required_cost_scope` y `required_hours_scope` como listas de identificadores elegidas por una persona. Si falta una, toda cifra derivada de esa métrica queda desconocida: contribuyentes estimados, totales de escenario, rango y agregado. Los valores históricos `base_*` se conservan como evidencia, no como estimación. La compatibilidad se resuelve por métrica: un registro solo de coste puede combinarse con otro solo de horas; cada scope no vacío debe coincidir exactamente con el requerido y nunca aporta a la otra métrica. La respuesta publica `effective_cost_scope` y `effective_hours_scope`.

Todas las respuestas correctas usan `{"data": ..., "error": null}`. Por defecto se excluyen sintéticos, el mismo `project_id` y los `exclude_record_ids` del target.

La recuperación `attribute` publica cada componente del score y diferencias concretas. La recuperación `semantic` requiere un `OpenAIEmbeddingProvider` compatible, publica modelo/dimensiones y cachea por hash del registro, modelo y dimensión. Nunca se presenta el coseno como distancia geométrica, probabilidad o equivalencia de fabricación.

## Escenarios provisionales sin promoción de hechos

`/history/scenarios` es una vía separada de la estimación confirmada. `create_history_router` recibe opcionalmente `scenario_snapshot_loader(run_id, proposal_revision, review_revision) -> ProvisionalScenarioSnapshot`. Integración debe cargar exactamente esas revisiones desde los repositorios generales, aplicar ownership/autenticación global y devolver 404/409 en ausencia o conflicto; no se usa un alias `latest`.

Solo se consumen filas BOM `provisional` con cantidad `hypothesis` autoaceptada, IDs de ocurrencia únicos y checks aprobados `quantity_basis` y `duplicate_scan`. Longitud y ancho deben ser hipótesis autoaceptadas con dependencia/evidencia. Material y acabado conocidos deben estar autoaceptados y ser homogéneos; si son desconocidos, cada escenario puede heredarlos de su referencia, siempre como condición visible. Un conflicto o una abstención de la revisión completa bloquea el cálculo.

La respuesta usa `conditional_provisional_not_quote` y crea una tarjeta por comparable no sintético, con máximo 3 por defecto. Nunca promedia tarjetas: cada una hereda de una sola referencia su familia condicional, moneda, scopes, fecha efectiva, `origin`, `cost_basis` y procedencia por métrica. La cantidad de mueble igual a 1 es un supuesto condicional, no una ocurrencia física. Contributors y scaling basis permanecen trazables; un único comparable conserva rangos `null` porque un punto no forma un intervalo calibrado.

El endpoint no escribe el histórico, no modifica `GeneralHistoricalTarget` y no produce una oferta ni presupuesto industrial. Si faltan cantidad/geometría/evidencia o la BOM conocida mezcla materiales/acabados, responde `not_estimable` con `missing_data` explícito.

## Fórmulas, escenarios e incertidumbre

Cada concepto se calcula dentro de su comparable, nunca sumando proyectos alternativos:

```text
estimación = base × factor_cantidad × factor_consumo × factor_tarifa_unitaria
```

- `fixed`: factores de cantidad y consumo iguales a 1.
- `item`: `factor_cantidad = cantidad_objetivo / cantidad_histórica`.
- `area`: con cantidades de muebles conocidas, usa el factor de cantidad anterior y `factor_consumo = área_por_unidad_objetivo / área_por_unidad_histórica`; sin cantidad objetivo respaldada, escala por la razón de consumos totales.
- `length` y `volume` aplican la misma relación por unidad sobre longitud o volumen declarados.
- La moneda debe coincidir para costes. La compatibilidad de material se exige solo al concepto `material`, usando primero su override; la de acabado, solo a `finish`. Los conceptos fijos y de mano de obra no se invalidan por esos cambios. No se inventan conversiones, inflación ni factores para cambios incompatibles.
- Las horas se escalan desde horas históricas con los mismos drivers declarados; nunca se derivan de euros.

La respuesta conserva `scenarios`, uno por registro, con sus líneas y total. `cost_subtotal` y `manufacturing_hours` son promedios ponderados por la similitud de escenarios completos, no la suma de alternativas. Los rangos mínimo/máximo solo usan escenarios completos y son escenarios observados, no intervalos estadísticos.

Una sola referencia por conceptos produce incertidumbre `medium`; varias referencias completas, `low`; analogía global sin desglose, `high`; incompatibilidad o ausencia suficiente, `not_estimable`. `missing_data` explica la abstención. La salida conserva revisión objetivo, IDs, fuente/fecha, `origin` y `cost_basis` de cada comparable.

## Evaluación empírica leave-one-project-out

La QA pública incluye una evaluación leave-one-project-out de los cuatro muebles `published/budget` del único caso académico disponible. En cada fold se retira completamente el proyecto objetivo, se importan solo los otros tres y se cachean sus embeddings reales `text-embedding-3-small` de 256 dimensiones. El target contiene exclusivamente familia, dimensiones/consumos disponibles, cantidad, material, acabado, moneda, scopes y exclusiones; nunca contiene el coste, las horas ni los conceptos económicos retenidos. Se recuperan semánticamente los tres candidatos y se pasan todos sus IDs al estimador sin selección retrospectiva ni tuning.

El protocolo declara que las predicciones se congelaron y hashearon antes de consultar las referencias presupuestarias retenidas; no constituye una attestación externa independiente. El protocolo, targets, IDs de entrenamiento, scores, hashes de payload/vector y predicciones están en `.runtime/transcript-qa/public-history/loocv_predictions_precomparison.json`. La comparación posterior está en `.runtime/transcript-qa/public-history/loocv_economic_evaluation.json`.

Resultados sobre cuatro folds:

- Coste: cobertura de predicción finita 4/4, MAE 48,82 PLN, MAPE 32,250755 % y cobertura del rango de escenarios 2/4.
- Horas: cobertura de predicción finita 4/4, MAE 0,46775 h, MAPE 16,292619 % y cobertura del rango de escenarios 3/4.
- No hubo resultados no finitos.

Estos valores miden consistencia interna sobre solo cuatro presupuestos de una misma publicación académica. No miden precisión sobre costes ejecutados, órdenes cerradas o datos ERP. Los rangos son mínimos/máximos de escenarios históricos, no intervalos de confianza calibrados.

## Límites

- No hay conversión de moneda ni ajuste temporal de precios.
- No se infiere una tarifa de material o acabado diferente.
- CSV no expresa conceptos; JSON sí.
- No se incluyen XLSX ni adjuntos de ERP.
- La API genera una orientación provisional; no es una orden de compra ni un presupuesto aprobado.
