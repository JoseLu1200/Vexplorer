# Comparación real con Jev 1.14

Fecha: 2026-11-14. Esta comparación es **retrospectiva y post-hoc**: los conjuntos de
validation y test ya se habían abierto en experimentos anteriores. El protocolo de
Jev se fijó antes de consultar sus métricas, pero esta ejecución no crea un nuevo test
ciego.

## Corrección sobre la API vigente

El repositorio histórico inspeccionado inicialmente utilizaba Jev 1.13 solo sobre texto
OCR. Esa integración no describe todas las capacidades actuales del proveedor. La
documentación vigente indica que Jev 1.13 y 1.14 aceptan texto e imágenes; Jev 1.14 se
identifica como `jev-1.14.0`. Las imágenes requieren el encabezado
`TypeSafe-Danger-Zone-Images: true` y un asset PNG/JPEG referenciado desde el estado.

Fuentes oficiales consultadas:

- [Modelos y precio](https://docs.typesafe.ai/models)
- [API System One](https://docs.typesafe.ai/api/system-one)
- [Estado estructurado](https://docs.typesafe.ai/concepts/state)
- [Imágenes y límites](https://docs.typesafe.ai/images)
- [Choice y distribuciones](https://docs.typesafe.ai/primitives/choice)

El propio proveedor marca las imágenes como una capacidad experimental, no lista para
afirmaciones de producción. Este resultado es por tanto una prueba comparativa, no una
certificación.

## Protocolo fijado

Se evaluaron 160 dibujos, una vez en cada modo:

| Cohorte | Validation | Test/probe | Total |
|---|---:|---:|---:|
| Core, cuatro clases | 17 | 18 | 35 |
| CAD-extra, 16 clases | 56 | 55 | 111 |
| Engineering fuera de dominio | — | 14 | 14 |

Los modos fueron:

- `text`: las seis magnitudes geométricas globales de `sample["text"]`.
- `mixed`: esas mismas seis magnitudes y el render PNG 384×384 utilizado por EG2.

Cada dibujo generó una petición independiente con tres preguntas paralelas:

1. `closed_category`: elección forzada entre las clases de la taxonomía.
2. `open_category`: las mismas clases más `OTHER` y `UNKNOWN`.
3. `sufficient_evidence`: Noul independiente sobre suficiencia de evidencia.

Los criterios describen la taxonomía global. El estado no contiene la etiqueta de la
muestra, nombre de archivo, ruta, fuente, revisión, precio, vecinos ni ejemplos de
referencia. No se ajustó el prompt después de observar respuestas. El prerregistro y las
respuestas crudas permanecen fuera de Git. Los errores de proveedor se conservan como
errores y cuentan en todos los denominadores; nunca se convierten en `UNKNOWN`.

## Resultado cerrado

Macro-F1 y balanced accuracy se calculan sobre todas las muestras, incluidos posibles
errores API. En esta ejecución no hubo errores.

| Cohorte / modo | Validation F1 / BA | Test F1 / BA | Aciertos test |
|---|---:|---:|---:|
| Core, Jev texto | 0,1250 / 0,2500 | 0,0556 / 0,1667 | 2/18 |
| Core, Jev mixto | 0,9416 / 0,9583 | **0,9143 / 0,9167** | 17/18 |
| Core, EG2 mixto 768 + kNN5 | 1,0000 / 1,0000 | 0,8261 / 0,8333 | 16/18 |
| CAD-extra, Jev texto | 0,0296 / 0,1000 | 0,0433 / 0,1042 | 7/55 |
| CAD-extra, Jev mixto | 0,7012 / 0,7244 | **0,5249 / 0,5510** | 39/55 |
| CAD-extra, EG2 mixto 768 + kNN5 | 0,7261 / 0,7644 | 0,7780 / 0,7719 | — |

La imagen cambia por completo la utilidad de Jev. En core, Jev mixto supera el F1
post-hoc del kNN congelado. En CAD-extra ocurre lo contrario: Jev mixto queda claramente
por debajo, con F1 cero en test para `bathroom-set`, `bathtubs`, `doors-plan`,
`restaurant-layouts` y `trees-3d`. El texto global por sí solo no contiene información
semántica suficiente y colapsa casi toda la clasificación.

## Elección abierta y abstención

`coverage` es la fracción de todas las muestras para las que Jev eligió una clase en
vez de `OTHER`/`UNKNOWN`. `exactitud total` conserva abstenciones y errores en el
denominador. La exactitud condicional usa solo decisiones cubiertas.

| Cohorte, modo mixto, test | Coverage | Exactitud total | Exactitud condicional |
|---|---:|---:|---:|
| Core | 17/18 = 94,4% | 17/18 = 94,4% | 17/17 = 100% |
| CAD-extra | 46/55 = 83,6% | 36/55 = 65,5% | 36/46 = 78,3% |

En los 14 planos mecánicos fuera de las cuatro clases core, `open_category` se abstuvo
en 13/14 con imagen y en 14/14 con solo texto. Esto mide comportamiento de rechazo sobre
ese conjunto, no exactitud OOD general. Noul se conserva como diagnóstico; no se eligió
ningún umbral de aceptación.

## Operación y coste observado

- 320 solicitudes de 320 previstas; 320 respuestas válidas y cero errores API.
- Los 320 registros tienen hashes distintos y cada uno observó un solo intento HTTP;
  no hubo reintentos en la batería medida.
- 467.561 tokens de entrada y 96.239 tokens de salida reportados; como no hubo
  aciertos de caché, coinciden con los tokens nuevos de respuestas válidas sin caché.
- Mediana HTTP sin caché: 0,257 s.
- Coste estimado de entrada: USD 0,01964 usando USD 0,042/Mtokens, precio oficial
  consultado el 2026-11-14. Es una estimación, no una factura; la salida figura como
  gratuita en la documentación consultada. El cálculo solo cubre respuestas válidas
  nuevas sin caché; ante una entrega ambigua el uso y coste quedarían como desconocidos.

La caché externa usa el hash del endpoint y payload canónico, incluidos modelo y bytes
de imagen, pero no la autorización. Las respuestas persistidas no incluyen payloads,
renders, rutas ni credenciales.

Tras cerrar la batería se endureció el cliente para futuras corridas: reconstruye las
respuestas mediante whitelist y descarta extras del proveedor; deduplica solicitudes
simultáneas por hash; solo reintenta los estados explícitos 429/529; rechaza esperas
`Retry-After` superiores a 30 segundos; y aplica el límite compartido a intentos HTTP,
no solo a trabajos lógicos. Estas guardas se probaron después y no se presentan
retroactivamente como controles de las 320 llamadas ya ejecutadas.

La paridad de métricas también se corrigió sin llamadas API: macro-F1 usa la unión de
etiquetas verdaderas y predichas, y balanced accuracy solo las clases presentes en la
verdad, igual que el evaluador local basado en scikit-learn. Una clase ausente tanto en
verdad como en predicción queda fuera de macro-F1; si se predice aunque tenga soporte
cero, sí entra. Todas las clases de la taxonomía permanecen visibles en el detalle por
clase. El resumen anterior se conserva externamente como evidencia de procedencia.

Una auditoría de integridad posterior, también sin llamadas API, comparó los hashes de
texto e imagen actuales contra `ordered_input_hashes` de los metadatos EG2: 160/160
pares coincidieron. Después reconstruyó los dos payloads fijados por dibujo y comparó
su identidad con los registros de ejecución: 320/320 coincidieron. El digest agregado
de la auditoría es `ac6335e8500a6796b97fb9b0a657687ee8eda47695c767a284097174d03dda89`.
Esto acredita paridad post-hoc de los bytes de entrada y de las solicitudes; no convierte
esos hashes en parte del prerregistro anterior a la ejecución.

## Dictamen

Jev 1.14 visual es una referencia zero-shot real y competitiva en una taxonomía pequeña:
en core obtuvo 0,9143 de macro-F1 post-hoc sin ejemplos de entrenamiento. No reemplaza al
pipeline EG2 de forma general: al ampliar a 16 clases proxy obtuvo 0,5249, frente a
0,7780 de EG2+kNN5.

La comparación tampoco es simétrica. Jev recibe descripciones de clase y el dibujo, sin
ejemplos; EG2+kNN5 utiliza vecinos etiquetados del train. Las etiquetas son directorios
editoriales ruidosos, no verdad técnica humana. El resultado justifica conservar Jev
visual como baseline zero-shot o segundo dictamen con revisión, no afirmar superioridad
global ni sustituir el clasificador local entrenado.

## Reproducción

El runner es `tools.semantic_lab.jev_comparison`. La clave se proporciona mediante
`TYPESAFE_API_KEY` o con `--credential-file` apuntando a una configuración local ignorada.
Nunca debe entrar en el repositorio, los argumentos documentados, la caché o los informes.
Los manifiestos y directorios de salida se pasan explícitamente; la ejecución exige los
hashes congelados, exactamente 320 peticiones planificadas y un límite por defecto de
350 intentos HTTP en esta ejecución.

El resumen versionable está en
[`jev-summary.json`](../experiments/classifier-comparison-2026-11-14/jev-summary.json).
