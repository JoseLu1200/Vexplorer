# Prueba de embeddings en otros datasets descargados

Fecha de ejecución: 2026-11-14.

## Objetivo y alcance

Esta prueba aplicó el espacio elegido en el laboratorio principal, EmbeddingGemma 2 mixed 768d, a tres corpus locales que ya estaban descargados. No hubo ajuste del encoder, selección de modelo, PCA ni búsqueda de umbrales. El experimento responde tres preguntas acotadas:

1. ¿Se conservan las categorías editoriales al ampliar CADBlock con clases distintas de las cuatro del piloto?
2. ¿El mismo objeto de PlankAssembly aparece cerca cuando se consulta desde otra vista ortográfica?
3. ¿Qué hace el clasificador cerrado de muebles ante dibujos de ingeniería fuera de dominio?

Los resultados de CADBlock no demuestran generalización a CAD industrial. Las categorías provienen de directorios del mismo sitio y actúan como etiquetas proxy. PlankAssembly mide identidad pública del objeto, no familia semántica. El corpus de ingeniería carece de una etiqueta correcta entre las cuatro clases de muebles, por lo que no admite una medida de accuracy.

## Prerregistro

El runner escribió `D:/Vexplorer-semantic-lab/cross-dataset/preregistration.json` antes de calcular métricas. SHA-256: `8ffdf3e0244ba64d4780d9288b8f3f9a0595e0a0884f437dfe22e7a78047cc2c`.

Protocolo congelado:

- modelo `google/embeddinggemma-2`, revisión `f9972ac22e696a105c482202646979e33e4b5a1e`;
- entrada `mixed`: render geométrico de 384 px y texto con seis observaciones globales, dentro del conjunto de 27 atributos numéricos disponibles;
- 768 dimensiones, inferencia bfloat16 y persistencia float32 normalizada L2;
- kNN con k=5, distancia coseno, pesos por distancia y sin PCA;
- semilla de partición 20261114;
- CAD-extra: train como índice fijo; validation y test como consultas separadas; macro-F1, balanced accuracy, P@5 y Hit@5;
- PlankAssembly: todas las vistas consultan contra las otras 29, sin autocoincidencia; Hit@1 y Hit@2 con relevancia definida como el mismo id público;
- ingeniería: kNN entrenado solo con el train del corpus principal de 117 muebles; se informa la asignación forzada, sin medir accuracy ni calibrar rechazo.

El runner comprueba el hash de cada manifiesto antes de puntuar. Los labels, ids, rutas, nombres de archivo y grupos no entran al modelo. Solo entran los bytes del render y el texto geométrico neutral.

## Corpus preparados

### CADBlock extra

Se encontraron 379 DXF en 17 directorios distintos de `sofas`, `simple-tables`, `beds` y `buffets`. `table-lamps` no contenía archivos. El extractor aceptó 373 dibujos repartidos en 16 clases y formó grupos antes del split. La partición congelada contiene 262 train, 56 validation y 55 test.

Seis archivos quedaron excluidos con su ruta, tipo de excepción y causa en el manifiesto:

- tres dibujos tenían geometría con Z distinto de cero;
- dos entidades `3DFACE` y una entidad `SOLID` provocaron `DXFAttributeError` al solicitar el atributo `v0`.

El runner captura el error por archivo y continúa con el resto del lote. No cambió el extractor principal para acomodar estos seis casos.

Hashes de manifiesto:

| Corpus | Filas | SHA-256 |
|---|---:|---|
| CAD-extra | 373 | `bac26796ab89d3f170cc2f5667a957ff86e527b8791873ba99df209b37d17bf4` |
| Plank views | 30 | `e31ca7900c93bf7f7758f84a092cb9b14d97b27e12ba540d883422cb067572eb` |
| Engineering DXF | 14 | `7372147f3968899befca71be89cf140fc3340f73451e71061a7794d5be5a09af` |

### PlankAssembly público

La prueba consumió solo los 10 DXF de `plankassembly_adapter_test_v1`. Para cada objeto generó tres archivos temporales fuera de Git, uno por `ORTHO_FRONT`, `ORTHO_SIDE` y `ORTHO_TOP`. No leyó artefactos privados ni oráculos. El `family_hash` no se usó como label, feature ni criterio de relevancia.

### Engineering pilot público

El extractor aceptó los 14 DXF de `engineering_evaluation_pilot_v3/agent_inputs`. Los tres PDF públicos quedaron registrados como exclusiones por formato. Esta ejecución no necesitaba rasterizarlos para responder la pregunta de comportamiento closed-set.

El bloque `historical_import` también quedó fuera: sus cuatro registros económicos exigirían una sonda textual distinta. Compararla con mixed CAD como si compartiera la misma tarea habría producido una cifra sin interpretación válida.

## Resultados observados

### CADBlock extra

| Split | n | Macro-F1 | Balanced accuracy | P@5 | Hit@5 |
|---|---:|---:|---:|---:|---:|
| Validation | 56 | 0.7261 | 0.7644 | 0.7643 | 0.9643 |
| Test | 55 | 0.7780 | 0.7719 | 0.7745 | 0.9273 |

El resultado indica que el embedding conserva bastante información de los proxies editoriales dentro de la misma fuente. No convierte esas carpetas en una taxonomía técnica y no mide transferencia entre proveedores de CAD.

Un replay posterior del mismo train, modelo y kNN congelados generó `D:/Vexplorer-semantic-lab/cross-dataset/diagnostics.json`, SHA-256 `73b669ce0e5adbed3e3f6fe9878923d20684512c590646070e4be107764326a3`. Este paso describe errores del test ya abierto; no selecciona ni ajusta nada. Las clases con menor recall fueron `trees-3d` 0/1, `dining-sets` 1/3, `bathroom-set` 1/2 y `bathtubs` 1/2. Los soportes de una a tres muestras impiden leer esas tasas como estimaciones estables por clase.

Los nueve errores fueron: bathroom-set→toilets, bathtubs→trees-plan, dining-sets→kitchen-sinks, dining-sets→living-room, living-room→kitchen-appliances, palm-trees→trees-elevation, sanitary-ware→toilets, trees-3d→trees-elevation y trees-elevation→living-room. Cada par ocurrió una vez. La matriz de confusión completa y su orden de labels están en el diagnóstico local y en el resumen versionado.

### PlankAssembly: recuperación del mismo objeto entre vistas

| Consultas | Hit@1 | Hit@2 |
|---:|---:|---:|
| 30 | 0.3000 | 0.3000 |

El top de las consultas front acertó en 5/10, side en 4/10 y top en 0/10. Para las diez consultas top, el vecino más cercano fue otra vista top. Hit@2 no mejoró Hit@1. La señal de orientación dominó a la identidad del objeto, sobre todo en planta. Esta sonda desaconseja usar el espacio mixed sin adaptación para vincular vistas ortográficas de una misma pieza.

Hit@1 es una tasa de acierto, no Recall@1. Cada consulta tiene dos vistas relevantes; llamar recall al indicador habría dado una definición incorrecta.

### Engineering: comportamiento closed-set fuera de dominio

| Clase de mueble impuesta | Conteo |
|---|---:|
| buffets | 11 |
| sofas | 2 |
| simple-tables | 1 |
| beds | 0 |

Las distancias coseno al vecino más próximo estuvieron entre 0.0678 y 0.1001. Esos valores describen la ejecución; no constituyen un umbral de rechazo. El experimento no miró estas 14 consultas para elegir un umbral. La concentración en `buffets` muestra el fallo esperado de un clasificador cerrado: asigna una categoría de mueble incluso cuando ninguna de las cuatro opciones es una respuesta válida.

## Artefactos e integridad

El informe local está en `D:/Vexplorer-semantic-lab/cross-dataset/report.json`, SHA-256 `51f238e4f0bd91b97304231564a750cb85c45b1bd779168bd3629a52255926f2`. Los pesos, renders y NPZ no se incorporan a Git.

El resumen compacto versionable está en `docs/experiments/cross-dataset-2026-11-14/embeddings-summary.json`. Contiene hashes, protocolo, métricas, exclusiones, matriz de confusión, asignaciones forzadas y el registro de cero eventos OOM. Omite rutas de entrada, nombres personales y hashes por muestra.

| NPZ | Forma | SHA-256 | Tiempo de encoding |
|---|---:|---|---:|
| CAD-extra | 373 x 768 | `4c34c4d94724eb9d13744faf7b1a4207fe7ad8ceece0e7960a2b81a0bd33f02c` | 71.129 s |
| Plank views | 30 x 768 | `7a4752bacc03077b078bb6de218e8d281d0885c89a7d1b33c440e4254e4b250e` | 6.766 s |
| Engineering | 14 x 768 | `209ca716175007c8cd500103be02601b74667c1654b34384d91972fd02cb22a0` | 3.028 s |

Las tres matrices contienen ids únicos, valores finitos y dtype float32. El intervalo observado de normas L2 fue 0.999999881–1.000000119. La ejecución usó una NVIDIA GeForce RTX 5070 Ti Laptop GPU con 12 227 MiB y driver 591.86. Los tiempos miden la codificación de cada corpus y excluyen la carga del checkpoint.

## Reproducción

Preparación y prerregistro, sin abrir métricas:

```powershell
$SemanticDatasetRoot = 'C:/datasets'
python -m tools.semantic_lab.probe_datasets prepare `
  --cadblock-source "$SemanticDatasetRoot/cadblock_2d" `
  --plank-source "$SemanticDatasetRoot/plankassembly_adapter_test_v1" `
  --engineering-source "$SemanticDatasetRoot/engineering_evaluation_pilot_v3/agent_inputs" `
  --output-root "D:/Vexplorer-semantic-lab/cross-dataset-reproduction"
```

Puntuación después de publicar el hash del prerregistro:

```powershell
& "D:/Vexplorer-semantic-lab/venv/Scripts/python.exe" `
  -m tools.semantic_lab.probe_datasets score `
  --preregistration "D:/Vexplorer-semantic-lab/cross-dataset-reproduction/preregistration.json" `
  --output-root "D:/Vexplorer-semantic-lab/cross-dataset-reproduction" `
  --cache-dir "D:/Vexplorer-semantic-lab/hf-cache" `
  --core-manifest "D:/Vexplorer-semantic-lab/data/core/manifest.json" `
  --core-embeddings "D:/Vexplorer-semantic-lab/embeddings/embeddinggemma2-mixed-768.npz"
```

Pruebas sin red ni descarga:

```powershell
python -m pytest tests/test_semantic_lab_probe_datasets.py -q
```

La investigación de modelos y métodos relacionados permanece separada en [INVESTIGACION_SOTA.md](INVESTIGACION_SOTA.md). Esta página registra solo lo ejecutado en los corpus adicionales.
