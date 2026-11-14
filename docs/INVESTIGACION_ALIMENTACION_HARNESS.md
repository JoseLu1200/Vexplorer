# Investigación: cómo alimentar mejor el harness

Estado: investigación del 2026-11-14 sobre la rama `mejoras/cad-harness`. **Aplicada en la misma rama** (segundo bloque de [MEJORAS_CAD](MEJORAS_CAD.md)), salvo lo que allí figura como no aplicado. Cada propuesta indica dónde actúa, qué regla de [CLAUDE.md](../CLAUDE.md) respeta, coste aproximado y si está verificada. Complementa [MEJORAS_CAD](MEJORAS_CAD.md) sin repetirlo.

Lo que llega al agente depende de tres cosas: (1) qué entidades sobreviven a la ingesta, (2) cómo se resume el ledger en el primer mensaje y (3) qué priors de dominio puede contrastar. Probablemente el cuello de botella principal es la primera. No se ha medido con un DWG real de taller (los DXF de demo se construyen dentro del subconjunto admitido), pero la lista de entidades admitidas deja fuera bloques, arcos y círculos, que son habituales en planos de mueble.

## Comprobaciones hechas en esta sesión

| Comprobación | Resultado |
|---|---|
| Bloques con atributos (prueba con bloque `BISAGRA`: círculo + ATTDEF `REF`) | `recursive_decompose(msp)` devuelve el ATTRIB (`REF=CLIP-110`, **con** handle real) y el CIRCLE virtual con `handle=None`. `insert.virtual_entities()` devuelve solo el CIRCLE: los atributos se leen aparte con `insert.attribs`. |
| `ezdxf` instalado en `.venv` | 1.4.5; importan `ezdxf.disassemble`, `ezdxf.path`, `ezdxf.bbox`, `ezdxf.recover` y `ezdxf.addons.drawing.pymupdf`. PyMuPDF y Pillow ya están en `pyproject.toml`: un canal de render no añade dependencias. |
| Esquemas de herramientas (`agente/tools.py`) en modo `strict` | Los tres tienen `additionalProperties: false` y todas las propiedades en `required`. Usan `minItems`, `minLength` y `exclusiveMinimum`: **comprobar** contra la documentación vigente de Structured Outputs del modelo configurado que esas palabras clave se aceptan (no verificado; el proveedor real nunca se ha ejecutado, ver `team/pablo.md`). |

## 1. Ingesta: lo que hoy se pierde (prioridad alta)

Referencias a `backend/app/ingesta/dxf_reader.py`. Todas las mejoras son deterministas (regla 1) y deben conservar un ID de origen trazable (regla 3).

| Hueco | Dónde | Propuesta concreta | Detalle nicho |
|---|---|---|---|
| **Bloques (`INSERT`) descartados** | `:173` → `unsupported_entity` | `ezdxf.disassemble.recursive_decompose(msp)` o `insert.virtual_entities()` para aplanar bloques anidados. También descompone DIMENSION, LEADER, MLEADER y MLINE; **no** XREF, UNDERLAY ni ACAD_TABLE. | Las entidades virtuales **no tienen handle** (comprobado arriba). Hay que generar IDs sintéticos deterministas: `handle_insert/ruta_anidada/ordinal`. Sin eso se rompe la trazabilidad y la caché. Guardar además el nombre del bloque y sus `ATTRIB` cuando existan (es plausible que bloques de herrajes lleven referencia en atributos; no verificado con bibliotecas reales): evidencia semántica gratuita, tratada como texto no confiable. |
| **Límite de entidades antes de descomponer** | `:75` | Contar después de aplanar, o contar ambas cosas. | Un bloque repetido 40 veces son 40×N primitivas tras explotar. |
| **Polilíneas con arcos (`bulge`) descartadas enteras** | `:91-94` | `ezdxf.path.make_path(entity)` + `flattening(distance)` con tolerancia fija en mm; o conservar el arco como segmento curvo marcado. | Una polilínea cerrada con una esquina redondeada se dibuja con bulge en ese vértice: hoy la pieza entera desaparece por un radio. |
| **ARC, CIRCLE, SPLINE, ELLIPSE, POLYLINE 2D, HATCH ignorados** | `:173` | Leer al menos CIRCLE (centro, radio) y ARC; HATCH como región con nombre de patrón. | Los **círculos son la señal más rica en mueble**: Ø5 en filas a paso 32 mm = laterales con taladro System 32; Ø35 en puertas = cazoleta de bisagra (diámetro pendiente de confirmar con ficha de fabricante). Otros diámetros (espigas, excéntricas) dependen del herraje: sacarlos del catálogo del taller, no fijarlos aquí. Un HATCH dentro de una sección puede marcar material cortado; hipótesis a calibrar con casos reales. |
| **Solo cotas lineales/alineadas** | `:101-108` (dimtype 0 y 1) | Añadir ordinales (tipo 6) y, si aparecen, radiales/diámetros (3, 4). | Los planos de CNC y despiece de taller acotan muy a menudo por **ordenadas** desde un origen; hoy se pierden todas. |
| **Solo modelspace** | `:84` | Inventariar paperspace y viewports (escala de cada viewport) aunque no se extraiga geometría de ahí. | Muchos DWG ponen cotas y textos en paperspace sobre un viewport a escala: aparecen como "plano sin cotas". |
| **DXF dañados de ODA** | `:73` `ezdxf.readfile` | Si falla, `ezdxf.recover.readfile(path)` (devuelve documento + `auditor`) y volcar los errores del auditor como `warnings`. | Más lento; usar solo como reintento. Verificar antes que el archivo no es DXF binario. |
| **`$INSUNITS = 0`** | `:77` | Leer `$MEASUREMENT` (0 imperial / 1 métrico) y la magnitud de `bbox.extents(msp)` como **pista** que se muestra al revisor. | Nunca resolver unidades automáticamente con eso: mantiene `needs_review` (ver HARNESS.md). |

Capas como evidencia: los post-procesadores de CNC de madera (Homag woodWOP, Biesse bSolid/BiesseWorks, Polyboard, Thermwood) pueden codificar operación, profundidad y diámetro **en el nombre de la capa**; la importación DXF de woodWOP se rige por nombres de capa, no por cómo se dibujó la geometría. No hay una tabla pública única: la codificación cambia entre BiesseWorks y bSolid y entre versiones. Si un cliente exporta desde su software de taller, sus nombres de capa son evidencia casi directa de taladros y profundidades. Propuesta: tabla de patrones de capa **por cliente**, sacada de sus propios archivos o del manual de su post-procesador, en configuración y nunca en el prompt, con la coincidencia como evidencia de tipo `layer_convention`.

## 2. Contexto del agente (prioridad media)

Referencias a `backend/app/agente/runner.py` y `provider.py`.

- **Truncado silencioso** (`runner.py:43-45`, `:64-67`): se corta a 60 elementos y 120 caracteres sin avisar. Añadir `{"total": n, "shown": k, "truncated": true}` por lista para que el modelo sepa que debe pedir `inspeccionar_evidencia` en vez de concluir que no hay más.
- **Formato**: CAD-Assistant (ICCV 2025) y el proyecto `cad-dxf-agent` coinciden con la decisión actual: **no pasar DXF crudo al modelo**, sino un resumen estructurado (JSON) de entidades, capas y bloques. Mantenerlo. Lo que falta es incluir capas y bloques en ese resumen (hoy solo linetypes).
- **Agregados deterministas baratos** que conviene precalcular y meter en el digest: número de entidades por capa; bloques por nombre y número de inserciones; histograma de diámetros de círculos; pasos repetidos entre círculos (detecta 32 mm); grosores de las bandas paralelas cercanas (candidatas a espesor de tablero). El modelo razona mucho mejor sobre agregados que sobre listas largas.
- **Proveedor** (`provider.py:42`, `:54`): `max_output_tokens: 1200` y tratar `incomplete` como fallo es frágil con modelos de razonamiento, que consumen tokens antes de emitir la llamada. Comprobar con el modelo configurado; si se queda corto, subir el límite o reintentar una vez dentro del presupuesto.

## 3. Canal visual (propuesta, requiere acuerdo A/B)

`prompts.py:2` dice "No recibes imágenes ni visión" y la lista de herramientas es cerrada, así que esto es un cambio de contrato.

- HARNESS.md ya prevé `visualizar_vista`. Se puede implementar sin dependencias nuevas: `ezdxf.addons.drawing` con `PyMuPdfBackend` → PNG de una vista, con `Configuration` para ocultar texto si se quiere.
- **Set-of-Mark**: superponer sobre el render el ID corto de cada contorno (o número) y pasar la tabla número→ID. El paper SoM muestra que marcas numéricas visibles mejoran mucho el anclaje de GPT-4V a regiones; aquí permite que el modelo diga "el contorno 7 es la trasera" y el backend lo resuelva a IDs del ledger (trazabilidad intacta).
- Advertencia de los benchmarks recientes (MechVQA, AECV-Bench, TechMB, DesignQA): los VLM siguen fallando en lectura fina de cotas. La imagen debe servir para **relaciones** (qué está dentro de qué, qué se repite), no para medir. Las medidas siguen saliendo del ledger.

## 4. Priors de dominio para el validador y el revisor

Ninguno de estos valores debe rellenar campos ni lo inventa el agente: sirven como **rangos de plausibilidad** del validador o pistas para la persona revisora. Los valores definitivos deben venir del catálogo del taller (compras, ver MEJORAS_CAD).

| Prior | Uso | Estado de la fuente |
|---|---|---|
| System 32: taladros Ø5 a paso 32 mm, retranqueo 37 mm del canto frontal | Detectar laterales y su orientación; la presencia de la fila confirma que es lateral portante | Confirmado (Wikipedia, WOODWEB, KISS II) |
| Bisagras referidas al primer taladro y en múltiplos de 32 mm; cazoleta inferior ~64 mm del borde | Detectar puertas y su lado de giro | Fuentes de foro; orientativo |
| Cazoleta Ø35 mm | Idem | **No confirmado** en esta búsqueda: verificar con ficha de fabricante |
| Tablero de casco 16/18/19 mm | Rango de `observed_thickness_mm` plausible | 18–19 mm confirmado en guías; 16 mm no confirmado |
| Trasera en ranura (HDF fino) | Explica líneas ocultas paralelas cerca del fondo | Ranura confirmada; espesores 3 mm/6 mm con fuentes contradictorias |
| Canto 0,4 / 1 / 2 mm | Descuento de canto en medida de corte | Solo se confirmó 0,5 mm en una ficha; **verificar** |

Para la lista de corte: Polyboard exporta en ASCII el orden `Alto; Ancho; Cantidad; Material; Veta; Referencia; Canto superior; Canto inferior; Espesor de canto`, y la convención habitual de veta es `0 = rotable`, `1 = solo giro de 180°` (varía según el programa). Sirve para hacer `format=cutlist` compatible con optimizadores sin inventar un formato propio. No se pudo confirmar el esquema exacto de columnas de OpenCutList.

## 5. Datos para calibrar y alimentar el histórico

- **Caso con líneas ocultas** (pendiente en MEJORAS_CAD): generar vistas desde PlankAssembly con las aristas ocultas en linetype `HIDDEN`/`DASHED` (ISO 128). Da a la vez el caso de calibración de `linetype` y su respuesta. Bloqueado mientras `../engineering_dataset` no exista en este equipo (MEJORAS_CAD). Licencia CC BY-NC-ND: no distribuir adaptaciones del dataset; los casos generados no entran en el repo ni en la demo, solo en evaluación local.
- **Reconstrucción clásica desde tres vistas** (Markowsky–Wesley, 1980–81; Furferi et al. sobre DXF): produce el *pseudo-wireframe*, la unión de todas las soluciones compatibles. Es determinista y encaja como generador de escenarios alternativos para el agente; no se encontró implementación Python lista.
- **Taxonomía de piezas**: PartNet tiene la categoría *StorageFurniture* con jerarquía de partes anotada por expertos. Útil como vocabulario cerrado de `role` y para el descriptor semántico (con la migración de embeddings que MEJORAS_CAD exige).

## Descartado y por qué

| Opción | Motivo |
|---|---|
| SymPoint, VecFormer, CADSpotting (detección de símbolos en vectores) | Requieren entrenamiento y están ajustados a planos de planta (FloorPlanCAD, ArchCAD-400K), no a mueble. Interesantes solo si hubiera miles de planos anotados del taller. |
| eDOCr2 y OCR de cotas con VLM | Trabajan sobre ráster. Solo tienen sentido si se aprueba entrada PDF/escaneada, fuera del alcance DXF actual. |
| LibreDWG (`dwg2dxf`) en lugar de ODA | Su propio README declara ~90 % de cobertura de entidades; ODA sigue siendo la opción madura. Puede valer como respaldo en Linux. |
| Pasar el DXF crudo al LLM | La literatura (CAD-Assistant, survey de LLM para CAD, CAD-Coder) y herramientas reales lo desaconsejan por longitud y ruido. Confirma la arquitectura actual. |
| PlankAssembly como modelo de inferencia | Sin seguimiento directo publicado 2024–25 encontrado; exigiría entrenar un transformer propio con un dataset cuya licencia NC-ND no permite distribuir adaptaciones ni uso comercial. Se mantiene solo como fuente de casos de evaluación local (sección 5). |

## Orden recomendado

1. `INSERT` + IDs sintéticos deterministas y bulge/arcos/círculos en `dxf_reader.py` (A). Es lo que más contenido añade.
2. Agregados (capas, bloques, histograma de círculos, pasos de 32 mm) y avisos de truncado en el digest (B).
3. Validar el proveedor real con un plano de demo y ajustar `max_output_tokens` (B).
4. Priors System 32 como reglas de plausibilidad en el validador, con valores del catálogo del taller (A + compras).
5. Canal visual con Set-of-Mark, tras acuerdo A/B y aviso a C.

## Fuentes

Las cifras marcadas como de resumen secundario (resultados de SoM y CAD-Assistant) no se contrastaron con el texto completo de los papers.

- ezdxf: [disassemble](https://ezdxf.readthedocs.io/en/stable/disassemble.html), [Insert](https://ezdxf.readthedocs.io/en/stable/blocks/insert.html), [drawing add-on](https://ezdxf.readthedocs.io/en/stable/addons/drawing.html), [image export](https://ezdxf.readthedocs.io/en/stable/tutorials/image_export.html), [recover](https://ezdxf.readthedocs.io/en/stable/drawing/recover.html), [ODA add-on](https://ezdxf.readthedocs.io/en/stable/addons/odafc.html)
- [Set-of-Mark Prompting (arXiv 2310.11441)](https://arxiv.org/abs/2310.11441)
- [CAD-Assistant (arXiv 2412.13810)](https://arxiv.org/abs/2412.13810), [LLMs for CAD: survey (arXiv 2505.08137)](https://arxiv.org/pdf/2505.08137), [CAD-Coder (arXiv 2505.08686)](https://arxiv.org/html/2505.08686v1), [cad-ai-agent](https://github.com/jeremylongshore/cad-ai-agent)
- Benchmarks VLM: [MechVQA](https://arxiv.org/pdf/2605.30794), [AECV-Bench](https://arxiv.org/pdf/2601.04819), [Enginuity](https://arxiv.org/pdf/2606.03410), [DesignQA (MIT)](https://dspace.mit.edu/entities/publication/ff7b3dee-88b0-4ecb-97fd-c0fa769e07f0)
- OCR de planos: [eDOCr2 (MDPI Machines)](https://mdpi.com/2075-1702/13/3/254), [Florence-2 GD&T (arXiv 2411.03707)](https://arxiv.org/pdf/2411.03707), [pipeline híbrido (arXiv 2510.21862)](https://arxiv.org/pdf/2510.21862v2)
- Símbolos en vectores: [FloorPlanCAD](https://arxiv.org/abs/2105.07147v2), [SymPoint](https://arxiv.org/abs/2401.10556v1), [VecFormer](https://arxiv.org/html/2505.23395v3), [CADSpotting](https://arxiv.org/html/2412.07377v4), [ArchCAD-400k](https://arxiv.org/html/2503.22346v3)
- [PlankAssembly](https://manycore-research.github.io/PlankAssembly), [PartNet](https://ar5iv.arxiv.org/html/1812.02713), [Markowsky–Wesley y reconstrucción desde vistas (curso IIT Kanpur)](https://cse.iitk.ac.in/users/amit/courses/751/97/2D_Orthographic_to_Wireframe/methodology.html), [Furferi et al.](https://flore.unifi.it/bitstream/2158/391901/1/From%202D%20Orthographic%20views.pdf)
- Mueble: [Sistema 32 mm](https://en.wikipedia.org/wiki/32_mm_cabinetmaking_system), [KISS II (37 mm)](https://www.woodweb.com/knowledge_base_images/zp/kiss_2_system.pdf), [Odd cabinet heights 32 mm](https://woodweb.com/knowledge_base/Odd_Cabinet_Heights_with_32mm.html), [davelers 32mm](https://davelers.com/32mm), [especificaciones de casco](https://temple-5xa.pages.dev/architecture/Building-Construction/Estimating--and--Costing/kitchens/cabinetry-detail-and-specifications), [Frameless specs](https://www.cabinetnow.com/frameless-cabinet-specs/)
- CNC y listas de corte: [woodWOP: capas a geometría DXF](https://stilesmachinery.com/assigning-woodwop-layer-names-to-dxf-geometry/), [Homag woodWOP DXF import](https://www.homag.com/fileadmin/software/downloads/woodwop-dxf_import_basic.pdf), [AVC DXF export (capas Biesse/Homag)](https://sites.google.com/site/avcplugins/dxf), [Polyboard post-processor DXF](https://wooddesigner.org/help-centre/polyboard-post-processor-parameters-dxf/), [formato de listas de corte](https://wooddesigner.org/formating-cutting-lists-for-other-applications/)
- Conversión DWG: [OSArch DWG](https://wiki.osarch.org/index.php/Drawing_(DWG)), [FreeCAD y DWG](https://wiki.freecad.org/FreeCAD%20and%20DWG%20Import), [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter.md)
- Structured Outputs: [restricciones de modo strict (Azure OpenAI)](https://learn.microsoft.com/mt-mt/azure/ai-services/openai/how-to/structured-outputs), [anyOf en strict (foro OpenAI)](https://community.openai.com/t/oneof-allof-usage-has-problems-with-strict-mode/966047)
