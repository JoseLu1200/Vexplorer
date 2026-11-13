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
