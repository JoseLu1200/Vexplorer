# Integración del explorador semántico de Vexplorer

Fecha: 2026-11-14. Diseño ampliado por instrucción explícita del usuario: implementar los modelos y arquitecturas ensayados que más aportan al menor coste, delegando la selección técnica. Base inmutable: `83df72d`, que incluye `main` / `dbd1bb6` y el flujo autónomo; las ramas continúan avanzando. Complementa la [decisión](DECISION_ARQUITECTURA_PRODUCCION.md) y el [diseño de producción](DISENO_ARQUITECTURA_PRODUCCION.md).

## Objetivo de producto

La [transcripción](../../transcripcion-contexto-poc.md) describe a 50 personas que convierten planos pobres en despieces y estimaciones. El explorador debe ayudar a encontrar precedentes, entender qué se parece y qué falta, y abrir la evidencia para continuar ese trabajo. Un mapa atractivo sin recuperación útil ni procedencia no satisface este objetivo.

## Investigación y diferencias entre ramas

| Evidencia | Conclusión para la integración |
|---|---|
| `dbd1bb6`, main y experiment/semantic-furniture | Laboratorio y decisión EG2 mixto 768 L2/coseno, logística candidata y Jev opcional; no runtime multimodal publicado. |
| `c7ea203` → `a61f97a`, feat/transcript-completion | Mueble general, PDF/DWG, propuesta/crítica autónoma, revisiones exactas, importación de histórico y escenarios condicionales. |
| `83df72d`, feat/transcript-final | Une ambas líneas; base apropiada para esta implementación. |
| Checkout raíz modificado | Trabajo UX/evaluación concurrente no integrado en esta base; no se sobrescribe ni se presenta como entregado aquí. |
| PLAN T11–T13 y CASO_DE_USO_Y_EVALUACION | Cotar un dibujo no prueba inferencia constructiva, utilidad del histórico ni ahorro de tiempo. |
| SEMANTICA, contratos 0.4/0.5 y mueble general 0.6 | Observación, componente, vista, ocurrencia, hipótesis y revisión son identidades distintas. |
| HISTORICO_REAL y EVALUACION_INTEGRAL | Hay importación y experimentos económicos públicos posteriores al laboratorio; no hay validación ERP/industrial. |
| AUDITORIA_COMPLETA y registros de equipo | Numerosos Markdown conservan checkpoints históricos. El código y el commit determinan capacidad actual, no una frase aislada de un plan. |

Se han inventariado y leído los 112 Markdown versionados de la base integrada, incluyendo `team`, planes, especificaciones, frontend y evaluación; véase el [inventario con hashes](INVENTARIO_DOCUMENTAL.md). Las ramas auxiliares se contrastan por ascendencia y diffs; los worktrees duplicados no cuentan como fuentes independientes. Originales, referencias privadas, pesos y bases locales quedan fuera del inventario documental público.

## Requisitos trazables

| ID | Necesidad | Comportamiento y criterio de aceptación |
|---|---|---|
| EX-01 | Explorar parecidos | Mapa 2D de embeddings reales, selección con ratón/teclado y lista alternativa accesible. Vacío real cuando no hay vectores. |
| EX-02 | Recuperar precedentes | Vecinos exactos por coseno de vectores originales normalizados; excluir la propia consulta y ordenar empates por ID. |
| EX-03 | Encontrar un elemento | Filtro textual por etiqueta/metadatos rotulado como filtro, separado de la búsqueda vectorial por ejemplo. No fingir embedding de una consulta libre. |
| EX-04 | Diferenciar espacios | Selector de proveedor/modelo/dimensión/descriptor y release. No concatenar ni comparar OpenAI y Gemma. |
| EX-05 | Entender parecidos | Mostrar coseno, fuentes, revisión, dimensiones y diferencias constructivas disponibles; desconocido no significa cero ni coincidencia. |
| EX-06 | Volver al plano | Abrir la ejecución para la biblioteca; previsualización autorizada del render para corpus publicados localmente. No exponer rutas del sistema. |
| EX-07 | Integrar laboratorio | Publicador CLI que valida NPZ y metadatos/hash, copia renders autorizados y crea release inmutable. No cargar pickle ni descargar modelos en una consulta. |
| EX-08 | Conservar revisiones | Excluir biblioteca obsoleta respecto al resultado actual; identificar el snapshot del mapa y rechazar consultas contra snapshots cambiados. |
| EX-09 | Operar sin proveedor | Consultar vectores persistidos no necesita llamadas pagadas. Ausencia/corrupción de vectores produce estado explícito. |
| EX-10 | Publicar y revertir | Feature flag; directorio aislado; puntero atómico al release; validación antes de activación; rollback explícito; retiradas se aplican también al volver atrás. |
| EX-11 | Presupuesto trazable | Navegar al flujo económico existente. El mapa y el coseno no generan precios, horas, medidas ni cantidades. |
| EX-12 | Evaluar utilidad | Pruebas de recuperación independientes del mapa, revisiones obsoletas, aislamiento, errores, teclado, XSS y recorrido HTTP/navegador. |

## Enfoques y entrega elegida

1. **Integración aditiva en la app actual:** API de consulta y vista propia, biblioteca persistida y releases del laboratorio. Aprovecha los vectores existentes y permite verificar utilidad sin volver a entrenar. Es la propuesta para esta entrega.
2. **Servicio vectorial externo y UMAP en tiempo real:** añade operación, dependencias y variación del mapa sin necesidad de volumen demostrada. Se reserva para una medición que justifique el coste.
3. **Página estática del experimento:** útil para investigación, pero deja fuera revisiones y acceso desde la app. No cubre por sí sola la petición.

La entrega implementa EX-01 a EX-12 dentro de un **piloto privado de exploración** y la ampliación siguiente. Clasificación automática calibrada, entrenamiento empresarial y ANN siguen pendientes de evaluación industrial. La búsqueda semántica conserva recuperación por ejemplo, además del flujo existente de biblioteca/histórico; el filtro de etiquetas sigue siendo léxico.

### Ampliación solicitada y selección por coste

| Componente | Integración elegida | Coste y autoridad |
|---|---|---|
| EG2 mixto 768 | Principal; ingesta offline de planos nuevos mediante el encoder real ya ensayado y publicación versionada. | Inferencia local explícita, caché por contenido; navegar no carga pesos. |
| EG2 imagen/texto/256, DINOv3 y MiniLM | Publicar y comparar espacios ya calculados; el CLI permite generar con los adaptadores existentes. | Controles opcionales, no ejecutar todos automáticamente. |
| Regresión logística EG2+27 features | Exportar parámetros numéricos del artefacto propio para inferencia local sin pickle en servidor. | Propuesta no calibrada; no cambia vecinos ni confirma una familia. |
| kNN5 | Baseline y ganador core; artefacto numérico de train. | Sin red; clases y scores sin garantía OOD. |
| Jev visual | Petición explícita de segunda opinión, desactivada sin clave/presupuesto del servidor, respuesta estructurada y caché. | Presupuesto durable por intentos; fallo conserva resultados locales. |
| Geometría y atributos | Diferencias explicables de biblioteca y comparación separada. | No inventar campos ausentes ni equivalencia económica. |
| PCA | Proyección visual persistida por snapshot. | Nunca comprimir el índice de búsqueda. |
| HDBSCAN/KMeans/boosting | Conservar informes del laboratorio; no promover automáticamente. | No demostraron ventaja operativa suficiente para justificar otra dependencia de runtime. |

Se incorporan modelos Pydantic nuevos en un módulo propio; no se modifican los contratos compartidos de inferencia ni las reglas económicas. No se interpreta esta entrega como calibración industrial o autorización de entrenamiento sobre históricos privados.

### Concreciones de la revisión

- NumPy pasa a dependencia explícita de runtime. sklearn sigue siendo dependencia de preparación, no de consulta.
- Los clasificadores numéricos JSON v2 incluyen encoder completo, esquema de features y hashes del entrenamiento; se reproducen con receta fija sobre train. El publicador rechaza modelos incompatibles y Joblib legado sin ese contrato.
- La importación exige renders relativos y contenidos en el corpus, incluso al resolver enlaces. Una herramienta separada prepara copias portables de los manifiestos históricos sin alterar sus vectores.
- Releases, imágenes PNG, activaciones, retiradas y caché de proyección se almacenan en `semantic_explorer.sqlite3`. Transacciones SQLite serializan publicación y retirada; el backup incorpora esta base opcional.
- La proyección se persiste. Se garantiza estabilidad del snapshot publicado, no igualdad binaria entre SVD de plataformas con autovalores empatados.
- La caché comprueba checksum, identidad y miembros; se reconstruye si está dañada. Extender un catálogo comprueba que su activación no cambió antes de sustituir el puntero.
- Identidad de consulta: origen/catálogo, espacio y miembro; los IDs locales nunca se comparan globalmente.
- Límite explícito del piloto: 2.000 miembros por espacio, hasta 4.096 dimensiones y PNG de hasta 2 MiB. Se rechaza el exceso; no se trunca silenciosamente.
- API: listado de espacios, snapshot, vecinos y render. Conflicto 409 ante snapshot obsoleto, 404 para miembro/espacio inexistente y 503 para funcionalidad desactivada. Vectores solo en servidor.

## Componentes y límites

- `backend/app/semantic_explorer/`: contratos Pydantic aditivos, proyección determinista, búsqueda exacta, lectura de releases y adaptador de biblioteca. No modifica `backend/app/contratos/`.
- `tools/publish_semantic_explorer.py`: admisión offline de corpus y gestión de activación/rollback/retirada. Datos fuera de Git y sin importar scripts del corpus.
- `frontend/explorer.html`, `explorer.js` y módulos propios: pantalla accesible enlazada desde Biblioteca. JS/HTML/SVG, coherente con el estilo existente, sin otro framework.
- API bajo `/api/v1/semantic-explorer`, montada antes de los estáticos y cubierta por autenticación privada existente.
- Persistencia de releases fuera del árbol fuente. La biblioteca sigue siendo autoritativa para sus revisiones. No se crea un histórico económico paralelo.

El perfil privado actual es un catálogo compartido por el equipo autenticado. No hay ACL de proyecto ya implementadas: no prometer multitenancy. Los corpus externos solo se habilitan mediante configuración de servidor y quedan en ese mismo ámbito. Despliegues que necesiten separación empresarial usan instancias/directorios distintos hasta implementar las ACL del diseño objetivo. El cliente nunca elige un directorio o `catalog_scope` arbitrario.

## Proyección 2D

PCA 2D centrada sobre los vectores L2 del snapshot autorizado, con orden de IDs estable y orientación de signos determinista. Se usa únicamente para dibujar. La búsqueda conserva las 768 dimensiones de EG2 o las dimensiones originales del proveedor seleccionado.

La UI muestra método, versión, tamaño, varianza explicada y el aviso de distorsión. No calcula distancias físicas ni etiquetas de familia a partir de la posición. Se contempla cero, uno, dos puntos, vectores idénticos y rango deficiente. No se inventa separación con ruido. Un filtro visual conserva coordenadas del snapshot; cambiar corpus o revisión genera otro snapshot y puede mover puntos. Para este tamaño se limita el número de puntos de forma explícita, nunca con truncado silencioso.

Los vecinos seleccionados se resaltan en el mapa y se listan con el mismo orden obtenido en el espacio original. La alternativa textual permite completar el recorrido sin usar el gráfico. Zoom/encuadre y selección no modifican datos, clasificación ni revisión.

## Identidad, consistencia y seguridad

Un snapshot referencia versión de algoritmo de proyección, espacio, revisión/modelo/preprocesado, miembros e identidades de sus vectores. El ID cambia si cambia cualquier entrada. Las respuestas de búsqueda exigen ese ID y fallan con conflicto si quedó obsoleto. La API no envía vectores completos al navegador.

Los releases externos contienen solo una lista declarada de IDs, vectores finitos/no nulos, metadatos públicos y renders admitidos. Sus rutas son relativas controladas por el publicador. Hashes, dimensiones, cardinalidad y unicidad se validan antes de activar. El loader rechaza traversals, espacios incompatibles, corrupción y tamaños excesivos. Una lista de retiradas fuera del release evita resucitar un miembro por rollback.

No se infiere correspondencia entre un ID del laboratorio y un registro económico. Sin enlace revisado, esa relación permanece ausente. Los nombres/etiquetas no entran en el encoder durante publicación; se usan únicamente para mostrar y filtrar.

## Reconciliación con el flujo autónomo

La puerta de revisión del diseño previo debe distinguir dos vías: resultados confirmados para decisiones respaldadas y escenarios provisionales con premisas visibles. La crítica automática puede producir hipótesis auto-revisadas sin obligar a una persona a aprobarlas; no las convierte en medidas observadas. Un escenario condicional económico conserva moneda, fuente, alcance y supuestos, y no equivale a una oferta.

La cifra histórica de cero propuestas de la prueba offline del laboratorio describe ese snapshot y modo. No describe todos los resultados live posteriores. Las métricas 510/CI/Astra de `dbd1bb6` tampoco aceptan automáticamente este incremento.

## Validación y despliegue gradual

1. Baseline de la base integrada y tests focales rojos para nuevas fronteras.
2. Unitarios con vectores de coseno conocido; proyección degenerada; filtros y orden; rechazo de mezcla/corrupción.
3. HTTP de biblioteca/release, snapshots obsoletos, activación fallida, retirada y rollback; autenticación del perfil privado.
4. Navegador con corpus real local ya calculado y fixture propio identificado; escritorio/móvil, teclado, estados vacío/error y consola.
5. Suite Python/JS y verificación de enlaces/diff; registro de resultados del árbol final.
6. Piloto local con flag. Operador publica corpus autorizado, verifica manifiesto y activa el flag en una instancia privada. Canary por instancia/grupo de usuarios; no simular porcentajes sin infraestructura para aplicarlos.
7. Rollback: desactivar flag o reactivar release anterior validado. No revierte resultados/revisiones ni restaura miembros retirados. Backup de releases/puntero/retiradas junto a los almacenes existentes.

No se despliega a un servidor ni se fusiona `main` con esta especificación. Esos pasos requieren la entrega verificada y el destino autorizado. Las pruebas funcionales no validan por sí solas relevancia industrial ni ahorro: el piloto debe medir juicios técnicos, Precision@k, cobertura, tiempo de búsqueda y errores por familia sobre consultas nuevas.
