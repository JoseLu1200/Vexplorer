# Vexplorer — planos, piezas y reconstrucción revisable

Vexplorer convierte vistas DXF 2D en propuestas de piezas y medidas revisables. Admite dos recorridos acotados: **mesa rectangular desde alzado, planta y perfil del conjunto**, y **estantería desde vistas de piezas separadas con identificadores explícitos**. La geometría mide; el modelo propone asociaciones y operaciones; una revisión registra las premisas aceptadas y los datos aportados.

Recorrido de mesa: **plano con cotas parciales → programa de componentes → revisión → planos acotados generales, por pieza y de despiece → reconstrucción esquemática → similares y costes por conceptos**. La biblioteca usa atributos geométricos o embeddings reales. El incremento privado permite un catálogo económico propio con fuente y fecha; el catálogo de demostración se mantiene identificado como sintético. Los casos propios de desarrollo no acreditan generalización, precisión industrial ni ahorro medido con técnicos.

**Aplicación privada del equipo:** [abrir Vexplorer](https://gex-dashboard.hopto.org/vexplorer/). Requiere credenciales individuales. El despliegue del 2026-11-14 incluye API, almacenamiento persistente, inferencia live y replay verificado; se comprobaron reinicio y recuperación de copia. Las tarifas iniciales son demo. Evidencia y límites en la [verificación privada](docs/VERIFICACION_PRIVADA_2026-11-14.md).

El [contrato de mesa 0.5](docs/CONTRATO_MESA_0_5.md) define el recorrido. La [verificación de mesa y CAD](docs/VERIFICACION_MESA_CAD_2026-11-14.md) conserva el cierre anterior con API, navegador, inferencia y visión reales. La [integración de PR1](docs/INTEGRACION_PR1_2026-11-14.md) documenta los 14 commits revisados y sus adaptaciones. El incremento privado añade contratos económicos 0.6, jobs durables y replay verificado; las aceptaciones históricas no sustituyen su revisión actual.

## Auditoría e incremento privado

La [auditoría completa](docs/AUDITORIA_COMPLETA_2026-11-14.md) recorre los 495 commits accesibles al comenzar, la documentación y los módulos propios; identifica defectos que la suite anterior no detectaba. La [verificación privada](docs/VERIFICACION_PRIVADA_2026-11-14.md) recoge 423 pruebas Python, 108 JavaScript, CI, navegador y el SHIP de Astra. El [diseño privado](docs/superpowers/specs/2026-11-14-private-production-design.md) y el [plan](docs/superpowers/plans/2026-11-14-private-production.md) registran sus criterios de aceptación. La guía [PRODUCCION](docs/PRODUCCION.md) incluye usuarios, catálogo, despliegue y copias. El alcance sigue siendo el perfil de mesa y los recorridos acotados descritos abajo; validación industrial y aceptación con técnicos se informan por separado.

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

- **geometry_only**: extracción y candidatos deterministas compatibles de la familia admitida; no llama a un proveedor.
- **live**: OpenAI Responses con herramientas nativas, bucle propio y validación local. En mesa genera bindings y componentes dentro del perfil acotado; en los otros recorridos inspecciona y elige hipótesis existentes. Las explicaciones conservan fuentes, fórmulas y premisas. El canal predeterminado es evidencia vectorial estructurada; no demuestra descomposición libre de cualquier mueble.
- **recorded_replay**: reproduce offline una ejecución live grabada por el servidor con la misma entrada y configuración. Verifica transcript y resultados de herramientas, conserva procedencia y no importa decisiones humanas. Si no existe una grabación válida coincidente, lo comunica y rechaza la ejecución. No admite grabaciones subidas por el cliente.

Para live, configurar `OPENAI_API_KEY` en un `.env` local ignorado por Git. [`.env.example`](.env.example) muestra los nombres, sin credenciales. Con la clave ya configurada:

```powershell
$env:OPENAI_MODEL="gpt-6.1-sol"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --env-file .env
```

Los errores de proveedor se muestran como tales; no se convierten en resultados geométricos etiquetados live. Límites: 15 llamadas de modelo, 30 herramientas, 2 reparaciones estructurales y 120 segundos para la fase del agente. `OPENAI_MAX_OUTPUT_TOKENS` vale 4096 por defecto y admite de 256 a 16384; una configuración inválida deshabilita el proveedor con motivo explícito. Nunca incorporar `.env` a Git.

La visión está **desactivada por defecto**. En mesa live, `OPENAI_VISION_ENABLED=1` habilita la herramienta nativa `visualizar_vista`; el modelo debe consultar al menos una vista antes de entregar su programa. Se permiten tres intentos en total, con PNG locales del ledger de hasta 1024 px y 2 MB por vista. Las marcas identifican contornos o entidades; los píxeles no aportan medidas. La traza conserva vista, hash y número de marcas. Esta opción se probó contra la API real y sigue sin acreditar reconocimiento general de muebles. La lectura CAD y las herramientas vectoriales siguen siendo la fuente numérica.

Los embeddings son independientes del modo de análisis del DXF. Usan `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` y `OPENAI_EMBEDDING_DIMENSIONS=256` por defecto. Se generan mediante una acción explícita de guardado semántico. La caché distingue descriptor, modelo y dimensiones; se rechazan vectores corruptos o incompatibles. Los ejemplos de la misma familia tienen cosenos muy altos: la utilidad de esa agrupación sobre un histórico variado sigue pendiente de evaluación.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
.\.venv\Scripts\python.exe -m compileall -q backend tools
```

Node prepara los módulos locales de Three.js y ejecuta las pruebas JavaScript; el servidor de uso es Python. Resultados actuales y comandos de auditoría HTTP/proveedor en [VERIFICACION_MESA_CAD_2026-11-14.md](docs/VERIFICACION_MESA_CAD_2026-11-14.md); antecedentes en [VERIFICACION_PIEZAS_SEPARADAS.md](docs/VERIFICACION_PIEZAS_SEPARADAS.md).

Los DXF propios se pueden regenerar con:

```powershell
.\.venv\Scripts\python.exe -m tools.build_demo_fixture
.\.venv\Scripts\python.exe -m tools.build_parts_fixture
.\.venv\Scripts\python.exe -m tools.build_table_fixture
```

Las pruebas cubren unidades, vistas frente a cantidades, espesor ausente, cotas conflictivas, referencias aisladas, revisiones, geometría variable y cálculo económico independiente. Las pruebas del proveedor usan un doble de la frontera HTTP; no sustituyen el motor ni se presentan como inferencia live.

## Alcance y trabajo pendiente

- Lectura DXF: modelspace, bloques anidados y atributos, líneas y polilíneas rectas, círculos/arcos tipados, textos y cotas lineales o por ordenadas. ELLIPSE/SPLINE son aproximaciones visuales declaradas; no generan paneles ni medidas exactas. Se detectan filas regulares de círculos y líneas ocultas como evidencia neutral y se contrasta un catálogo de taller que por defecto no está confirmado. DXF recuperados requieren revisión. Límites: 100.000 entidades, 20.000 puntos por entidad y 200.000 por dibujo. Paperspace se clasifica y limita: anotaciones informativas, cotas que requieren revisión y no se proyectan a modelspace. HATCH, bulges y ARC con OCS negativo quedan fuera. No hay lector general de croquis, PDF, DWG ni muebles arbitrarios.
- La revisión de piezas separadas permite elegir asignación y completar cantidad o dimensiones desconocidas, con material/acabado y motivo. Dividir/unir componentes y crear elementos ocultos arbitrarios desde la interfaz quedan pendientes.
- Biblioteca geométrica/semántica de revisiones guardadas, separada del histórico económico de tres ejemplos inventados. Agrupación por componentes conexos y umbral, sin evaluación estadística de relevancia. No se infieren tiempos industriales, mecanizados, acabado cotizado ni impuestos. No es un presupuesto de fabricación completo.
- Reconstrucción por cajas de tableros según montaje revisado y niveles observados, sin traseras ocultas añadidas, mecanizados, uniones detalladas ni certificación de colisiones. Las ejecuciones antiguas se abren, pero para obtener cotas enriquecidas y vínculo al CAD original deben analizarse de nuevo.
- El endpoint legado local conserva ejecución síncrona. El perfil privado incorpora trabajos persistidos y seguimiento mediante polling; no se afirma procesamiento distribuido ni streaming de tokens o imágenes.
- PlankAssembly sigue separado y no se han publicado datos ni derivados. El incremento de evaluación añade un preparador local de muestra; conserva índices, excluye envolvente y trata normales ausentes. Preparar vistas no demuestra inferencia ni resuelve por sí solo las condiciones de uso; ver [PLANKASSEMBLY](docs/PLANKASSEMBLY.md) y la aceptación de producción.
- La comparación de métodos, evaluación con técnicos y medición de ahorro siguen pendientes; ver [COMPARATIVA_METODOS](docs/COMPARATIVA_METODOS.md).

## Documentación y coordinación

[Diseño inicial](docs/DEMO_IMPLEMENTACION.md), [ampliación del visor](docs/VISOR_RECONSTRUCCION_SIMILITUD.md), [proyectos open source evaluados](docs/OPEN_SOURCE.md), [coordinación](team/agente_coordinador.md), [A geometría](team/agente_geometria.md), [B backend](team/agente_backend.md), [C frontend](team/agente_frontend.md), [D evaluación](team/agente_evaluacion.md).

Los documentos [initial-plan.md](initial-plan.md), [PLAN.md](PLAN.md), [ARQUITECTURA](docs/ARQUITECTURA.md) y [CONTRATOS_DATOS](docs/CONTRATOS_DATOS.md) conservan el diseño amplio y sus pendientes. Los acuerdos [0.4 de piezas](docs/CONTRATO_PARTS_ONLY_0_4.md) y [0.5 de mesa](docs/CONTRATO_MESA_0_5.md) añaden sus recorridos; el envelope HTTP sigue en **0.2.0**, el export de mesa en **0.5.0** y sus descriptores son **furniture-v2/v3**. A/B acordaron los cambios y avisaron a C; [modelos.py](backend/app/contratos/modelos.py) es la fuente contractual. No todas las tareas T1–T13 están terminadas.

El preparador mecánico anterior continúa disponible. Esta entrega elimina sus diagnósticos de abstención del contexto público, verifica la referencia contra el manifiesto y consume los bytes verificados; los pilotos antiguos requieren regeneración para incorporar esas correcciones. No se ha redistribuido ni regenerado aquí el corpus externo. Véase [PILOTO_DATASET](docs/PILOTO_DATASET.md).
