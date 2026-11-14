# Evaluación de recuperación de precedentes (idea 2.7)

Mide si el buscador de comparables ordena bien la biblioteca con juicios graduados y métricas reproducibles. Los modelos y las métricas están en `backend/app/precedentes/evaluacion.py`; la CLI es `tools/evaluar_recuperacion.py`.

```bash
python -m tools.evaluar_recuperacion --biblioteca export.json --juicios evaluation/recuperacion/juicios_sinteticos.json --k 5 --metodo geometrico
```

- `--biblioteca` es un JSON con una lista de `LibraryItem` o con la forma `{"items": [...]}`. Por ejemplo, un volcado de `Repository.get_library_items()`.
- Cada consulta se rankea contra el resto de la biblioteca. Se excluyen el propio elemento, los elementos del mismo `run_id` y los de otra versión de descriptor. El informe cuenta cada exclusión.
- La salida es JSON con métricas por consulta y agregadas, exclusiones y advertencias. Una advertencia aparece, por ejemplo, cuando una consulta o un candidato juzgado no están en la biblioteca.

## Formato de juicios

```json
{"version": "1.0.0", "origen": "team_reviewed", "descripcion": "...",
 "consultas": [{"consulta_id": "<id LibraryItem>", "relevancias": {"<id candidato>": 2}, "nota": "opcional"}]}
```

Escala: `2` comparable, `1` parcialmente comparable, `0` no comparable. `origen` es `synthetic` o `team_reviewed`.

## Métricas

- **precision@k:** relevantes (grado ≥ 1) en el top-k, divididos siempre entre k.
- **recall@k:** relevantes en el top-k entre el total de relevantes juzgados.
- **MRR:** sobre el ranking completo.
- **nDCG@k:** ganancia `2^grado − 1`. El ideal se calcula con todos los grados juzgados.

Detalles de cálculo:

- Si una consulta no tiene relevantes, recall, MRR y nDCG quedan indefinidos (`null`). Esas consultas no entran en la media y se cuentan en `consultas_sin_relevantes`.
- Un candidato rankeado sin juicio cuenta como no relevante. Aparece en `candidatos_sin_juicio`, y `cobertura_juicios` resume la proporción juzgada. Si la cobertura es baja, las métricas no son fiables.

## `juicios_sinteticos.json` no es evidencia

El archivo está marcado `synthetic`. Sus ids pertenecen a una biblioteca inventada que construyen los tests. Sirve para comprobar que el mecanismo funciona; sus cifras **no demuestran la calidad de ningún método**.

## Cómo crear juicios revisados por el equipo

1. Exporta la biblioteca real a JSON y elige consultas representativas, sin quedarte solo con los casos fáciles.
2. Para cada consulta, ejecuta los métodos que se van a comparar y une sus top-k. Juzga **todo** ese conjunto para que ningún método salga favorecido por falta de juicios.
3. Pide a dos personas que juzguen cada consulta por separado con la escala 0/1/2. Resolved los desacuerdos y anota el criterio en `nota`.
4. Guarda el resultado en un archivo nuevo con `origen: "team_reviewed"` y una versión. No reescribas un conjunto ya usado para comparar métodos.
5. Compara métodos solo sobre el mismo conjunto y la misma `k`, y comprueba siempre `cobertura_juicios`.

## Punto de extensión

Registra en `METODOS` de `tools/evaluar_recuperacion.py` una función `(consulta, candidatos) -> ((id, score), ...)`. Puede ser el score híbrido de la idea 2.3, que todavía no está implementado. Orden y exclusiones son comunes a todos los métodos.

## Juicios derivados de PlankAssembly (`derived_reference`)

`origen: "derived_reference"` marca juicios calculados por una regla determinista sobre la referencia privada de un corpus, sin revisión humana. `tools/evaluar_recuperacion.py` los acepta y añade un `aviso` al informe: miden acuerdo con la regla, no preferencia del técnico. No se versionan aquí (derivan de PlankAssembly, CC BY-NC-ND 4.0): se generan fuera del repositorio.

```powershell
hf download manycore-research/PlankAssembly --repo-type dataset --revision d1d4308f0ee0aac2f9f407b3533ff83ecee22d34 --local-dir ../plankassembly_dataset
# extraer data.zip en ../plankassembly_dataset/extracted/
python -m tools.plankassembly_corpus --source ../plankassembly_dataset --public-output ../plankassembly_corpus_public --private-output ../plankassembly_corpus_private --seed 20261114 --train 2000 --valid 200 --test 200 --poor-variants
python -m tools.evaluar_recuperacion --biblioteca <biblioteca.json> --juicios ../plankassembly_corpus_private/juicios/juicios_test.json --k 5 --metodo geometrico
```

- Archivos: `juicios_test.json` (similitud graduada, consultas = test), `juicios_test_<tipo>.json` (consultas empobrecidas) y `juicios_identidad_<tipo>.json` (identidad entre vistas: solo el mueble completo propio es relevante).
- La biblioteca debe contener todos los casos completos con `id` = id del caso y `run_id` distinto por caso. En `juicios_test_<tipo>` la variante lleva `run_id` = id de su base; en `juicios_identidad_<tipo>`, uno distinto. Detalle de la regla, particiones y limitaciones: [PLANKASSEMBLY](../../docs/PLANKASSEMBLY.md#corpus-de-evaluación-por-particiones-y-juicios-derivados).
- Son densos (`cobertura_juicios` 1,0) salvo con `--zeros-per-query`. Las consultas de test nunca tienen entre sus candidatos su propio duplicado: el generador descarta duplicados entre particiones y deja un representante por grupo.
- Revisa una muestra con dos personas (sección anterior) antes de tratarlos como evidencia.
