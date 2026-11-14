# Fuentes públicas para el histórico económico

Fecha de comprobación: 2026-11-14.

## Dataset descargado y admitido

Se descargó fuera de Git, en `../public_furniture_history_2026-11-14/`, una muestra pública de cuatro muebles procedente de un estudio académico primario:

- Małgorzata Grotowska, Emilia Grzegorzewska, Piotr Beer y Sylwia Oleńska, *Creative Upcycling of Wood Waste into Furniture: Bridging Durability Testing and Economic Viability, a Case Study*, Sustainability 18(15), 7720, publicado el 2026-07-30, DOI `10.3390/su18157720`.
- Licencia declarada por el editor: Creative Commons Attribution 4.0 (CC BY 4.0).
- Procedencia conservada: PDF y XML originales del editor, URL, DOI, fecha, licencia y SHA-256 en `manifest.json`.

La fuente publica cuatro registros: mesa cuadrada, silla infantil, mesa infantil y puf. Para cada uno hay horas de trabajo, coste de material, coste de personal, coste indirecto y coste total de producción. También aporta consumo de madera, materiales/acabado y componentes con dimensiones; tres productos tienen dimensiones exteriores textuales. Son 4 registros normalizados y 12 líneas de concepto, repartidas entre material, mano de obra e indirectos.

El fichero `historical_import.json` valida directamente contra `HistoricalImport` y mantiene:

- moneda `PLN` y fecha de fuente;
- `cost_basis: budget`, porque el propio artículo denomina los importes costes asumidos y análisis económico preliminar;
- `origin: published`, porque es un benchmark académico publicado; nunca se presenta como orden empresarial ejecutada ni como fixture sintético;
- `cost_scope: [material, labor, indirect]`, coincidencia exacta con las tres clases de conceptos que aportan coste en las tablas 6 y 7;
- `hours_scope: [labor]`, porque solo la línea de mano de obra contiene horas; no se atribuyen horas de proceso a materiales ni indirectos;
- `included_scope: [material, labor, indirect]`, unión documental de ambos alcances;
- un `project_id` distinto por producto publicado; el DOI común permanece en procedencia, pero mesa, silla, mesa infantil y puf no se tratan como revisiones de un mismo mueble;
- suma exacta de conceptos igual al coste total y suma de horas igual al total de fabricación;
- dimensiones ausentes como `null`/campo omitido, sin completarlas con valores típicos.

Los valores de venta/ingreso neto de las tablas 8 y 9 están en `retail_benchmark.csv`, separado del coste de producción. No se importan como `actual_cost`.

## Adecuación

Esta fuente sirve para probar de extremo a extremo:

- importación de registros públicos no sintéticos;
- comparables con dimensiones, materiales, acabado y campos ausentes;
- estimación por conceptos con costes fijos, material por área y mano de obra por unidad;
- horas independientes de euros;
- trazabilidad y abstención ante incompatibilidad de moneda/material/acabado.

No sirve para medir precisión empresarial general: solo son cuatro productos upcycled de un caso académico. No son órdenes ERP cerradas, no representan distribución de una fábrica y no deben mezclarse con un histórico privado sin etiquetar su procedencia.

Existe además una contradicción interna en el puf: la tabla 2 indica seis tableros de 440 × 440 × 18 mm y la narración menciona un tablero de 380 × 380 × 18 mm. La normalización conserva la tabla 2 y declara el conflicto; no lo resuelve por inferencia.

## Fuentes revisadas y no descargadas

- La búsqueda de Hugging Face para `furniture cost`, `furniture price dimensions` y `furniture manufacturing` no devolvió datasets. Las entradas IKEA encontradas son manuales/imágenes, sin costes u horas de fabricación; no se descargaron.
- Catálogos IKEA o equivalentes pueden aportar dimensiones y precios retail, pero no costes ni horas de producción. No se usan como verdad económica de fábrica.
- El estudio de coste de mobiliario de IJMLC 2021 describe 1.026 productos, pero no publica el dataset fila a fila en la fuente consultada; no se fabricaron registros a partir de estadísticas agregadas.
- Un estudio de capacidad de producción de 2026 declara datos reales de máquinas, pero su disponibilidad es solo bajo solicitud a autores; no se descargó ni se aceptó ninguna licencia contractual.
- El artículo de Nuriyev et al. 2026 publica 15 productos y coeficientes de tiempo por unidad derivados de datos mensuales reales. Se descargó después como benchmark separado de horas; no se importaron profit, consumos ni supuestos de coste, y los datos brutos disponibles bajo solicitud no se pidieron.

## Uso operativo

La carpeta de terceros permanece fuera del repositorio. Antes de una importación, comprobar hashes con `manifest.json` y ejecutar una validación en seco. La fuente requiere atribución CC BY 4.0 si se redistribuyen o adaptan sus datos.

## QA integrada

Se importó realmente el payload final en `.runtime/transcript-qa/public-history/history.sqlite3`: 4 aceptados, 0 rechazados y 4 almacenados. Los cuatro se recuperan por atributos sin habilitar sintéticos. Para un objetivo de mesa compatible, la mesa infantil quedó primera con score `0.964848`.

La estimación focal, basada solo en esa mesa infantil, produjo 112,90 PLN y 3 horas. Conservó `origin: published`, `cost_basis: budget`, incertidumbre `high` y la advertencia de que no es un coste ejecutado. Los artefactos y el comando reproducible están en `.runtime/transcript-qa/public-history/`.

## Benchmark adicional de horas

En `../public_furniture_hours_2026-11-14/` se conserva el artículo de Nuriyev et al., DOI `10.3390/su18189636`, publicado el 2026-09-20 bajo CC BY 4.0. Sus tablas 1-3 y A2/A4/A6 publican 15 coeficientes de tiempo por unidad para mobiliario de dormitorio, infantil y salón, basados en datos mensuales reales de tres empresas anonimizadas de Azerbaiyán.

La normalización es deliberadamente estrecha:

- `origin: published`, `actual_cost: null`, `cost_basis: null` y sin moneda;
- `manufacturing_hours` contiene solo el coeficiente central publicado;
- `hours_scope: [production_time]`, no `labor`, porque el artículo lo define como tiempo de producción/proxy de carga laboral y no aporta desglose de mano de obra;
- `quantity: 1` representa el coeficiente explícito por unidad;
- dimensiones, material y acabado permanecen ausentes;
- los límites inferior/superior y la fiabilidad Z permanecen en CSV y procedencia, sin convertirse en intervalos estadísticos inventados.

La QA separada `.runtime/transcript-qa/public-hours/` aceptó 15 registros y rechazó 0. Recuperó los cinco productos de salón; una analogía focal de dos unidades de Karat devolvió 3,88 h y coste desconocido. El resultado conserva `hours_uncertainty=medium` y `cost_uncertainty=not_estimable`.
