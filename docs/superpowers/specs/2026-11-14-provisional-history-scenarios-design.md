# Escenarios económicos provisionales desde revisión autónoma

## Intención

Permitir que un run de mobiliario general auto-revisado obtenga orientaciones económicas condicionales sin promover hipótesis a hechos ni requerir moneda/scopes confirmados manualmente.

## Diseño aprobado

- `POST /api/v1/history/scenarios` recibe solo `run_id`, revisiones exactas, límite (3 por defecto) y método de recuperación. El cliente nunca envía el snapshot.
- `create_history_router` recibe un callback opcional server-side que carga un `ProvisionalScenarioSnapshot` exacto; integración correlaciona review y derived package y aplica ownership/auth global.
- Solo entran filas `provisional` con cantidad `hypothesis` autoaceptada y checks `quantity_basis` y `duplicate_scan` aprobados, además de dimensiones/material/acabado autoaceptados.
- La geometría BOM se agrega para un mueble condicional. Material/acabado conocidos deben coincidir exactamente; desconocidos se heredan de cada referencia como supuesto visible. Varias combinaciones conocidas en la BOM abstienen con `heterogeneous_material_finish`.
- Se genera un escenario separado por comparable no sintético. Cada uno hereda family, moneda, fecha efectiva, scopes, origin y cost basis de esa referencia, llama al estimador existente con un solo ID y nunca promedia escenarios incompatibles.
- La cantidad de mueble `1` y la familia/material/acabado heredados son condiciones del escenario, nunca hechos físicos ni clasificación del dibujo.
- Respuestas y UI usan `conditional_provisional_not_quote`, supuestos estructurados, procedencia por métrica, contributors/rangos y abstención explícita. No se escribe historial ni target confirmado.

## Alternativas descartadas

- Completar `GeneralHistoricalTarget`: mezclaría hipótesis con hechos revisados.
- Promediar comparables: mezclaría monedas/scopes/contextos incompatibles.
- Recibir BOM en el body: permitiría snapshots fingidos o revisiones stale.

## Límites

No es una oferta, presupuesto industrial ni estimación confirmada. No resuelve BOM heterogéneas por componente porque exigiría asignar costes fijos y evitar doble conteo con reglas nuevas.
