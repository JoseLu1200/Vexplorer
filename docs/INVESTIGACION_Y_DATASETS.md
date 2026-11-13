# Investigación y selección de datasets

Revisión: 13 de noviembre de 2026. Este documento contrasta el resumen aportado por el usuario con fuentes primarias y consulta de archivos del Hub. Los resultados publicados son de sus autores; no se han reproducido en Vexplorer. Consultar un catálogo o ver un enlace no equivale a descargar o validar un corpus.

## Selección según el objetivo

| Candidato | Qué permite estudiar | Límite y disponibilidad comprobada | Prioridad propuesta |
|---|---|---|---|
| PlankAssembly | Reconstrucción de muebles de tableros desde tres vistas; 26.707 programas de forma | Se distribuyen programas 3D; el código genera dibujos SVG. Descarga y extracción verificadas: ZIP de 19.607.117 bytes, 26.707 modelos oficiales; unidades mm; licencia CC BY-NC-ND 4.0. Vistas 2D pendientes | Primero para pares controlados de vistas y componentes de mobiliario |
| IKEA-Manual | 102 muebles con piezas, manuales y relaciones de montaje | Manuales, no planos de fabricación acotados. Conversión AssemblyWorld accesible; sus unidades físicas son desconocidas | Complemento para identidad de componentes y montaje |
| CAD2Program | Dibujos y programas de armarios; el artículo describe 368K modelos | El repositorio consultado contiene la web; no se verificó una descarga del corpus completo | Referencia de arquitectura; no dependencia disponible confirmada |
| OmniMech | Más de 251K dibujos/modelos mecánicos, cotas y reconstrucción | La web anuncia muestras; el Hub muestra directorios, pero deniega lectura a la cuenta conectada | Ampliación mecánica si se obtiene acceso; no sustituto automático de mobiliario |
| Drawing2CAD / CAD-VGDrawing | Dibujos vectoriales y modelos paramétricos emparejados | Generación CAD, sin evidencia aquí de una referencia de despiece y costes de muebles | Comparación de representación vectorial y raster |
| Corpus local engineering_dataset | Piezas CAD acotadas y conjuntos mecánicos con detalles | Descargado y verificado; piloto de 17 casos preparado; no histórico económico | Mantener como control técnico |

Fuentes: [PlankAssembly, proyecto](https://manycore-research.github.io/PlankAssembly/), [código y procedimiento de generación](https://github.com/manycore-research/PlankAssembly), [entrada del Hub](https://huggingface.co/datasets/manycore-research/PlankAssembly); [IKEA-Manual original](https://cs.stanford.edu/~rcwang/projects/ikea_manual/) y [conversión no oficial](https://huggingface.co/datasets/AssemblyWorld/ikea-manual/blob/main/README.md); [CAD2Program, artículo](https://arxiv.org/abs/2412.11892) y [repositorio web](https://github.com/manycore-research/CAD2Program); [OmniMech, artículo](https://arxiv.org/abs/2608.05539), [web](https://omnimech.dev/) y [Hub](https://huggingface.co/datasets/OmniEDA/OmniMech); [Drawing2CAD](https://arxiv.org/abs/2508.18733).

La selección es una inferencia de adecuación al proyecto, no un ranking publicado. PlankAssembly es el candidato más directo para representar tableros y vistas; IKEA-Manual aporta montaje explícito. Ninguno acredita por sí solo un presupuesto ni la interpretación general de un único alzado incompleto. Conservar los datos actuales permite comprobar cotas mientras se prepara la vertiente de mobiliario.

PlankAssembly no entrega un paquete listo de DWG/DXF industriales. Su referencia simplifica los tableros como cuboides con relaciones de contacto; los dibujos se generan desde los programas. Son pares controlados útiles, con una diferencia respecto a planos reales recibidos en fábrica. La ficha ya accesible declara milímetros y licencia CC BY-NC-ND 4.0, distinta del AGPL-3.0 del código. El usuario obtuvo acceso y la descarga autenticada se verificó. La [auditoría local](PLANKASSEMBLY.md) registra diferencias respecto a la descripción: 985 JSON fuera de los splits, normales ausentes y primera fila de envolvente excluida de las piezas.

La conversión AssemblyWorld de IKEA-Manual publica 102 Parquet y conserva geometría, páginas PNG y anotaciones seleccionadas. No incluye los PDF/SVG originales ni todas las máscaras y cámaras del dataset fuente. Para una evaluación de todas las anotaciones, preferir la distribución original de Stanford; para este formato convertido, admitir solo los campos comprobados. Tener coordenadas de vértices no prueba que estén en metros.

## Resultados de investigación contrastados

| Trabajo | Resultado o alcance confirmado | Implicación propuesta para Vexplorer |
|---|---|---|
| From Drawings to Decisions | El resumen reporta F1 93,5 % y tasa de alucinación 11,5 % en extracción de anotaciones; corpus de 1.367 dibujos | Separar extracción de anotaciones de inferencia de componentes; conservar procedencia y revisar errores |
| Drawing2CAD, ACM MM 2025 | Secuencias CAD desde vectores. Sus limitaciones incluyen precisión de parámetros, conflictos entre vistas y geometría no visible | No equiparar parecido visual con corrección dimensional |
| RealCADBench | 12.632 tareas; evaluación reportada de 1.770, incluidas 25 de montaje; programas FreeCAD y métricas complementarias | Medir ejecución, geometría e identidad por separado |
| Blueprint2CAD | Hasta 65 % Recall@1 con vistas conocidas y 43 % sin ellas, sobre galería de 10.000 modelos | Evaluar identificación de vistas y búsqueda por atributos además del embedding |
| Manual-PA | Ensambla piezas 3D con ayuda de diagramas y estima sus poses | Sirve para relaciones de montaje; no descubre todas las piezas desde un alzado sin ayudas |
| AssemState v2, 9-11-2026 | F1 de estructura 62,80 % bajo protocolo con máscaras de pasos; 5,3 % de operaciones aceptadas en su experimento de poses con refinamiento | Una estructura semántica mejor no implica montaje físicamente correcto |
| Estudio de coste de mobiliario, IJMLC 2021 | 1.026 productos; Random Forest R² medio 0,842 con todas las variables y validación cruzada de 10 particiones; incluye tiempos de proceso | Comparar modelos tabulares. No usar tiempos reales futuros como variables disponibles al presupuestar |

Fuentes primarias: [From Drawings to Decisions](https://arxiv.org/abs/2506.17374); [Drawing2CAD, limitaciones](https://arxiv.org/html/2508.18733v5); [RealCADBench](https://arxiv.org/html/2609.03773v2); [Blueprint2CAD](https://arxiv.org/abs/2611.02433); [Manual-PA](https://arxiv.org/abs/2411.18011); [AssemState](https://arxiv.org/html/2610.08446v2); [estudio de costes, tabla II](https://www.ijmlc.org/vol11/1010-T1018.pdf). Para este último se pudo contrastar el texto indexado de la fuente primaria; la apertura directa del PDF en el navegador de investigación falló.

Los porcentajes tienen tareas, entradas y denominadores distintos: no se promedian ni se traducen en «porcentaje de muebles correctamente despiezados». En particular, R² no es porcentaje de presupuestos acertados y las métricas de recuperación no prueban equivalencia de fabricación. No se afirma haber demostrado la inexistencia de una solución comercial integral; únicamente que estas fuentes no validan todo nuestro recorrido.

## Referencias comerciales

[Werk24](https://v2.docs.werk24.io/) documenta extracción estructurada de cotas, materiales, tolerancias y otros datos. [Paperless Parts](https://www.paperlessparts.com/press/paperless-parts-launches-new-dxf-quoting-capabilities-to-help-manufacturers-quote-faster/) anunció el 21-10-2026 clasificación y preparación de DXF de piezas planas para presupuestación, en beta abierta según ese anuncio. Son capacidades declaradas por sus fabricantes; no se han probado aquí ni demuestran despiece general de mobiliario.

## Decisión práctica y orden

1. Mantener el piloto local para cotas, unidades y abstención.
2. Priorizar la preparación 2D de PlankAssembly ya descargado, tras revisar las condiciones de uso y una muestra de desarrollo; conservar programas completos solo como referencia del evaluador.
3. Usar IKEA-Manual como complemento de estructura/montaje, sin atribuir precisión métrica a coordenadas de unidad desconocida.
4. Tratar CAD2Program como referencia hasta verificar una distribución utilizable. No confundir código de una web con código de entrenamiento o datos publicados.
5. Evaluar las cuatro alternativas con el protocolo de [COMPARATIVA_METODOS](COMPARATIVA_METODOS.md). No descargar grandes corpora mecánicos solo por su tamaño.

Actualización de disponibilidad: PlankAssembly se descargó y extrajo después de que el usuario obtuviera acceso. La integridad coincide con el hash publicado; [PLANKASSEMBLY](PLANKASSEMBLY.md) contiene revisión y auditoría. IKEA-Manual y los demás candidatos no se han descargado en esta actualización. OmniMech sigue pendiente de acceso comprobado. El corpus mecánico existente se conserva.
