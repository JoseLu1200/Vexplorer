# Reconstrucción desde planos pobres: comparación final

Fecha: 2026-11-14. Rama aislada `feat/reconstruction-3d`, base `affe009`.

**Decisión: priorizar el montaje paramétrico inferido y sus vistas. No incorporar Idol como paso obligatorio del harness, del despiece o del presupuesto.** En este diagnóstico Idol no reconstruye correctamente el objeto desde la lámina ortográfica. Alimentado con el render del harness ofrece una representación visual reconocible, pero no añade componentes identificables ni escala y degrada la similitud geométrica y la recuperación respecto a B. Es una conclusión sobre esta configuración y seis casos, no sobre todas las capacidades de Idol.

## Qué se ejecutó

| Variante | Entrada disponible | Salidas reales |
|---|---|---:|
| A | Plano pobre: alzado y lateral, una cota de anchura | 6 splats |
| B | Exactamente el mismo plano; harness estructurado y revisión de su render | 6 montajes por componentes |
| C | Render de B congelado | 6 splats |
| D | Render del original reservado | 6 splats; control privilegiado |

Se inspeccionaron visualmente los 24 resultados desde seis ángulos, además del despiece de B. No se entregó al modelo el despiece ni el 3D de referencia para A/B/C. D sí los aprovecha mediante un render y nunca se cuenta como reconstrucción desde plano pobre.

Tres casos son fixtures propios de mobiliario plausible: mesa, estantería y mueble bajo con compartimentos. Los otros tres son las geometrías PlankAssembly cuestionadas inicialmente por el usuario, reclasificadas como controles ambiguos. Su referencia geométrica no acredita que sean muebles completos, funcionales o fabricables. Tampoco los fixtures propios certifican cargas o uniones. No es un test industrial ciego ni una muestra representativa.

Idol base: 50 pasos, semilla 42, 32768 gaussianas, modo synthetic, CFG predeterminado, optimización desactivada. RTX 5070 Ti **Laptop de 12 GB**, PyTorch 2.10.0+cu128. No se probó Turbo ni otras semillas/densidades. Pesos y SDK fijados; VAE FLUX.2-klein-4B como sustitución accesible admitida por el SDK. No se afirma equivalencia experimental con FLUX.2-dev.

## Geometría y despiece

IoU es intersección/unión de siluetas: 1 significa coincidencia. Para splats se usa un renderizador diagnóstico ortográfico de gaussianas anisotrópicas con transparencia, umbral alfa 0,5 y normalización independiente de envolventes. Se permite elegir una de cuatro rotaciones alrededor de Z usando únicamente las dos siluetas correspondientes a vistas de entrada. Es alineación del evaluador, no recuperación de cámara ni escala física. B usa su orientación original y un rasterizador de triángulos. Estas diferencias de representación/renderizado limitan la comparación numérica.

| Caso | B: piezas / referencia | B: IoU vistas reservadas | A: IoU | C: IoU | D: IoU |
|---|---:|---:|---:|---:|---:|
| 01 Mesa | 9 / 9 | 0,983 | 0,118 | 0,925 | 0,919 |
| 02 Estantería | 7 / 7 | 1,000 | 0,203 | 0,785 | 0,766 |
| 03 Mueble bajo | 6 / 6 | 1,000 | 0,159 | 0,881 | 0,889 |
| 04 Escritorio ambiguo | 12 / 11 | 1,000 | 0,200 | 0,838 | 0,805 |
| 05 Marco ambiguo | 3 / 3 | 1,000 | 0,119 | 0,806 | 0,806 |
| 06 Carcasa ambigua | 12 / 4 | 0,831 | 0,207 | 0,584 | 0,553 |
| Media descriptiva | — | **0,969** | **0,168** | **0,803** | **0,790** |

**Coincidir en silueta no equivale a recuperar el despiece.** Los tres fixtures completos recuperan la envolvente en mm y el número de piezas, pero las dimensiones internas difieren: MAE de dimensiones emparejadas 1,48 / 2,86 / 1,78 mm. El emparejamiento minimiza diferencias de tamaños y no valida identidad semántica, posición o unión. La IoU de volumen material de cuboides, alineada sólo por traslación, baja a 0,828 / 0,756 / 0,850. Una silueta de 1,000 puede ocultar espesores o construcciones diferentes.

La única cota explícita es la anchura. Altura, profundidad y secciones son inferencias, aunque coincidan con el fixture. El generador suministra vistas limpias a escala uniforme; el harness asume esa relación. No extrapolar precisión a planos escaneados, vistas a distinta escala o cotas contradictorias. La métrica de vistas de entrada compara siluetas proyectadas de la referencia, no todas las líneas ni las anotaciones originales. No se midieron tolerancias de fabricación o precisión de superficies CAD.

La revisión final añadió distancia simétrica media entre **bordes de silueta**, normalizada por el ancho de imagen: B 0,00465; A 0,07785; C 0,02181; D 0,02287, promediando vistas reservadas y casos. Menor es mejor. Usa la misma alineación que IoU y no mide líneas internas/cotas del plano. Los valores ampliados están en `evaluation-reviewed.json`; `evaluation-final.json` se conserva sin sobrescribir.

Los controles ambiguos no tienen un único despiece funcional correcto: añadir una puerta al caso 04 o completar la carcasa 06 cambia la construcción. Sus diferencias de piezas se muestran descriptivamente y no se convierten en una puntuación de BOM correcta/incorrecta. A/C/D tienen BOM y dimensiones físicas **no evaluables**, no cero piezas.

## Inspección visual y comportamiento ante incertidumbre

- A: en los seis casos reproduce principalmente las vistas como figuras planas o separadas, con restos de cotas/texto. No unifica la lámina en un único mueble. BiRefNet elimina el papel y el SDK compone sobre negro; las líneas negras quedan casi negras sobre negro. El resultado refleja el pipeline completo probado, no aísla el efecto del denoiser. No se probó una ablación conservando el fondo del plano.
- B: mesa, estantería y mueble bajo tienen huecos, apoyos y componentes interpretables. No se detectaron solapes ni piezas desconectadas en las seis propuestas congeladas. Eso no verifica estabilidad, ergonomía o herrajes.
- C/D: conservan categorías reconocibles y varias caras, pero cambian proporciones, redondean bordes y generan manchas/discontinuidades en cantos. En el escritorio y la carcasa las caras ocultas no mantienen necesariamente la construcción de entrada. No crean un despiece trazable.
- B v1 justificaba el marco 05 mediante una instalación a pared asumida y completaba 06 con elementos y bloques de herraje no determinados por el plano. Se conserva este fallo. Un ajuste posterior del prompt prohíbe resolver esas dudas inventando función o conexiones; en pruebas reales posteriores **ambos casos se abstienen y piden uso/restricciones**. Son comprobaciones posteriores sobre casos conocidos, no una mejora validada en un test independiente. C usa siempre B v1 congelado.
- Controles adicionales reales: imagen vacía → insufficient_evidence; plano sin escala → relative, sin exportación métrica; una sola vista frontal acotada → propuesta con profundidad explícitamente supuesta.

## Recuperación y comprensión

EmbeddingGemma2 real, revisión `f9972ac22e696a105c482202646979e33e4b5a1e`, imágenes sin etiquetas ni nombres, vectores normalizados de 768 dimensiones. Galería de seis vistas reservadas, una por objeto. La consulta generada promedia seis vistas; el plano fuente es una sola imagen.

| Consulta | Hit@1 | MRR |
|---|---:|---:|
| Plano original | 2/6 | 0,569 |
| A | 1/6 | 0,528 |
| B | **6/6** | **1,000** |
| C | 5/6 | 0,917 |
| D, privilegiada | 6/6 | 1,000 |

Control con sólo la vista 0 por representación: B 5/6, C 4/6, A 2/6, D 5/6. Por tanto no aparece ventaja adicional de C en ninguno de los dos protocolos. La galería contiene el mismo objeto sintético desde otra vista, e incluso vistas muy próximas a B; no son históricos reales con costes. No hay significación estadística, entrenamiento ni evidencia de mejora de presupuestaje. Las distintas resoluciones y renderizadores también pueden influir.

Jev 1.14.0: 30 consultas válidas después de normalizar **todas** las imágenes a 512×512 con proporciones conservadas y relleno blanco. Los 18 errores HTTP 400 iniciales de splats de 256 px se conservan; el servidor indicó `Invalid image dimensions`. La normalización no es generación de detalle.

| Entrada | Categorías abiertas, casos 01 a 06 |
|---|---|
| Fuente | table, shelving, low_cabinet, table, frame, low_cabinet |
| B | table, shelving, low_cabinet, table, frame, low_cabinet |
| A | frame, shelving, low_cabinet, UNKNOWN, frame, UNKNOWN |
| C | table, shelving, low_cabinet, table, frame, frame |
| D | table, shelving, low_cabinet, table, frame, frame |

En los tres fixtures de función conocida: fuente/B/C/D 3/3 y A 2/3. Los tres controles ambiguos no tienen etiqueta funcional verificada; sus respuestas se comparan sin atribuirles exactitud. Jev no muestra mejora de clasificación de C frente a B o la fuente. Esta tarea mide categoría gruesa, no comprensión integral, conteo de piezas ni factibilidad física.

## Coste local y decisión de producto

Media por inferencia Idol: A 160 s, C 173 s, D 206 s. Hay efectos de calentamiento, orden y carga del equipo: no son una comparación controlada de velocidad entre entradas. Primeros intentos fallaron por memoria comprometida de Windows; se resolvió con espacio disponible y carga secuencial de tensores, sin cuantización. La memoria asignada/reservada de PyTorch se registra por caso y no equivale al consumo total observado por nvidia-smi.

El incremento útil es **plano → propuesta estructurada → comprobaciones → vistas/despiece/GLB → preguntas o propuesta condicionada**. Los registros de recuperación generados llevan `is_observed_evidence: false` y `generated_design_hypothesis`; no reemplazan fuentes, BOM confirmadas ni precios históricos. No se indexan automáticamente en producción.

Idol puede mantenerse como vista experimental opcional si se busca apariencia. En esta muestra no justifica su latencia como paso necesario de inferencia o recuperación. Antes de adoptarlo harían falta planos reales con varias escalas, referencias funcionales verificadas, más semillas, otras densidades, pruebas de preprocesado y evaluación independiente de completitud. No se ha medido ahorro de tiempo humano ni precisión económica.

## Evidencias y reproducción

Artefactos locales: `D:/Vexplorer-idol-study/experiment-v1/`. `four-arm-comparison.png`, `all-views-case-01.png` a `06`, `evaluation-final.json`, `retrieval-final/report.json`, `retrieval-final/single-view-control.json`, `jev-normalized/`, `stress/`, manifiesto público, hashes y predicciones B originales. Las imágenes/datos derivados de terceros permanecen fuera de Git.

Integridad: se comprobaron los hashes guardados de 187 archivos de B/splats y las seis entradas, sin discrepancias. La revisión detectó que las referencias privadas no tenían inventario previo: se capturaron **149 hashes durante la revisión posterior**, identificados como `post_execution_review`. Ese inventario permite detectar cambios futuros, pero no demuestra retrospectivamente que la referencia no cambiara desde antes de inferir. El preparador actual congela referencias antes de inferencia y el evaluador rechaza diferencias o archivos añadidos. Esta limitación histórica se conserva en las métricas agregadas; no se presenta como un benchmark íntegramente pre-registrado.

Revisión independiente: seis hallazgos importantes corregidos con pruebas. El servicio entrega el prompt también dentro de cada solicitud, incluso con proveedor inyectado; los fallos conservan la primera propuesta consultable; los metadatos sólo autorizan `input` como referencia; varias vistas llevan separadores, etiquetas y límites; se añadió error de bordes e inventario privado verificable. Queda un detalle menor: los textos de nombre/uso compuestos sólo por espacios todavía pasan la validación de longitud. No afecta a las predicciones evaluadas y se deja documentado.

SDK `speridlabs/idol-sdk` commit `8db700349a5570aac390e4780fa32e3eed6b587a`. Pesos Idol `2731c2291fc65a797c5cb627a5e5526fc1490902`, DINOv3 `c807c9eeea853df70aec4069e6f56b28ddc82acc`, VAE Klein `e7b7dc27f91deacad38e78976d1f2b499d76a294`. Dependencias experimentales en `tools/reconstruction3d/requirements-idol-windows.txt`, separadas del entorno de la app. El modelo admite una imagen y produce gaussianas PLY, no sólidos ni piezas CAD: [modelo oficial](https://huggingface.co/speridlabs/idol), [SDK oficial](https://github.com/speridlabs/idol-sdk).

Desde la raíz de esta rama:

```powershell
python -m tools.reconstruction3d.dataset --help
python -m tools.reconstruction3d.run B --root <experimento-nuevo> --env-file <config-local> --model gpt-6.1-sol
<python-idol> -m tools.reconstruction3d.run idol --root <experimento> --model-paths <model-paths.json>
python -m tools.reconstruction3d.splats --root <experimento>
python -m tools.reconstruction3d.evaluate --root <experimento> --output <informe-nuevo.json>
python -m tools.reconstruction3d.gallery --root <experimento>
<python-semantic> -m tools.reconstruction3d.retrieval --root <experimento> --output <directorio-nuevo> --cache <cache-modelo> --device cuda
python -m tools.reconstruction3d.jev --root <experimento> --credential-file <config-local> --normalized
python -m tools.reconstruction3d.preview --study <experimento> --data <datos-visor-aislados> --port 8873
```

La aplicación añade `POST /api/v1/runs/{run_id}/reconstruction`, consulta de trabajo y descarga de artefactos. Se accede desde **Construcción propuesta** para un run de mueble general. El visor de estudio sirve la galería en `/study/`; es un recurso local del evaluador, no una entrada de inferencia. La prueba congelada usó el prompt guardado en `frozen-harness-prompt.txt`; el prompt actual incluye la corrección posterior de abstención, por lo que una nueva ejecución no reproduce B v1 literalmente.
