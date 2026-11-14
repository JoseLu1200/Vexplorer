# Corpus semántico sintético reservado

## Propósito y límite

Este corpus prueba lectura semántica de mobiliario desde vistas ortográficas pobres: BOM por rol, ocurrencias físicas, relaciones de montaje y alternativas compatibles con la geometría visible. Los diseños y sus referencias son sintéticos propios y se certifican como `design_known_synthetic`; no son verdad independiente revisada por técnicos ni planos de fabricación industriales.

El generador crea 18 escenarios: 12 de desarrollo y 6 reservados. Hay tres clases de producto en ambos splits. La unidad de separación es el proyecto/topología estructural (`project_id` y `structural_signature`), no la etiqueta de producto. Todas las variantes de vista de un diseño quedan en un solo split y ninguna firma estructural cruza entre desarrollo y reservado. Por tanto, «reservado» significa diseño/topología no visto, no familia de producto no vista.

## Contraste de fuentes públicas

- [PlankAssembly (publicador)](https://github.com/manycore-research/PlankAssembly) es la referencia más próxima para reconstrucción de muebles de tableros desde tres vistas ortográficas. Su programa paramétrico no aporta por sí solo roles funcionales fiables ni alternativas de montaje, y sus condiciones de datos se mantienen separadas.
- [IKEA 3D Assembly Dataset (IKEA)](https://github.com/IKEA/IKEA3DAssemblyDataset) aporta modelos por piezas e instrucciones de cinco productos. Es útil para confirmar la distinción entre ocurrencia manipulable y objeto final, pero es demasiado pequeño y su licencia CC BY-NC-SA 4.0 no justifica copiarlo a este benchmark propio.
- [Fusion 360 Gallery Assembly Dataset (Autodesk)](https://github.com/AutodeskAILab/Fusion360GalleryDataset/blob/master/docs/assembly.md) aporta jerarquía, contactos y conectividad, y su [subconjunto de joints](https://github.com/AutodeskAILab/Fusion360GalleryDataset/blob/master/docs/assembly_joint.md) formaliza relaciones entre pares de piezas. Es un corpus CAD general pesado, no un conjunto directo de planos pobres de mobiliario con roles funcionales.

La ruta práctica elegida es generar diseños propios. No se importa geometría, nombre, malla, programa ni anotación de esas fuentes. Así se controlan licencia, particionado, roles y ambigüedad sin presentar datos sintéticos como validación humana.

Las recetas de desarrollo pueden vivir en el preparador para depurar la tubería. Las recetas reservadas reales no viven en Git, tests, release ni runtime: permanecen como especificación JSON en custodia externa privada. El preparador contiene solo la lógica genérica y exige esa especificación mediante ruta explícita. Los tests construyen diseños privados de desarrollador distintos; no replican valores del holdout.

## Frontera pública estricta

Cada caso público es un ZIP opaco con solo:

- `input.dxf`: líneas sin texto, bloques ni nombres semánticos; capas permitidas `V0`, `V1`, `V2` y `N0`.
- `case.json`: exactamente `id`, `file`, `format`, `unit`, `view_kind`, `instruction` y `sha256`, compatible con `tools.run_general_benchmark`.

Los IDs `sx-NNN` no codifican clase, proyecto, split ni variante. El bundle no contiene BOM, roles, cantidades, firma, perfil de vista, relaciones, alternativas ni identificadores privados. El runner debe recibir exclusivamente este directorio y usar `--strict-bundles`.

## Referencia privada offline v1

La referencia separada enlaza por `scenario_id`, igual al `id` público opaco. Cada escenario conserva privadamente:

- split, proyecto, clase de producto, firma topológica y perfil de vista;
- componentes agregados por rol con cantidad y alias;
- ocurrencias físicas con cuboide en mm;
- relaciones `fixed_to`, `supported_by` o `hinged_to` entre roles;
- una alternativa de método de unión que produce el mismo contorno visible, nunca una pieza oculta opcional;
- ambigüedad explícita y certificación sintética.

El evaluador alinea por roles/etiquetas normalizados, no por IDs de ocurrencia privados. Las predicciones se congelan antes de abrir esta referencia. El directorio privado no se copia al repositorio, al runtime, al directorio público ni a los prompts.

`references.json` no es todavía un envelope evaluable. Después de congelar un manifiesto completo para la cohorte seleccionada (los 18 casos o cualquier subconjunto no vacío), el evaluador lo sella una sola vez. «Completo» significa que conserva todos los IDs seleccionados, incluidos los casos fallidos como predicción vacía con desconocidos; no exige incluir siempre los 18:

```powershell
python -m tools.seal_semantic_reference `
  --private-reference <directorio-privado-existente> `
  --predictions <predicciones-congeladas.json>
```

El sello por lote `evaluation-reference-<hash>.json` registra el SHA-256 exacto de esas predicciones, `frozen_before_evaluation: true`, visibilidad `evaluator_only` y unidad de partición `project_id+structural_signature`. Acepta un subconjunto no vacío (por ejemplo, humo o reservado), conserva casos fallidos y rechaza IDs duplicados/ajenos, hashes de entrada distintos, otro dataset o un segundo sellado del mismo lote.

## Generación reproducible

Desde la raíz del repositorio, indicando dos destinos nuevos y físicamente separados:

```powershell
python -m tools.prepare_semantic_corpus `
  --public-output <directorio-publico-nuevo> `
  --private-output <directorio-privado-nuevo> `
  --private-design-spec <especificacion-reservada-externa.json>
```

El comando rechaza destinos existentes, iguales o anidados, y no tiene un holdout incorporado por defecto. Usa metadatos DXF y ZIP fijos, escribe primero en staging y renombra al terminar. Cada salida incluye `SHA256SUMS`; los manifiestos privados enlazan el hash del manifiesto público y de las referencias. La custodia privada registra por separado el SHA-256 de la especificación y del código de preparación para reproducibilidad sin publicar el oráculo.

Antes de empaquetar código se ejecuta una auditoría contra la especificación privada:

```powershell
python -m tools.audit_semantic_oracle_absence `
  --private-design-spec <especificacion-reservada-externa.json> `
  --source-root tools --source-root tests --source-root backend `
  --source-root evaluation --source-root frontend --source-root docs
```

La auditoría busca IDs exactos de proyectos privados y combinaciones de fragmentos geométricos/relacionales exactos. Un hash ausente no se usa como supuesto sustituto de inspeccionar el texto fuente.

## Invariantes verificadas

`tests/test_prepare_semantic_corpus.py` comprueba:

- recuento 12/6 y seis proyectos, con topologías y proyectos disjuntos por split;
- tres clases de producto sin afirmar que sean clases reservadas;
- dimensiones positivas y ausencia de interpenetración volumétrica entre cuboides; el contacto en frontera sí es válido;
- igualdad entre cantidades BOM y ocurrencias, y extremos de relaciones existentes;
- alternativas no vacías limitadas a montaje visualmente indistinguible;
- DXF en mm, vistas pobres controladas, ausencia de texto/bloques/capas semánticas y hashes únicos;
- ZIP aceptados por `load_public_sources(..., strict_bundles=True)`;
- reproducibilidad byte a byte y separación de destinos.
- ausencia de recetas privadas exactas en árboles de fuente mediante una prueba positiva que demuestra que el auditor detecta una fuga sembrada.

Estas comprobaciones validan el diseño conocido y la higiene del benchmark. No demuestran inferencia correcta, fabricabilidad, herrajes concretos, mecanizados, tolerancias ni generalización a planos reales.
