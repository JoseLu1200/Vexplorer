# Vexplorer — planos, piezas y reconstrucción revisable


**Demo sin API de IA:** [demo completa con embeddings Gemma/DINOv3/MiniLM y pipeline Plank ya procesados](data/semantic_pipeline_demo/README.md) · [paquete Plank independiente](data/plank_pipeline_demo/README.md) · [muebles sintéticos ya procesados](docs/DEMO_DATOS_PROCESADOS.md) · [datasets: descargas directas](docs/DATASETS_DESCARGA_DIRECTA.md).
Vexplorer convierte planos DXF, DWG y PDF en propuestas de piezas y medidas revisables. El recorrido **Mueble general** permite proponer paneles, elementos lineales, herrajes y componentes pendientes de identificar, sin limitar la entrada a mesa o estantería. Conserva también los recorridos especializados de mesa rectangular y piezas separadas. La geometría mide; un proponente multimodal interpreta el plano y un segundo pase visual contrasta y corrige la propuesta. La edición humana es opcional.

Recorrido general: **plano → propuesta visual → crítica y corrección automáticas → BOM, SVG/DXF y esquema 3D → comparables → estimación de costes y horas**. El histórico admite JSON/CSV con procedencia, fecha, moneda, materiales, acabado y alcance económico; recupera por atributos o embeddings reales y estima por conceptos compatibles. Distingue registros empresariales, fuentes publicadas y datos sintéticos. La evaluación técnica no acredita precisión industrial ni ahorro medido con técnicos.

**Aplicación desplegada del equipo:** [abrir Vexplorer](https://gex-dashboard.hopto.org/vexplorer/). El acceso anónimo está habilitado de forma explícita en el VPS desde el release operativo `public-access-20261114-071821`; el 2026-11-14 se observaron HTTP 200 tanto en la raíz como en health. El perfil de producción sigue aplicando guard de origen a mutaciones, límites y jobs, pero **el acceso público no equivale a aislamiento entre usuarios**. La autenticación continúa siendo el valor seguro por defecto para despliegues nuevos. El candidato UX anterior `a61f97a89a86-treec58bbe42140dd03c` se aceptó con Basic Auth y 401 anónimo antes de este cambio posterior; ambas evidencias se conservan con su cronología. Las tarifas iniciales son demo. Operación y límites en [PRODUCCION](docs/PRODUCCION.md).

El [contrato de mesa 0.5](docs/CONTRATO_MESA_0_5.md) define el recorrido. La [verificación de mesa y CAD](docs/VERIFICACION_MESA_CAD_2026-11-14.md) conserva el cierre anterior con API, navegador, inferencia y visión reales. La [integración de PR1](docs/INTEGRACION_PR1_2026-11-14.md) documenta los 14 commits revisados y sus adaptaciones. El incremento privado añade contratos económicos 0.6, jobs durables y replay verificado; las aceptaciones históricas no sustituyen su revisión actual.

## Auditoría e incremento privado

El [explorador semántico](docs/semantic-lab/INTEGRACION_EXPLORADOR.md) añade mapa 2D, vecinos por coseno, comparación de modelos y propuestas kNN/logística. Se habilita por instancia y reutiliza embeddings persistidos; [operación, publicación y rollback](docs/semantic-lab/OPERACION_EXPLORADOR.md). Este incremento está integrado en `main`, pendiente de despliegue; no se atribuye a la aplicación privada enlazada arriba.

La [verificación de esta ampliación](docs/VERIFICACION_TRANSCRIPCION_2026-11-14.md) registra integración, navegador, inferencia real y límites observados. El [diseño](docs/superpowers/specs/2026-11-14-transcript-completion-design.md) y el [plan](docs/superpowers/plans/2026-11-14-transcript-completion.md) describen el incremento implementado por agentes GPT-6.1 Sol y revisado por GPT-6 Astra. La guía [PRODUCCION](docs/PRODUCCION.md) incluye despliegue y copias. La [auditoría anterior](docs/AUDITORIA_COMPLETA_2026-11-14.md) y la [verificación privada anterior](docs/VERIFICACION_PRIVADA_2026-11-14.md) conservan sus resultados históricos; no sustituyen la aceptación actual.

El cierre de PoC posterior se trabaja en la rama/worktree aislada `poc-closure`: integra las correcciones de abstención, PDF raster, semántica y corpus sin borrar los cambios concurrentes útiles de similitud que el usuario pidió conservar. La cohorte pareada inicial de seis casos se congeló antes de puntuación; tres casos terminaron y tres se detuvieron por el mismo presupuesto visual antes del proveedor. La recuperación se fijó de antemano solo para esos tres fallos y conserva denominador, bytes de los éxitos, fallos originales y procedencia por versión. Las métricas y límites consolidados pertenecen a [CIERRE_POC](docs/CIERRE_POC_2026-11-14.md); no se anticipan aquí. El commit y paquete definitivos se registrarán después de integrar y repetir la verificación, y este trabajo no implica un nuevo despliegue.

## Instalación y arranque local (PowerShell)

Desde la raíz del repositorio, con Python 3.11 o posterior y Node/npm:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
npm ci --prefix frontend
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

Abrir **http://127.0.0.1:8765**. FastAPI sirve también el frontend JS/HTML: no hay otro proceso de frontend. `npm ci` prepara Three.js local, sin CDN durante el uso. La geometría, el visor, la revisión y la similitud geométrica funcionan sin credenciales. Instalación comprobada en Windows con Python 3.14.2 y Node 25.8.1; [requirements-demo.txt](requirements-demo.txt) registra las dependencias Python verificadas. Para repetir esas versiones en un entorno compatible, instalar con `-c requirements-demo.txt`.

El arranque anterior usa modo local: documentos, resultados y revisiones en `.vexplorer-data/`, ignorado por Git; mantener ese modo en `127.0.0.1`. Para el equipo existe un perfil privado con cuentas individuales, trabajos persistidos y TLS mediante proxy: seguir [PRODUCCION](docs/PRODUCCION.md), que registra la configuración y el estado del despliegue.

La biblioteca puede conservar descriptores v1/v2/v3. La interfaz de mesa filtra v3; las comparaciones rechazan mezclas de versiones incompatibles. Para una demo con almacenamiento separado:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from dotenv import load_dotenv; load_dotenv(); import uvicorn; from backend.app.main import create_app; uvicorn.run(create_app(data_dir=Path('.runtime/demo-parts')),host='127.0.0.1',port=8765)"
```

## Guion de mueble general e histórico

1. Cargar DXF, DWG o PDF y elegir **Mueble general**. DWG necesita LibreDWG u ODA configurado; en PDF seleccionar una página y confirmar su escala cuando se conozca. Sin escala, las dimensiones métricas permanecen desconocidas. Una página raster puede aportar evidencia visual al agente, pero sus píxeles no se convierten en cotas.
2. Ejecutar **Agente en vivo** para proponer y revisar automáticamente mediante herramientas nativas e imágenes del plano. La crítica utiliza un contexto separado y un ciclo acotado de reparación. Cada dimensión conserva su referencia; una asignación inferida continúa siendo hipótesis aunque la medida geométrica sea precisa. **Solo geometría** sigue disponible para inspección sin proveedor.
3. Consultar las comprobaciones y correcciones automáticas. El resultado conserva incógnitas y separa las ocurrencias provisionales de escenario de las confirmadas; tres vistas no cuentan como tres piezas. No hay aprobación humana obligatoria. Opcionalmente se pueden editar, dividir, combinar o descartar componentes con una decisión registrada; las versiones anteriores permanecen disponibles.
4. Abrir **Esquema general** y descargar los SVG/DXF acotados. El despiece automático identifica sus escenarios y cantidades provisionales; no representa uniones, mecanizados ni una colocación certificada para fabricación.
5. Importar históricos propios en JSON/CSV con procedencia, moneda, fecha y alcances separados de costes y horas. El flujo automático puede calcular escenarios condicionales por referencia usando el despiece provisional: muestra expresamente el supuesto de una unidad y el material, acabado y alcance heredados del comparable. No transforma esos supuestos en atributos observados del plano.
6. Consultar los escenarios y su procedencia, o buscar comparables por atributos o embeddings. Cada escenario conserva su moneda y alcance; no se promedian referencias incompatibles. Los costes fijos se cuentan una vez y los variables se escalan por su unidad; las horas proceden de conceptos históricos de tiempo. El presupuesto basado en datos confirmados sigue disponible por separado. La opción de datos sintéticos está desactivada por defecto; las fuentes públicas y los presupuestos se identifican por separado.

Contratos y ejemplos en [MUEBLE_GENERAL](docs/MUEBLE_GENERAL.md), [HISTORICO_REAL](docs/HISTORICO_REAL.md) y [EVALUACION_INTEGRAL](docs/EVALUACION_INTEGRAL.md). La [auditoría de datasets locales](docs/DATASETS_INTEGRALES.md) y las [fuentes económicas públicas](docs/FUENTES_HISTORICO_PUBLICO.md) explican qué datos se admitieron y qué conclusiones permiten.

## Guion de mesa desde vistas montadas

1. Cargar [mesa_demo_001.dxf](data/planos_demo/mesa_demo_001.dxf), elegir **Mesa · vistas montadas**, **Solo geometría** y la plantilla explícita **2 soportes laterales**. Es una baseline de catálogo, no inferencia live. Con proveedor configurado, **Agente en vivo** genera su propio programa acotado de componentes y operaciones referenciadas.
2. Inspeccionar cotas escritas y medidas de geometría CAD. Los offsets observados de 30 y 18 mm todavía requieren interpretar qué sección representan; esa asignación es una hipótesis, no una cota escrita de espesor. La tapa propuesta mide 1200 × 700 × 30 mm y los dos soportes 720 × 700 × 18 mm bajo las premisas del programa.
3. En **Revisar**, aceptar o rechazar programa, componentes y premisas con motivo y nombre. La nueva revisión recalcula las dependencias y conserva las anteriores. Los campos desconocidos bloqueantes se pueden completar con una decisión registrada; no se sustituyen medidas observadas por números libres.
4. Abrir **General acotado**, **Por pieza** y **Despiece**. Descargar SVG/DXF de cada lámina. Las cotas conservan estado y procedencia; el despiece representa ocurrencias físicas. **3D** muestra cajas esquemáticas tras una revisión suficiente, sin uniones ni mecanizados certificados.
5. En **Coste**, elegir tarifas sintéticas de material, canteado y operaciones. Revisar cantidades, fórmulas y contribuciones por componente. Los conceptos no resueltos permanecen desconocidos: un subtotal conocido no se presenta como precio completo ni valor comercial del mueble. Exportar ficha JSON y lista de corte CSV genérica.
6. Guardar revisiones en **Biblioteca** y compararlas con [mesa_demo_002.dxf](data/planos_demo/mesa_demo_002.dxf). El descriptor `furniture-v3` conserva estructura, cantidades y dimensiones de componentes y se consulta separado de las versiones anteriores. El parecido semántico no justifica por sí solo un coste.
7. Probar [mesa_demo_003.dxf](data/planos_demo/mesa_demo_003.dxf), con información insuficiente, y [mesa_demo_004.dxf](data/planos_demo/mesa_demo_004.dxf), con conflicto dimensional. Conservar los pendientes y revisar la traza; no esperar un plano fabricable por defecto.

El programa generativo está limitado a tapa más dos soportes laterales o cuatro patas de esquina, con operaciones `copy/add/subtract` sobre medidas del ledger y reglas versionadas. No genera muebles arbitrarios, piezas curvas, herrajes ocultos ni soluciones de unión. Una referencia reservada no determina por sí sola la única construcción compatible con un plano pobre.

## Guion de piezas separadas

1. Cargar [piezas_completo.dxf](data/planos_demo/piezas_completo.dxf), seleccionar **Piezas separadas** y **Solo geometría**, y pulsar **Abrir**. La entrada contiene nueve vistas de tres tipos de panel, sin montaje ni modelo 3D.
2. Seleccionar **Pieza K2**: ver sus tres vistas, cotas y fuentes en el inspector. La cantidad `2` procede de `QTY K2 2`, no del número de vistas. Sus dimensiones son `864 × 300 × 18 mm`.
3. En **Revisar**, comparar las asignaciones de K2/K3 a tapa/base o baldas. Son hipótesis compatibles, no funciones reveladas por sus identificadores. El ancho montado calculado es `864 + 18 + 18 = 900 mm`.
4. Elegir una asignación, indicar persona revisora, material `tablero sintético`, acabado `melamina sintética` y motivo. Registrar la decisión crea la revisión 2; no cambia las evidencias observadas.
5. Abrir **3D**: seis ejemplares, órbita, selección y **Despiece 3D**. La posición de las baldas es esquemática y explícitamente hipotética; las colisiones no se evalúan. No es un modelo certificado para fabricación.
6. En **Biblioteca**, guardar la revisión. Repetir con [dimensiones distintas](data/planos_demo/piezas_dimensiones_variante.dxf), [identificadores y posición distintos](data/planos_demo/piezas_ids_trasladados.dxf) y [espesor de 36 mm](data/planos_demo/piezas_espesor_36.dxf). Buscar y agrupar en **Geométrico · offline**. Cambiar identificadores/posición conserva el descriptor; cambiar espesor lo modifica incluso con igual envolvente montada.
7. Con proveedor configurado, elegir **Semántico · modelo real** y guardar cada revisión para generar su embedding. Buscar y agrupar usa los vectores guardados; no llama al modelo en cada consulta. Se identifica modelo, dimensión y método; el coseno no es una probabilidad.
8. En **Coste**, consultar comparables sintéticos y calcular: material `1,7568 m² × 50 EUR/m² = 87,84 EUR`; preparación `40 EUR`, una sola vez; total **127,84 EUR**. Horas desconocidas. Exportar ficha JSON con escena, explicaciones, descriptor, biblioteca, resultado y traza; CSV para la tabla de piezas.
9. Probar [cantidad desconocida](data/planos_demo/piezas_qty_desconocida.dxf), [espesor desconocido](data/planos_demo/piezas_espesor_desconocido.dxf) y [asociación ambigua](data/planos_demo/piezas_ambigua_sin_id.dxf). Los faltantes se conservan; una revisión puede aportar cantidad o medidas con su motivo. Sin asociación suficiente no se fuerza un montaje.

El formato admitido para asociar vistas de piezas separadas es texto visible `PART <clave> FRONT|TOP|SIDE`; la cantidad usa `QTY <clave> <entero>`. Los ejes locales son FRONT largo/ancho, TOP largo/espesor y SIDE espesor/ancho. No es reconocimiento general de piezas sin etiquetas. Las vistas montadas pueden asociarse por una disposición inequívoca, marcada para revisión. La opción **Estantería · legado** conserva la primera demo con [estanteria_montada.dxf](data/planos_demo/estanteria_montada.dxf).

La entrada no contiene una BOM ni nombres de piezas. La referencia propia está en [evaluation/reference](evaluation/reference/README.md), reservada a las pruebas del evaluador; las herramientas y endpoints del producto no la sirven ni la leen. El caso es de desarrollo inspeccionado, no un benchmark ciego. El test congela la salida antes de abrir la referencia.

## Modos

- **geometry_only**: extracción determinista sin proveedor; en el recorrido general permite elaborar una propuesta manual a partir de esa evidencia.
- **live**: OpenAI Responses con herramientas nativas, bucle propio y validación local. En mueble general propone componentes y asigna referencias geométricas; en mesa genera el programa especializado. Las explicaciones conservan fuentes, fórmulas y premisas. Puede usar la página raster como evidencia visual sin inventar medidas. La inferencia general sigue sujeta a revisión y cobertura empírica.
- **recorded_replay**: reproduce offline una ejecución live grabada por el servidor con la misma entrada y configuración. Verifica transcript y resultados de herramientas, conserva procedencia y no importa decisiones humanas. Si no existe una grabación válida coincidente, lo comunica y rechaza la ejecución. No admite grabaciones subidas por el cliente.

Para live, configurar `OPENAI_API_KEY` en un `.env` local ignorado por Git. [`.env.example`](.env.example) muestra los nombres, sin credenciales. Con la clave ya configurada:

```powershell
$env:OPENAI_MODEL="gpt-6.1-sol"
$env:OPENAI_MAX_OUTPUT_TOKENS="16384"
$env:VEXPLORER_GENERAL_REVIEW_MODEL="gpt-6-astra"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --env-file .env
```

Los errores de proveedor se muestran como tales; no se convierten en resultados geométricos etiquetados live. Límites: 15 llamadas de modelo, 30 herramientas, 2 reparaciones estructurales y 120 segundos para la fase del agente. `OPENAI_MAX_OUTPUT_TOKENS` vale 4096 por defecto y admite de 256 a 16384; una configuración inválida deshabilita el proveedor con motivo explícito. Nunca incorporar `.env` a Git.

En **mueble general live**, el proponente y el crítico reciben imágenes de la fuente automáticamente: vista general y recortes con referencias del ledger. El ejemplo anterior usa GPT-6.1 Sol para proponer y GPT-6 Astra para revisar. El crítico emite decisiones sobre campos y comprobaciones; una reparación semántica, si procede, vuelve a pasar por el proponente y el crítico. Los valores inferidos siguen siendo hipótesis. El job dispone de 300 segundos por defecto, con hasta cinco llamadas de revisión y dos reparaciones de formato; conserva la propuesta previa si falla una fase posterior.

En el recorrido especializado de **mesa live**, la visión continúa desactivada por defecto: `OPENAI_VISION_ENABLED=1` habilita la herramienta nativa `visualizar_vista`, que debe consultar al menos una vista antes de entregar su programa. Se permiten tres intentos en total, con PNG locales del ledger de hasta 1024 px y 2 MB por vista. Esta opción no desactiva las imágenes del recorrido general. Las marcas identifican contornos o entidades; los píxeles no aportan medidas. La traza conserva vista, hash y número de marcas. La lectura CAD y las herramientas vectoriales siguen siendo la fuente numérica.

Los embeddings son independientes del modo de análisis del DXF. Usan `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` y `OPENAI_EMBEDDING_DIMENSIONS=256` por defecto. La biblioteca los genera al guardar en modo semántico; el histórico los genera y cachea al solicitar recuperación semántica explícita. La caché distingue descriptor, modelo y dimensiones; se rechazan vectores corruptos o incompatibles. Los ejemplos de la misma familia tienen cosenos muy altos: la utilidad de esa agrupación sobre un histórico variado sigue pendiente de evaluación.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
.\.venv\Scripts\python.exe -m compileall -q backend tools
```

Node prepara los módulos locales de Three.js y ejecuta las pruebas JavaScript; el servidor de uso es Python. Resultados actuales y auditoría HTTP/proveedor en [VERIFICACION_TRANSCRIPCION_2026-11-14.md](docs/VERIFICACION_TRANSCRIPCION_2026-11-14.md); antecedentes en [VERIFICACION_MESA_CAD_2026-11-14.md](docs/VERIFICACION_MESA_CAD_2026-11-14.md).

Los DXF propios se pueden regenerar con:

```powershell
.\.venv\Scripts\python.exe -m tools.build_demo_fixture
.\.venv\Scripts\python.exe -m tools.build_parts_fixture
.\.venv\Scripts\python.exe -m tools.build_table_fixture
```

Las pruebas cubren unidades, vistas frente a cantidades, espesor ausente, cotas conflictivas, referencias aisladas, revisiones, geometría variable y cálculo económico independiente. Las pruebas del proveedor usan un doble de la frontera HTTP; no sustituyen el motor ni se presentan como inferencia live.

### Snapshot reproducible del runtime

El empaquetador local crea un `tar.gz` determinista a partir de una allowlist del runtime. Incluye los bytes actuales de `backend/app`, los helpers y assets del frontend —incluidos `frontend/core/ui.js` y las fuentes locales—, las tres herramientas operativas y los manifiestos de dependencias Python/Node. Excluye pruebas, secretos, `.env`, datos, referencias de evaluación, documentación y `.runtime`. Si falta una entrada esencial, el build falla en vez de producir un shell parcial.

```powershell
python -m tools.build_release --output .runtime/release-a
python -m tools.build_release --output .runtime/release-b
Get-FileHash .runtime/release-a/*.tar.gz, .runtime/release-b/*.tar.gz -Algorithm SHA256
```

Dos ejecuciones sobre los mismos bytes deben producir el mismo `candidate_id`, `payload_tree_sha256` y SHA-256 del archivo. `RELEASE.json` registra el commit base y declara que el snapshot puede incorporar contenido allowlisted aún no confirmado; por eso el identificador de cierre solo es definitivo después de integrar todos los cambios y repetir el comando. El empaquetado es local: no activa, transfiere ni publica ningún release.

## Alcance y trabajo pendiente

- Lectura DXF: modelspace, bloques anidados y atributos, líneas y polilíneas rectas, círculos/arcos tipados, textos y cotas lineales o por ordenadas. ELLIPSE/SPLINE son aproximaciones visuales declaradas; no generan paneles ni medidas exactas. Se detectan filas regulares de círculos y líneas ocultas como evidencia neutral y se contrasta un catálogo de taller que por defecto no está confirmado. DXF recuperados requieren revisión. Límites: 100.000 entidades, 20.000 puntos por entidad y 200.000 por dibujo. Paperspace se clasifica y limita: anotaciones informativas, cotas que requieren revisión y no se proyectan a modelspace. HATCH, bulges y ARC con OCS negativo quedan fuera. DWG se convierte mediante LibreDWG u ODA; PDF conserva originales y páginas vectoriales/raster. Estas entradas no garantizan reconocimiento de toda construcción ni fidelidad universal del CAD.
- La revisión general permite reemplazar, dividir, combinar y descartar componentes. Los elementos ocultos o desconocidos necesitan evidencia y decisiones explícitas; la herramienta no garantiza una interpretación única del plano.
- Biblioteca geométrica/semántica e histórico importable de costes y horas. La estimación conserva procedencia, fórmulas, cobertura y faltantes; no añade impuestos, inflación ni conceptos no declarados. La relevancia de recuperación y el error económico requieren un histórico representativo.
- Reconstrucción por cajas de tableros según montaje revisado y niveles observados, sin traseras ocultas añadidas, mecanizados, uniones detalladas ni certificación de colisiones. Las ejecuciones antiguas se abren, pero para obtener cotas enriquecidas y vínculo al CAD original deben analizarse de nuevo.
- El endpoint legado local conserva ejecución síncrona. El perfil privado incorpora trabajos persistidos y seguimiento mediante polling; no se afirma procesamiento distribuido ni streaming de tokens o imágenes.
- PlankAssembly y los originales de terceros permanecen fuera de Git. Se ejecutó inferencia real sobre seis casos diagnósticos y diez casos nuevos, congelando resultados antes de la puntuación. Los informes separan cobertura dimensional, cantidades, ocurrencias y escenarios; no equivalen a validación con técnicos. Ver [EVALUACION_INTEGRAL](docs/EVALUACION_INTEGRAL.md).
- La comparación de métodos, evaluación con técnicos y medición de ahorro siguen pendientes; ver [COMPARATIVA_METODOS](docs/COMPARATIVA_METODOS.md).

## Documentación y coordinación

El [laboratorio semántico de mobiliario](docs/semantic-lab/README.md) reúne la auditoría de embeddings/harness, investigación de modelos, experimentos locales con EmbeddingGemma 2/DINOv3/MiniLM, comparación con geometría/PCA, resultados, reproducción y límites para clasificación y precios. Es un laboratorio aislado del runtime; consultar su versión de app/datasets antes de trasladar sus conclusiones al producto.

[Diseño inicial](docs/DEMO_IMPLEMENTACION.md), [ampliación del visor](docs/VISOR_RECONSTRUCCION_SIMILITUD.md), [proyectos open source evaluados](docs/OPEN_SOURCE.md), [coordinación](team/agente_coordinador.md), [A geometría](team/agente_geometria.md), [B backend](team/agente_backend.md), [C frontend](team/agente_frontend.md), [D evaluación](team/agente_evaluacion.md).

Los documentos [initial-plan.md](initial-plan.md), [PLAN.md](PLAN.md), [ARQUITECTURA](docs/ARQUITECTURA.md) y [CONTRATOS_DATOS](docs/CONTRATOS_DATOS.md) conservan el diseño amplio y sus pendientes. Los acuerdos [0.4 de piezas](docs/CONTRATO_PARTS_ONLY_0_4.md) y [0.5 de mesa](docs/CONTRATO_MESA_0_5.md) añaden sus recorridos; el envelope HTTP sigue en **0.2.0**, el export de mesa en **0.5.0** y sus descriptores son **furniture-v2/v3**. A/B acordaron los cambios y avisaron a C; [modelos.py](backend/app/contratos/modelos.py) es la fuente contractual. No todas las tareas T1–T13 están terminadas.

El preparador mecánico anterior continúa disponible. Esta entrega elimina sus diagnósticos de abstención del contexto público, verifica la referencia contra el manifiesto y consume los bytes verificados; los pilotos antiguos requieren regeneración para incorporar esas correcciones. No se ha redistribuido ni regenerado aquí el corpus externo. Véase [PILOTO_DATASET](docs/PILOTO_DATASET.md).
