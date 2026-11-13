# Piloto del dataset preparado

Estado: herramienta local implementada y ejecutada. Esto prepara entradas y referencias; todavía no ejecuta el agente, mide su precisión ni implementa la aplicación web.

## Resultado

Se verificaron 421 archivos de SHA256SUMS, 65 casos del índice y sus 93 rutas. Ningún hash discrepó antes ni después de generar el piloto. El manifiesto no cuenta su propio archivo. Los archivos auxiliares de caché fuera del manifiesto no se incorporan.

| Casos | Entrada | Uso |
|---|---|---|
| cad-001 a cad-014 | DXF originales con nombres neutros | Extracción de cotas y unidades; anotaciones conservadas, no evaluación ciega |
| visual-001 | Vista 2D del conjunto montado, sin lista ni despiece | Proponer componentes y reconocer ambigüedad; no exigir cantidades o medidas invisibles |
| visual-002 | Dos vistas acotadas de una pieza individual | Control de lectura: 69,85 × 44,45 × 5 mm; cantidad de conjunto desconocida desde esta entrada |
| visual-003 | Vista frontal de la misma pieza | Leer ancho/alto y dejar espesor y cantidad desconocidos |

Los tres casos visuales pertenecen a una misma familia y a desarrollo. No deben cruzar particiones de desarrollo/prueba. Los PDF se reconstruyen desde recortes rasterizados para excluir objetos, texto, adjuntos y metadatos ocultos. **No son DXF editables ni prueban lectura CAD nativa.** Los 14 DXF sí conservan su formato original. La unidad mm de las dos vistas de pieza procede del cajetín original y se declara como contexto; el conjunto sin cotas conserva unidad desconocida. No medir milímetros a partir de píxeles.

Los 50 conjuntos Julius permanecen íntegros en el corpus fuente: se verificaron sus archivos, pero este piloto no les atribuye despieces etiquetados ni crea automáticamente una referencia que aún no está anotada.

## Archivos locales generados

En el mismo directorio padre de Vexplorer: `engineering_evaluation_pilot_v2/`.

- `agent_cases/<id>.zip`: entregar **solo uno por ejecución**, con contexto nuevo y acceso limitado a ese caso. Incluye `input.pdf` o `input.dxf` y `case.json`.
- `agent_inputs.zip`: transporte conjunto de las entradas, **no** montarlo completo en una evaluación individual. Contiene variantes que pueden revelar respuestas de otras variantes.
- `evaluator_reference.zip`: originales, BOM, referencias del publicador, recortes, hashes y expectativas; exclusivo del evaluador.
- `SHA256SUMS`: hashes de los 68 archivos generados, incluidos los ZIP.

Separar directorios no crea un aislamiento de permisos. El futuro harness debe restringir herramientas y contexto al ZIP individual, sin acceso al repositorio, corpus completo, referencia ni otros casos. No usar una conversación que ya haya visto la respuesta para medir precisión ciega.

La referencia del conjunto tiene 12 tipos de pieza y 22 unidades; solo una pieza tiene dimensiones revisadas. No exigir reconstruir los elementos ocultos de esa BOM desde una sola vista. Conservar hipótesis, cobertura y abstenciones en la futura evaluación.

## Reproducir desde la raíz del repositorio

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
python -m tools.prepare_evaluation --source ../engineering_dataset --audit-only
python -m tools.prepare_evaluation --source ../engineering_dataset --output ../engineering_evaluation_nuevo
```

El directorio de salida debe ser nuevo y no solaparse con la fuente. No se sobrescriben salidas previas. Si una generación se interrumpe después de la auditoría puede quedar un directorio `.partial-*`, que no se presenta como resultado terminado. Los hashes de las dos fuentes PDF están fijados para que un cambio de revisión obligue a revisar los recortes. No se ejecutan scripts del dataset ni se llama a APIs.

## Comprobaciones realizadas

- 11 pruebas fallaron primero por funciones no implementadas y pasaron tras implementarlas.
- Dos pruebas adicionales fallaron primero y pasaron al añadir ZIP aislados por caso y verificación de hash antes de empaquetar.
- `python -m pytest -q`: 13 pruebas aprobadas.
- Generación real completada; 17 casos, 17 ZIP individuales, 4 páginas de PDF.
- Verificación independiente de los 68 hashes de salida, archivos de cada ZIP, ausencia de texto/adjuntos/título de fuente en los PDF y suma de la BOM de referencia.
- Renderizado con Poppler y revisión visual de los cuatro recortes. Se corrigió el margen izquierdo para evitar cortar la cota 25,40.
- Fuente revalidada después de generar: 421/421 hashes correctos.
- Empaquetado Python comprobado con `pip wheel --no-deps --no-build-isolation`; 167 enlaces locales de documentación resueltos.

## Alcance y siguiente integración

Usar estos casos para probar primero extracción y abstención. Después conectar una ejecución aislada del harness por caso y un evaluador independiente. Los resultados de esta entrega son de preparación e integridad, no precisión de interpretación, utilidad en mobiliario ni calidad de presupuestos. Los datos y referencias generados quedan fuera de Git; se versionan la herramienta, pruebas y procedimiento.

## Revisión independiente

Revisión del cambio `6d6229d..c8f1f63`: sin incidencias críticas o importantes; confirmó 13 pruebas y 68 hashes. Mejora menor aplazada: los ZIP incluyen fechas de generación, por lo que no son idénticos byte a byte entre ejecuciones. El procedimiento y contenido son reproducibles; los hashes documentan la integridad de cada generación concreta.

## Complemento de mobiliario

La [selección de nuevos datasets](INVESTIGACION_Y_DATASETS.md) propone PlankAssembly para tableros/vistas y IKEA-Manual para montaje. No sustituye ni modifica este corpus verificado. El protocolo de [cuatro métodos](COMPARATIVA_METODOS.md) describe cómo usar el piloto sin confundir preparación con resultados de inferencia.
