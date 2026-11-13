# Reconstrucción revisable desde vistas de piezas separadas

## Objetivo y autorización

El usuario aclara que el sistema debe recibir únicamente vistas del despiece, sin montaje completo ni referencia 3D, y confirma **DXF 2D con piezas separadas**. La auditoría del baseline `dab7ce5` demuestra que el recorrido anterior no satisface este requisito. Se conserva como evidencia histórica, no como validación del nuevo flujo.

El usuario ya autorizó decisiones rutinarias autónomas, contratos acordados por A/B, swarm GPT-6.1 Sol, revisión final GPT-6 Astra, worktrees, integración y push a main. No se añade una aprobación de diseño redundante. Las elecciones técnicas siguientes son del coordinador y se contrastan con la revisión final y pruebas.

## Diseño elegido

Se conserva Python/FastAPI/Pydantic/ezdxf y frontend JS/HTML. La ruta nueva es explícita `separated_part_views`; la antigua queda identificada `mounted_views_legacy`. No se transforma artificialmente el despiece en vistas de un conjunto conocido.

Se compararon dos alternativas: forzar el ledger antiguo de tres vistas globales, que escondería el cambio de significado y requiere conocer el montaje, y añadir observaciones de piezas y candidatos de ensamblaje separados, que preserva fuentes e incertidumbre. Se elige la segunda. Una reconstrucción libre sin restricciones se descarta para esta primera familia porque no permite verificar todas sus medidas ni resolver la falta de información.

La fuente única de tipos es Pydantic; el [acuerdo A/B](../../CONTRATO_PARTS_ONLY_0_4.md) fija nombres y compatibilidad. El plano puede contener identificadores opacos, orientación de vistas y cantidades explícitas legítimas. No contiene roles, familia, montaje, dimensiones generales ensambladas ni respuesta reservada. Sin asociación demostrable, la vista queda ambigua. Tres vistas de una pieza nunca significan tres piezas.

El motor determina dimensiones locales con evidencia, conserva conflictos/desconocidos y propone combinaciones compatibles de paneles para la familia acotada. Familia, función de una pieza y posición de montaje son hipótesis. Las dimensiones exteriores se calculan desde los paneles y el montaje propuesto. El modelo consulta herramientas y propone/selecciona candidatos respaldados; no modifica cifras del ledger. Sin una construcción única identificable se muestran alternativas.

La persona revisora puede confirmar candidato y premisas/faltantes, creando una versión nueva. La escena 3D es una reconstrucción derivada de esa revisión, nunca una entrada ni una prueba de que el objeto original tuviera ese montaje. Se generan sólidos solo con dimensiones, cantidad y colocación respaldadas. Colisiones y fabricación real permanecen pendientes.

## Experiencia visible

Entrada «Piezas separadas»; vistas agrupadas por identidad demostrable; cotas y entidades interiores conservadas; encuadre por selección. Tabla de piezas observadas, cantidades y desconocidos antes de cualquier montaje. Inspector con evidencias y explicación de la asociación. Hipótesis de clasificación y montajes separadas del dibujo. Revisión y 3D con premisas visibles. Biblioteca basada en descriptor canónico versionado que incluye espesores e incertidumbre, con similitud geométrica offline y embeddings reales identificados.

## Límites y criterios

- Una familia de paneles rectangulares para demostrar el recorrido; no afirmar entendimiento universal de muebles.
- DXF 2D; PDF/imágenes/DWG quedan fuera de esta entrega acordada.
- Geometría y cálculo deterministas. No BOM esperada en extractor/prompt ni lectura de referencias privadas por runtime.
- Si faltan unidad, cantidad, espesor, asociación o restricciones suficientes: conservar `null`, advertencias y la posibilidad de revisar el dibujo.
- Modo `geometry_only` sin proveedor, `live` con proveedor real, replay no anunciado mientras no exista.
- Revisión versionada, explicación/escena/exportación exactas para su revisión; sin reutilizar silenciosamente datos de otra sesión.
- Fixture propio con solo piezas y referencia separada; variante incompleta y cambios de escala/dimensión/posición/key para evitar memorizar respuestas.
- Nueva verificación HTTP y navegador del flujo integrado, además de suites y revisión Astra. No VPS ni publicación de datasets externos.

## Correcciones necesarias detectadas en el baseline

Se incluyen OCS/Z y texto DIMLFAC (medición veraz), entidades interiores/encuadre por vista (visualización completa), descriptor con espesor/versionado y actualización de traza/bloqueos de UI relacionados con el nuevo recorrido. Los demás hallazgos permanecen en la auditoría hasta verificarse expresamente; una implementación nueva no los borra.
