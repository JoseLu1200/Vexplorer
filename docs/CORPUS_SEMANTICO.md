# Corpus semántico sintético reservado

## Propósito y límite

Este corpus prueba lectura semántica de mobiliario desde vistas ortográficas pobres: BOM por rol, ocurrencias físicas, relaciones de montaje y alternativas compatibles con la geometría visible. Los diseños y sus referencias son sintéticos propios y se certifican como `design_known_synthetic`; no son verdad independiente revisada por técnicos ni planos de fabricación industriales.

La versión activa v2 crea 80 escenarios a partir de **16 diseños/topologías independientes**: 10 topologías y 50 casos de desarrollo, 6 topologías y 30 casos reservados. Cada topología produce cinco perfiles de evidencia; esos 80 casos no son 80 diseños. Hay seis familias (`shelving`, `table`, `cabinetry`, `workspace`, `seating` y `storage`). La unidad de separación es el proyecto/topología estructural (`project_id` y `structural_signature`), no la etiqueta de producto. Todas las vistas de un diseño quedan en un solo split y ninguna firma estructural cruza entre desarrollo y reservado.

Las topologías incluyen estanterías abiertas, de escalera y de carriles; mesas de caballete y pedestal; armarios con puertas, cajones, frentes correderos y barra; escritorios rectos y en esquina; banco con cubículos; taburete y sillón. La diversidad procede de grafos de roles y ocurrencias distintos, no de escalar tres modelos base.

Resumen agregado, calculado desde las especificaciones del generador sin abrir respuestas por caso: 134 ocurrencias en los 16 diseños (3–13 por diseño, media 8,38 y mediana 9; 670 exposiciones al contar las cinco vistas), 66 relaciones de diseño (2–7 por topología), de las que 20 son observables obligatorias y 46 uniones ocultas opcionales. La dificultad por caso queda en 7 `easy`, 35 `medium` y 38 `hard`.

## Contraste de fuentes públicas

- [PlankAssembly (publicador)](https://github.com/manycore-research/PlankAssembly) es la referencia más próxima para reconstrucción de muebles de tableros desde tres vistas ortográficas. Su programa paramétrico no aporta por sí solo roles funcionales fiables ni alternativas de montaje, y sus condiciones de datos se mantienen separadas.
- [IKEA 3D Assembly Dataset (IKEA)](https://github.com/IKEA/IKEA3DAssemblyDataset) aporta modelos por piezas e instrucciones de cinco productos. Es útil para confirmar la distinción entre ocurrencia manipulable y objeto final, pero es demasiado pequeño y su licencia CC BY-NC-SA 4.0 no justifica copiarlo a este benchmark propio.
- [Fusion 360 Gallery Assembly Dataset (Autodesk)](https://github.com/AutodeskAILab/Fusion360GalleryDataset/blob/master/docs/assembly.md) aporta jerarquía, contactos y conectividad, y su [subconjunto de joints](https://github.com/AutodeskAILab/Fusion360GalleryDataset/blob/master/docs/assembly_joint.md) formaliza relaciones entre pares de piezas. Es un corpus CAD general pesado, no un conjunto directo de planos pobres de mobiliario con roles funcionales.

La ruta práctica elegida es generar diseños propios. No se importa geometría, nombre, malla, programa ni anotación de esas fuentes. Así se controlan licencia, particionado, roles y ambigüedad sin presentar datos sintéticos como validación humana.

## Frontera pública estricta

Cada caso público es un ZIP opaco con solo:

- `input.dxf`: líneas sin texto, bloques ni nombres semánticos; capas permitidas `V0`, `V1`, `V2` y `N0`.
- `case.json`: exactamente `id`, `file`, `format`, `unit`, `view_kind`, `instruction` y `sha256`, compatible con `tools.run_general_benchmark`.

Los IDs `sx-NNN` no codifican clase, proyecto, split ni variante. El bundle no contiene BOM, roles, cantidades, firma, perfil de vista, relaciones, alternativas ni identificadores privados. El runner debe recibir exclusivamente este directorio y usar `--strict-bundles`.

## Referencia privada offline v2

La referencia separada enlaza por `scenario_id`, igual al `id` público opaco. Cada escenario conserva privadamente:

- split, proyecto, clase de producto, firma topológica y perfil de vista;
- componentes agregados por rol con cantidad y alias;
- ocurrencias físicas con cuboide en mm;
- verdad de diseño para relaciones `fixed_to`, `supported_by` o `hinged_to` entre roles;
- una alternativa de método de unión que produce el mismo contorno visible, nunca una pieza oculta opcional;
- ambigüedad explícita por par de roles, dificultad y unknowns esperables, con certificación sintética.

La verdad de diseño y la tarea observable están separadas. Un contacto entre rectángulos proyectados no permite distinguir tornillos, cola, espigas o bisagras ocultas. Por eso `fixed_to` y `hinged_to` permanecen en `assembly_relations` para auditar el diseño, pero llevan `required: false` y un scope `assembly_relation:<subject>:<object>` que acepta `unknown`. `supported_by` puede ser obligatorio cuando la disposición aporta evidencia directa de soporte. El informe debe mostrar verdad total, subconjunto observable y cobertura/abstención por separado; no debe borrar silenciosamente las uniones no observables.

`design_geometry.evaluation_annotations` es privado y contiene `difficulty` (`easy|medium|hard`), `expected_unknowns` y `evidence_scope: orthographic_outlines_only`. No se entrega al runtime.

El evaluador alinea por roles/etiquetas normalizados, no por IDs de ocurrencia privados. Las predicciones se congelan antes de abrir esta referencia. El directorio privado no se copia al repositorio, al runtime, al directorio público ni a los prompts.

`references.json` no es todavía un envelope evaluable. Después de congelar un manifiesto de predicciones, el evaluador lo sella por lote:

```powershell
python -m tools.seal_semantic_reference `
  --private-reference <directorio-privado-existente> `
  --predictions <predicciones-congeladas.json>
```

El valor por defecto es v2 (`semantic-furniture-synthetic-v2`). La generación v1 congelada sigue disponible para reproducibilidad histórica añadiendo `--corpus-version v1` y dos destinos nuevos.

La compatibilidad v1 se comprueba byte a byte contra un snapshot del generador original con `PYTHONHASHSEED=0`; fijar la semilla es necesario porque el orden de registro de clases de `ezdxf` puede variar entre procesos aunque la geometría sea idéntica.

El sello por lote `evaluation-reference-<hash>.json` registra el SHA-256 exacto de esas predicciones, `frozen_before_evaluation: true`, visibilidad `evaluator_only` y unidad de partición `project_id+structural_signature`. Acepta un subconjunto no vacío (por ejemplo, humo o reservado), conserva casos fallidos y rechaza IDs duplicados/ajenos, hashes de entrada distintos, otro dataset o un segundo sellado del mismo lote.

## Generación reproducible

Desde la raíz del repositorio, indicando dos destinos nuevos y físicamente separados:

```powershell
python -m tools.prepare_semantic_corpus `
  --public-output <directorio-publico-nuevo> `
  --private-output <directorio-privado-nuevo>
```

El comando rechaza destinos existentes, iguales o anidados. Usa metadatos DXF y ZIP fijos, escribe primero en staging y renombra al terminar. Cada salida incluye `SHA256SUMS`; los manifiestos privados enlazan el hash del manifiesto público y de las referencias.

## Invariantes verificadas

`tests/test_prepare_semantic_corpus.py` comprueba:

- recuento 50/30, 16 proyectos/firmas y cinco perfiles por proyecto, con topologías y proyectos disjuntos por split;
- firmas visibles normalizadas de las tres proyecciones disjuntas entre las 10 topologías de desarrollo y las 6 reservadas, ignorando roles y uniones privadas;
- al menos seis familias sin afirmar que sean clases reservadas;
- dimensiones positivas y ausencia de interpenetración volumétrica entre cuboides; el contacto en frontera sí es válido;
- igualdad entre cantidades BOM y ocurrencias, y extremos de relaciones existentes;
- alternativas no vacías limitadas a montaje visualmente indistinguible;
- uniones ocultas conservadas como verdad de diseño pero no obligatorias, con ambigüedad por par;
- dificultad y unknowns esperables presentes solo en la referencia privada;
- DXF en mm, vistas pobres controladas, ausencia de texto/bloques/capas semánticas y hashes únicos;
- cajas globales de `V0`, `V1` y `V2` separadas al menos 100 mm en todos los casos; el gate incluye un fixture rectangular 800×320 que reproduce el solapamiento heredado;
- ZIP aceptados por `load_public_sources(..., strict_bundles=True)`;
- reproducibilidad byte a byte y separación de destinos.

La cohorte principal reservada son 30 casos: `sx-041`–`sx-045` y `sx-056`–`sx-080`, correspondientes a seis topologías v2 completamente nuevas. Los tres diseños que fueron reservados en v1 (`hold-ladder`, `hold-pedestal` y `hold-wall-single`) pasan a desarrollo/regresión y nunca forman parte del holdout v2. Los smoke de desarrollo son diagnóstico y se excluyen del informe principal. Una comparación original/corregida usa exactamente esos 30 IDs, presupuesto, modelo y scoring v2.

Estas comprobaciones validan el diseño conocido y la higiene del benchmark. No demuestran inferencia correcta, fabricabilidad, herrajes concretos, mecanizados, tolerancias ni generalización a planos reales. En particular, no convierten contacto o coincidencia de proyecciones en evidencia de `fixed_to`.

La revisión de inputs vigente es rev3. Mantiene IDs y topologías, pero corrige las coordenadas globales de las vistas ortográficas. El SHA de `manifest.json` no cambia porque ese manifiesto describe el dataset y no enumera bundles; para distinguir revisiones de inputs se usa el SHA-256 de `public/SHA256SUMS`.

### Erratum de referencia rev4

Después de iniciar la inferencia rev3 y de inspeccionar el smoke de desarrollo `sx-001`, pero antes de inspeccionar predicciones semánticas o scores del holdout, una revisión del código detectó que la alternativa de fijación eliminaba por error la relación base `supported_by` del mismo par. Ningún contenido semántico holdout se usó para formar el erratum. Apoyo y fijación pueden coexistir: rev4 conserva todas las relaciones base, incluido soporte obligatorio, y añade `fixed_to` como método opcional no observable. No se presenta esta corrección como anterior a la salida del modelo.

Los 82 archivos públicos de `semantic-v2-20261114-rev4-reference-erratum/public` son una copia literal de rev3 (`public_diff_count=0` y el mismo SHA de `SHA256SUMS`). No se regeneraron porque el orden de serialización de clases de `ezdxf` puede variar con `PYTHONHASHSEED`. Por tanto no se repite inferencia; el informe debe distinguir explícitamente «inputs/inferencia rev3» de «referencia corregida rev4» y puede mostrar, por transparencia, el resultado con la referencia rev3 previa separado del scoring final del erratum.

`reference-erratum-audit.json` compara ambas referencias sin predicciones: 80 alternativas, cero relaciones eliminadas, 80 adiciones `supported_by|required=true` y cero cambios fuera de las alternativas.

El generador v2 futuro corrige también la causa de reproducibilidad: registra todas las clases requeridas y ordena canónicamente `document.classes.classes` antes de exportar. Una prueba ejecuta el CLI completo en subprocesos con `PYTHONHASHSEED=1` y `4` y exige árboles públicos y privados byte-idénticos. Esta corrección de tooling no modifica los artefactos congelados rev3/rev4; v1 mantiene su serialización histórica.
