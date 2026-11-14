# PlankAssembly: descarga, auditoría y uso previsto

Estado a 13 de noviembre de 2026: acceso autorizado en Hugging Face, descarga completa y extracción verificadas. Todavía no se han generado vistas 2D, convertido archivos a DXF ni ejecutado inferencia sobre este corpus. Es la fuente prioritaria para preparar una evaluación controlada de mobiliario de tableros; no sustituye la validación con planos y presupuestos reales de la empresa.

## Procedencia y archivos

Fuente: [manycore-research/PlankAssembly](https://huggingface.co/datasets/manycore-research/PlankAssembly). La revisión descargada es `d1d4308f0ee0aac2f9f407b3533ff83ecee22d34`.

Los datos están fuera de Git, en `../plankassembly_dataset/`, respecto a la raíz de Vexplorer:

- `data.zip`: archivo original de 19.607.117 bytes.
- `README.md`: ficha del publicador con unidades y licencia.
- `extracted/data/model/`: 27.692 programas JSON.
- `extracted/data/splits/`: listas oficiales `train.txt`, `valid.txt` y `test.txt`.
- `download_audit.json`: registro local de comprobaciones; no es un contrato de la aplicación.

SHA-256 del ZIP: `3a7f6d0bb66ace28a3a05e286c127b5385954e29bfa7ed2e932121b2429a460c`. Coincide con el hash LFS publicado. Se comprobó el CRC de todas sus entradas y, después de extraer, la existencia y el tamaño de cada archivo: sin discrepancias. Esto verifica integridad de transferencia, no corrección industrial de cada diseño.

La descarga se realizó con `hf download`. Para repetirla en otra carpeta con una cuenta que tenga acceso, fijar la revisión:

```powershell
hf download manycore-research/PlankAssembly --repo-type dataset --revision d1d4308f0ee0aac2f9f407b3533ff83ecee22d34 --local-dir ../plankassembly_dataset
```

No incluir credenciales, cachés, programas fuente ni respuestas de evaluación en Git. La descarga es local; PlankAssembly no se ha subido al VPS.

## Inventario observado

| Comprobación | Resultado |
|---|---|
| JSON presentes | 27.692 |
| Modelos únicos en las particiones oficiales | 26.707 |
| Entrenamiento | 24.039 |
| Validación | 1.329 |
| Prueba | 1.339 |
| JSON fuera de esas listas | 985 |
| Modelos listados pero ausentes | 0 |
| Identificadores compartidos entre particiones | 0 |
| Tableros por modelo oficial, excluida la envolvente | Mínimo 3, mediana 8, máximo 19 |
| JSON sin el campo `normal` | 6.520; de ellos, 6.427 en particiones oficiales |

Todos los JSON se pudieron leer. En las comprobaciones realizadas no aparecieron coordenadas no finitas, filas de coordenadas de longitud distinta de seis, desajustes de número de filas de `attach` ni índices de asociación fuera del rango comprobado. No se auditó exhaustivamente la validez constructiva, la orientación de todas las caras ni la calidad semántica de las asociaciones.

Mantener los 985 modelos no listados fuera de la comparación con las particiones oficiales. No deducir su calidad ni el motivo de su exclusión. La ausencia de IDs compartidos no descarta muebles duplicados, variantes o escalados entre particiones: esa comprobación sigue pendiente.

## Cómo interpretar la referencia

La ficha declara coordenadas en **milímetros**. Cada JSON representa cuboides y asociaciones entre coordenadas. El lector oficial omite la primera fila de `planks` al construir geometría: corresponde a la envolvente global, no a un tablero. Véase [la función build del publicador](https://github.com/manycore-research/PlankAssembly/blob/main/dataset/data_utils.py).

Para cada fila posterior, las extensiones geométricas son las diferencias entre coordenadas máximas y mínimas. Son dimensiones del cuboide de referencia; no aportan por sí solas mecanizados, tolerancias o planos de corte. Los papeles semánticos —lateral, puerta, balda— necesitan revisión o una inferencia identificada como tal. No declarar material, acabado, precio ni horas a partir de esos cuboides.

`attach` usa índices de la secuencia aplanada, incluido el marco original. Omitir la envolvente de la lista física no autoriza a desplazar índices sin un mapeo. La ausencia de `normal` es un caso real que el futuro adaptador debe admitir o excluir explícitamente según la tarea; no descartar todos esos modelos como archivos corruptos ni inventar la dirección de extrusión. Cualquier dirección inferida debe quedar diferenciada de una anotación original.

El ZIP no contiene DWG, DXF, SVG ni PDF. El [repositorio oficial](https://github.com/manycore-research/PlankAssembly) proporciona código para generar vistas ortogonales SVG desde los programas. Esas vistas son derivadas sintéticamente de modelos de mobiliario; no son planos de fabricación originales. El código de render aplica escalas de trabajo: registrar las transformaciones y no etiquetar sus coordenadas normalizadas como milímetros sin la conversión correspondiente.

## Preparación pendiente para Vexplorer

1. Revisar las condiciones de uso aplicables a la PoC y sus entregables. Seleccionar una muestra pequeña de desarrollo de armarios/estanterías y revisarla antes de generar todo el corpus.
2. Congelar IDs, revisión, grupos de variantes y partición. Conservar los splits oficiales como referencia reproducible y, si se crea otra partición por familia, documentarla con nombre distinto. Los ejemplos inspeccionados dejan de ser prueba ciega de Vexplorer.
3. Generar vistas del mueble montado, con orientación, escala y unidades registradas. Preparar controles completos y variantes pobres: vistas parciales o solo líneas visibles. Una variante sin escala o cota útil no debe permitir afirmar dimensiones métricas.
4. Si se requiere CAD editable, crear y verificar una exportación DXF con capas y unidades explícitas; comprobarla en un lector real. No existe todavía ese conversor en Vexplorer ni un archivo listo para abrir en FreeCAD.
5. Separar entrada 2D y referencia privada por caso. El agente no recibe `planks`, `attach`, `normal`, nombres originales reveladores, piezas individualizadas ni el programa 3D. Revisar también IDs de entidades, bloques, capas, metadatos y archivos vecinos que puedan revelar componentes.
6. Validar el generador con fixtures propios de medidas conocidas y revisión visual independiente. No usar su salida como única prueba de que el mismo generador interpreta correctamente la referencia.
7. Comparar los métodos de [COMPARATIVA_METODOS](COMPARATIVA_METODOS.md). Medir identidad, medidas, omisiones, invenciones, abstenciones y corrección humana por separado. Una solución alternativa compatible con un plano ambiguo no es necesariamente un error por diferir del JSON reservado.

El corpus permite preparar búsqueda por geometría con separación de proyectos y duplicados. No incluye un histórico económico verificado: recuperación geométrica y estimación de costes son evaluaciones distintas. Las tarifas inventadas solo sirven para fixtures aritméticos rotulados.

## Condiciones y límites

La [ficha del dataset](https://huggingface.co/datasets/manycore-research/PlankAssembly/blob/main/README.md) declara **CC BY-NC-ND 4.0**. El código declara AGPL-3.0; son condiciones de artefactos diferentes. La autorización de descarga en HF no acredita permiso adicional para uso comercial o publicación de derivados. No se ha documentado una autorización específica para la PoC empresarial o su redistribución; resolver ese alcance antes de esos usos. No se ha publicado el ZIP en Git ni en un endpoint nuevo.

La auditoría resuelve la disponibilidad y el formato. Quedan pendientes las vistas, la admisión semántica, el control de duplicados y las evaluaciones del sistema. [DATASET](DATASET.md) conserva el corpus mecánico auxiliar; [PILOTO_DATASET](PILOTO_DATASET.md) documenta los 17 casos ya preparados de ese corpus. Ninguno contiene resultados de inferencia de Vexplorer.

## Corpus de evaluación por particiones y juicios derivados

`tools/plankassembly_corpus.py` amplía el adaptador de muestra (`tools/prepare_plankassembly.py`, cuyas salidas `plank-*.dxf` y `plankassembly_adapter_*`, y por tanto los consumidores del laboratorio semántico y la galería 3D, no cambian). Genera un corpus a escala con el split oficial, auditoría de duplicados y juicios para [`tools/evaluar_recuperacion.py`](../evaluation/recuperacion/README.md). No ejecuta inferencia ni descarga datos. Los resultados no cuentan como prueba ciega hasta que los casos se congelen y no se usen para ajustar prompts o reglas.

### Ejecución con el dataset real

```powershell
hf download manycore-research/PlankAssembly --repo-type dataset --revision d1d4308f0ee0aac2f9f407b3533ff83ecee22d34 --local-dir ../plankassembly_dataset
# Extraer data.zip en ../plankassembly_dataset/extracted/ (deben existir extracted/data/model y extracted/data/splits).
python -m tools.plankassembly_corpus --source ../plankassembly_dataset `
  --public-output ../plankassembly_corpus_public --private-output ../plankassembly_corpus_private `
  --seed 20261114 --train 2000 --valid 200 --test 200 --poor-variants `
  --source-revision d1d4308f0ee0aac2f9f407b3533ff83ecee22d34
```

Las salidas deben estar **fuera del repositorio** (la herramienta rechaza destinos dentro de él): son derivados de datos CC BY-NC-ND 4.0. Los destinos no pueden existir (no se sobrescribe) ni estar anidados entre sí. Tamaños por defecto: 200/50/50. `--source-revision` solo se registra; no se puede verificar sin conexión. Otros parámetros: `--tolerance-mm` y `--scale-step` (duplicados), `--max-pairs` y `--zeros-per-query` (tamaño de los juicios), `--category-field` (ver abajo).

Con 3.000 modelos sintéticos, 700 casos y sus variantes, el generador tardó unos 54 s. Sobre los 26.707 modelos reales la auditoría lee todos los JSON listados; no se ha medido ese tiempo.

### Qué hace

1. **Split oficial.** Lee `train.txt`, `valid.txt` y `test.txt`. Un modelo listado y ausente, o presente en dos particiones, es un error. Los JSON no listados (985 esperados) no se muestrean ni entran en la auditoría; se cuentan en `audit.json`. Un JSON inválido se registra en `invalid_models` y se omite.
2. **Auditoría de duplicados** sobre **todos** los modelos válidos listados. Se agrupan por unión de claves: (a) tableros exactos en mm, invariantes a la traslación; (b) mismas dimensiones por tablero dentro de `--tolerance-mm`; (c) reescalado isótropo (dimensiones normalizadas por la mayor extensión, `--scale-step`). (b) y (c) usan dos rejillas desplazadas medio paso. Es una heurística: acota, no demuestra, la ausencia de casi duplicados, y no detecta variantes paramétricas anisótropas (mismo diseño con otra anchura). Estas últimas son vecinos legítimos para la recuperación, no duplicados.
3. **Política de particiones.** El split oficial no se redefine: cada caso conserva su partición. Un grupo que toca varias particiones se conserva solo en la primera según `train > valid > test` (se descontamina valid/test y train queda íntegro) y cada partición conserva un único representante por grupo (el menor nombre de archivo). Así el duplicado propio de una consulta no puede estar entre sus candidatos. Los descartes se listan en `audit.json`.
4. **Muestreo.** Orden ascendente por SHA-256 de `semilla|partición|archivo` y corte al tamaño pedido: determinista, independiente del orden del sistema de archivos y estable por prefijo (ampliar el tamaño conserva los casos anteriores). Ids opacos `pa-<partición>-<nº>`; nunca nombres de archivo.
5. **Separación física.** La parte pública contiene solo `dxf/`, `agent_cases/<id>.zip`, `cases.json`, `manifest.json` y `SHA256SUMS`: DXF con capas `ORTHO_*`, sin textos, programa, `normal`, categoría ni BOM. La privada contiene `references.json` (componentes, hashes, `group_id`, familia, características), `audit.json`, `manifest.json`, `juicios/` y `SHA256SUMS`. Los juicios son privados porque son la respuesta de evaluación.
6. **Variantes empobrecidas** (`--poor-variants`, solo partición test): `solo_frontal` y `frontal_y_planta`, que eliminan vistas sin mover las restantes. Son casos con id `<base>-<tipo>`, `variant: "empobrecida"`, `poor_kind`, `variant_of` y `view_kind: assembled_orthographic_partial`. El generador no dibuja cotas ni textos, así que no hay cotas que quitar: la ausencia de cotas es la norma de este corpus.

### Formato del manifiesto

`manifest.json` público: `generator_version` (`plankassembly-corpus-1`), `seed`, `source_dataset`, `source_revision`, `partitions` (por partición: `requested`, `available_after_audit`, `sampled`), `complete_cases`, `poor_variant_cases`, `poor_variants`, `view_kind`, `inference_evaluated: false`, `redistribution_authorized: false`, `license_notice` y `cases_sha256`. El privado añade `source_split_sha256` (de cada lista oficial), `audit_summary`, `unlisted_json_excluded`, `sampled_without_normal`, `sampling`, `duplicate_policy`, `relevance_rule`, `judgments` (archivos, nº de consultas, consultas sin relevantes, contrato de biblioteca) y los hashes del manifiesto y de `cases.json` públicos. No hay marcas de tiempo: las mismas entradas dan los mismos bytes. `cases.json` público: `id`, `partition`, `file`, `format`, `unit`, `view_kind`, `variant`, `poor_kind`, `variant_of`, `sha256`, `instruction`.

### Juicios derivados

PlankAssembly **no tiene clase semántica** verificada, así que la regla es estructural. Para cada consulta de test y cada caso completo del corpus (salvo ella misma) calcula un grado 0/1/2 con características de la referencia privada: nº de tableros, envolvente ancho/fondo/alto en mm, histograma de horizontales y verticales inferido del eje más delgado de cada cuboide (no usa `normal`) y una familia. La familia es estructural (`perfil` alto/medio/bajo + `con_trasera`/`abierto`, con la suposición x=ancho, y=fondo, z=alto) salvo que se pase `--category-field` con un campo de categoría cuya existencia se haya verificado; entonces se usa su valor. Umbrales (`ReglaRelevancia`, también en `manifest.json` y en la `descripcion` de cada archivo): grado 2 = misma familia, envolvente a ≤10 % por eje, |Δtableros| ≤1 y L1 del histograma ≤2; grado 1 = no es 2, envolvente ≤25 %, |Δtableros| ≤3 y (misma familia o L1 ≤2); grado 0 = el resto.

- `juicios/juicios_test.json`: similitud graduada, `origen: "derived_reference"`, densa (`cobertura_juicios` 1,0). Si consultas × candidatos supera `--max-pairs` el generador falla. `--zeros-per-query N` conserva los grados ≥1 y los N ceros más cercanos: la cobertura baja, las métricas no cambian porque lo no juzgado cuenta como 0.
- `juicios/juicios_test_<tipo>.json`: consultas empobrecidas con los grados de su caso completo.
- `juicios/juicios_identidad_<tipo>.json`: tarea entre vistas. La consulta es la variante empobrecida y solo su mueble completo es relevante (grado 2, resto 0). Recoge la dificultad registrada por el laboratorio semántico (Hit@1 = 0,30 entre vistas del mismo mueble) en lugar de medir solo casos fáciles.

Los grados miden el acuerdo con esta regla, no la preferencia de un técnico. Un método que use las mismas magnitudes (dimensiones, número de piezas) queda favorecido por construcción, y no hay histórico económico. Antes de usarlos como evidencia hay que revisar una muestra por personas (`team_reviewed`, véase el README de `evaluation/recuperacion`).

### Contrato de la biblioteca para evaluar

`tools/evaluar_recuperacion.py` busca las consultas por id en la biblioteca. Para estos juicios: `LibraryItem.id` = id del caso, un único `descriptor_version`, `run_id` distinto por caso, y la biblioteca debe contener **todos los casos completos** (train, valid y test). Las variantes empobrecidas se añaden como consultas. En `juicios_test_<tipo>` la variante usa `run_id` = id de su caso base (el evaluador excluye así el propio mueble completo); en `juicios_identidad_<tipo>` su `run_id` debe diferir del de la base. El descriptor debe construirse a partir de la vista pública, no de `references.json`: usar la referencia daría al método información reservada.

### Limitaciones

- Verificado solo con fixtures sintéticos (`tests/test_plankassembly_corpus.py`). No se ha ejecutado con el dataset real ni se ha comprobado qué claves tienen sus JSON aparte de `planks`, `attach` y `normal`.
- El auditor de duplicados es heurístico (rejillas) y puede dejar pasar o sobreeliminar variantes.
- Los juicios densos crecen con consultas × candidatos.
- Las vistas son rectángulos de cuboides: sintéticas, no planos de fabricación.
