# Agente de fuentes de datos públicas

## Identidad y autorización

- Identidad: agente de IA de fuentes externas; no representa a una persona.
- Autorización: delegación explícita del coordinador del swarm el 2026-11-14.
- Rol: localizar, descargar y documentar fuentes públicas reales de mobiliario para histórico económico, sin fabricar datos empresariales.

## Alcance y reservas

- Propiedad: este registro, `docs/FUENTES_HISTORICO_PUBLICO.md` y datasets nuevos fuera de Git bajo el directorio padre `1hack`.
- Posible código aislado: importador público y sus pruebas solo si la fuente no encaja en el contrato existente.
- No editar: `backend/app/main.py`, contratos, servicio de histórico, frontend, evaluación ni registros de otros agentes.

## Trabajo realizado

- Auditados los datasets existentes en `1hack`: PlankAssembly y corpus CAD no contienen histórico económico; el repositorio solo incluía fixtures sintéticos y el importador.
- Revisadas fuentes primarias y Hugging Face. No se encontró un corpus abierto mejor documentado con coste, horas y dimensiones fila a fila.
- Descargados PDF y XML originales CC BY 4.0 del estudio `10.3390/su18157720`.
- Normalizados 4 muebles con dimensiones/materiales/componentes, 4 costes totales, 4 tiempos y 12 conceptos económicos; precios de venta separados.
- Generado `historical_import.json` compatible con los modelos existentes, sin necesidad de implementar otro importador.
- Migrado tras el cambio contractual: coste cubre exactamente `material|labor|indirect`, horas solo `labor`, e `included_scope` conserva su unión; el concepto publicado de costes indirectos usa el identificador extensible `indirect`.
- Aplicada la clasificación contractual final `origin: published` y `cost_basis: budget`; nunca `actual` ni `synthetic`.
- Corregida la identidad histórica: cada producto del estudio tiene `project_id` propio para impedir que la deduplicación por revisión reduzca cuatro muebles a uno.
- Unificada la etiqueta de material entre registro y concepto; el aceite permanece en `finish` y no genera una incompatibilidad textual artificial.
- Registrados DOI, URLs, fecha, licencia, hashes y limitaciones en un manifiesto fuera de Git.

## Verificación

- `HistoricalImport.model_validate_json(...)`: 4 registros aceptados con los tres alcances explícitos.
- Para cada registro, la suma de conceptos coincide con coste total y horas totales.
- PDF/XML descargados desde `mdpi-res.com`; hashes SHA-256 registrados.
- Comparación textual contra las tablas 2, 6, 7, 8 y 9 del XML.
- Importación real aislada: 4 aceptados, 0 rechazados, 4 almacenados.
- Recuperación: 4 comparables publicados; mesa infantil primera (`0.964848`).
- Estimación compatible: 112,90 PLN y 3 h, `uncertainty=high`, `origin=published`, `cost_basis=budget` y aviso de no ejecutado.
- Descargada segunda fuente CC BY 4.0, DOI `10.3390/su18189636`: 15 coeficientes publicados de tiempo por unidad, sin importar profit/costes/consumos como coste.
- Verificados los 15 triples de tiempo contra las tablas XML A2/A4/A6; dimensiones, material y acabado permanecen ausentes.
- QA separada `public-hours`: 15 aceptados, 0 rechazados; cinco comparables de salón y estimación de 3,88 h para dos unidades Karat, con coste no estimable.

## Dependencias y avisos

- El histórico debe importar esta fuente como `cost_basis: budget`, no como coste ejecutado de ERP.
- La UI debe mostrar juntos `origin: published`, `cost_basis: budget` y la procedencia; ocultar cualquiera de ellos podría inducir a interpretar los costes asumidos como ejecutados.
- No mezclar `retail_benchmark.csv` con costes de producción.
- La muestra es suficiente para smoke y cálculos trazables, insuficiente para validar precisión empresarial o generalizar a todas las familias.
