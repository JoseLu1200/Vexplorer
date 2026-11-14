# Vexplorer — planos, piezas y reconstrucción revisable

Vexplorer permite explorar **vistas DXF 2D de piezas separadas**, asociarlas mediante identificadores explícitos del plano, obtener dimensiones y cantidades trazables y proponer su montaje como **estantería rectangular**. La revisión humana permite completar datos desconocidos antes de reconstruir sus tableros en 3D. Una biblioteca local recupera y agrupa revisiones mediante atributos geométricos o embeddings semánticos reales; el cálculo económico usa tarifas sintéticas.

Recorrido: **plano y cotas → piezas y explicación → revisión → reconstrucción 3D → similares y grupos → ficha, estimación y traza**. Los casos son propios y de desarrollo; no acreditan generalización, precisión industrial ni ahorro medido con técnicos.

La [verificación de piezas separadas](docs/VERIFICACION_PIEZAS_SEPARADAS.md) recoge esta entrega. La [auditoría anterior](docs/AUDITORIA_APP_2026-11-14.md) conserva los resultados y fallos de `dab7ce5`; no describe el estado de las correcciones posteriores. La siguiente ampliación solicitada —mesa desde vistas montadas con cotas parciales y planos derivados acotados— se documentará por separado cuando esté implementada y comprobada.

## Instalación y arranque (PowerShell)

Desde la raíz del repositorio, con Python 3.11 o posterior y Node/npm:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
npm ci --prefix frontend
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

Abrir **http://127.0.0.1:8765**. FastAPI sirve también el frontend JS/HTML: no hay otro proceso de frontend. `npm ci` prepara Three.js local, sin CDN durante el uso. La geometría, el visor, la revisión y la similitud geométrica funcionan sin credenciales. Instalación comprobada en Windows con Python 3.14.2 y Node 25.8.1; [requirements-demo.txt](requirements-demo.txt) registra las dependencias Python verificadas. Para repetir esas versiones en un entorno compatible, instalar con `-c requirements-demo.txt`.

Los documentos, resultados y revisiones se conservan en `.vexplorer-data/`, ignorado por Git. Instancia local de un operador, sin autenticación multiusuario; mantener el bind en `127.0.0.1`. No se ha desplegado al VPS.

Si ya existe una biblioteca antigua con descriptores v1, puede conservarse y abrir una instancia separada para v2; los grupos semánticos rechazan mezclar ambas versiones:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from dotenv import load_dotenv; load_dotenv(); import uvicorn; from backend.app.main import create_app; uvicorn.run(create_app(data_dir=Path('.runtime/demo-parts')),host='127.0.0.1',port=8765)"
```

## Guion de demo

1. Cargar [piezas_completo.dxf](data/planos_demo/piezas_completo.dxf), seleccionar **Piezas separadas** y **Solo geometría**, y pulsar **Abrir**. La entrada contiene nueve vistas de tres tipos de panel, sin montaje ni modelo 3D.
2. Seleccionar **Pieza K2**: ver sus tres vistas, cotas y fuentes en el inspector. La cantidad `2` procede de `QTY K2 2`, no del número de vistas. Sus dimensiones son `864 × 300 × 18 mm`.
3. En **Revisar**, comparar las asignaciones de K2/K3 a tapa/base o baldas. Son hipótesis compatibles, no funciones reveladas por sus identificadores. El ancho montado calculado es `864 + 18 + 18 = 900 mm`.
4. Elegir una asignación, indicar persona revisora, material `tablero sintético`, acabado `melamina sintética` y motivo. Registrar la decisión crea la revisión 2; no cambia las evidencias observadas.
5. Abrir **3D**: seis ejemplares, órbita, selección y **Despiece 3D**. La posición de las baldas es esquemática y explícitamente hipotética; las colisiones no se evalúan. No es un modelo certificado para fabricación.
6. En **Biblioteca**, guardar la revisión. Repetir con [dimensiones distintas](data/planos_demo/piezas_dimensiones_variante.dxf), [identificadores y posición distintos](data/planos_demo/piezas_ids_trasladados.dxf) y [espesor de 36 mm](data/planos_demo/piezas_espesor_36.dxf). Buscar y agrupar en **Geométrico · offline**. Cambiar identificadores/posición conserva el descriptor; cambiar espesor lo modifica incluso con igual envolvente montada.
7. Con proveedor configurado, elegir **Semántico · modelo real** y guardar cada revisión para generar su embedding. Buscar y agrupar usa los vectores guardados; no llama al modelo en cada consulta. Se identifica modelo, dimensión y método; el coseno no es una probabilidad.
8. En **Coste**, consultar comparables sintéticos y calcular: material `1,7568 m² × 50 EUR/m² = 87,84 EUR`; preparación `40 EUR`, una sola vez; total **127,84 EUR**. Horas desconocidas. Exportar ficha JSON con escena, explicaciones, descriptor, biblioteca, resultado y traza; CSV para la tabla de piezas.
9. Probar [cantidad desconocida](data/planos_demo/piezas_qty_desconocida.dxf), [espesor desconocido](data/planos_demo/piezas_espesor_desconocido.dxf) y [asociación ambigua](data/planos_demo/piezas_ambigua_sin_id.dxf). Los faltantes se conservan; una revisión puede aportar cantidad o medidas con su motivo. Sin asociación suficiente no se fuerza un montaje.

El formato admitido para asociar vistas es texto visible `PART <clave> FRONT|TOP|SIDE`; la cantidad usa `QTY <clave> <entero>`. Los ejes locales son FRONT largo/ancho, TOP largo/espesor y SIDE espesor/ancho. No es reconocimiento general de dibujos sin etiquetas. La opción **Vistas montadas · legado** conserva la primera demo con [estanteria_montada.dxf](data/planos_demo/estanteria_montada.dxf).

La entrada no contiene una BOM ni nombres de piezas. La referencia propia está en [evaluation/reference](evaluation/reference/README.md), reservada a las pruebas del evaluador; las herramientas y endpoints del producto no la sirven ni la leen. El caso es de desarrollo inspeccionado, no un benchmark ciego. El test congela la salida antes de abrir la referencia.

## Modos

- **geometry_only**: extracción y candidatos deterministas compatibles de la familia admitida; no llama a un proveedor.
- **live**: OpenAI Responses con herramientas nativas, bucle propio y validación local. El modelo inspecciona evidencias estructuradas y propone un escenario disponible; las explicaciones conservan fuentes, fórmulas y premisas. **No recibe imágenes ni demuestra visión directa o descomposición libre de cualquier mueble.**
- **recorded_replay**: no habilitado; el servidor lo rechaza porque no existe un mecanismo de replay admitido con grabaciones verificadas.

Para live, configurar `OPENAI_API_KEY` en un `.env` local ignorado por Git. [`.env.example`](.env.example) muestra los nombres, sin credenciales. Con la clave ya configurada:

```powershell
$env:OPENAI_MODEL="gpt-6.1-sol"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --env-file .env
```

Los errores de proveedor se muestran como tales; no se convierten en resultados geométricos etiquetados live. Límites: 15 llamadas de modelo, 30 herramientas, 2 reparaciones estructurales y 120 segundos para la fase del agente. Nunca incorporar `.env` a Git.

Los embeddings son independientes del modo de análisis del DXF. Usan `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` y `OPENAI_EMBEDDING_DIMENSIONS=256` por defecto. Se generan mediante una acción explícita de guardado semántico. La caché distingue descriptor, modelo y dimensiones; se rechazan vectores corruptos o incompatibles. Los ejemplos de la misma familia tienen cosenos muy altos: la utilidad de esa agrupación sobre un histórico variado sigue pendiente de evaluación.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
.\.venv\Scripts\python.exe -m compileall -q backend tools
```

Node prepara los módulos locales de Three.js y ejecuta las pruebas JavaScript; el servidor de uso es Python. Resultados de esta entrega en [VERIFICACION_PIEZAS_SEPARADAS.md](docs/VERIFICACION_PIEZAS_SEPARADAS.md); antecedentes en [VERIFICACION_DEMO.md](docs/VERIFICACION_DEMO.md) y [VISOR_RECONSTRUCCION_SIMILITUD.md](docs/VISOR_RECONSTRUCCION_SIMILITUD.md).

Los DXF propios se pueden regenerar con:

```powershell
.\.venv\Scripts\python.exe -m tools.build_demo_fixture
.\.venv\Scripts\python.exe -m tools.build_parts_fixture
```

Las pruebas cubren unidades, vistas frente a cantidades, espesor ausente, cotas conflictivas, referencias aisladas, revisiones, geometría variable y cálculo económico independiente. Las pruebas del proveedor usan un doble de la frontera HTTP; no sustituyen el motor ni se presentan como inferencia live.

## Alcance y trabajo pendiente

- Inferencia DXF: modelspace, LINE, LWPOLYLINE recta, TEXT/MTEXT y cotas lineales admitidas. Requiere vistas FRONT/TOP/SIDE o RIGHT coherentes. El SVG visual admite más grafismo, como bloques y curvas, pero eso no amplía las piezas inferibles. No hay lector general de croquis, PDF, DWG ni muebles arbitrarios.
- La revisión de piezas separadas permite elegir asignación y completar cantidad o dimensiones desconocidas, con material/acabado y motivo. Dividir/unir componentes y crear elementos ocultos arbitrarios desde la interfaz quedan pendientes.
- Biblioteca geométrica/semántica de revisiones guardadas, separada del histórico económico de tres ejemplos inventados. Agrupación por componentes conexos y umbral, sin evaluación estadística de relevancia. No se infieren tiempos industriales, mecanizados, acabado cotizado ni impuestos. No es un presupuesto de fabricación completo.
- Reconstrucción por cajas de tableros según montaje revisado y niveles observados, sin traseras ocultas añadidas, mecanizados, uniones detalladas ni certificación de colisiones. Las ejecuciones antiguas se abren, pero para obtener cotas enriquecidas y vínculo al CAD original deben analizarse de nuevo.
- Ejecución local síncrona y traza persistida; no se afirma procesamiento distribuido ni streaming de tokens o imágenes.
- PlankAssembly sigue separado: no se han publicado datos ni derivados. Su adaptación futura exige preservar índices, excluir la envolvente, manejar normales ausentes y resolver condiciones de uso; ver [PLANKASSEMBLY](docs/PLANKASSEMBLY.md).
- La comparación de métodos, evaluación con técnicos y medición de ahorro siguen pendientes; ver [COMPARATIVA_METODOS](docs/COMPARATIVA_METODOS.md).

## Documentación y coordinación

[Diseño inicial](docs/DEMO_IMPLEMENTACION.md), [ampliación del visor](docs/VISOR_RECONSTRUCCION_SIMILITUD.md), [proyectos open source evaluados](docs/OPEN_SOURCE.md), [coordinación](team/agente_coordinador.md), [A geometría](team/agente_geometria.md), [B backend](team/agente_backend.md), [C frontend](team/agente_frontend.md), [D evaluación](team/agente_evaluacion.md).

Los documentos [initial-plan.md](initial-plan.md), [PLAN.md](PLAN.md), [ARQUITECTURA](docs/ARQUITECTURA.md) y [CONTRATOS_DATOS](docs/CONTRATOS_DATOS.md) conservan el diseño amplio y sus pendientes. El [acuerdo 0.4](docs/CONTRATO_PARTS_ONLY_0_4.md) añade observaciones, asignaciones de ejemplares y montaje hipotético; mantiene el envelope **0.2.0** y usa descriptor **furniture-v2** separado del anterior. A/B acordaron los cambios y avisaron a C; [modelos.py](backend/app/contratos/modelos.py) es la fuente contractual. No todas las tareas T1–T13 están terminadas.

El preparador mecánico anterior continúa disponible. Esta entrega elimina sus diagnósticos de abstención del contexto público, verifica la referencia contra el manifiesto y consume los bytes verificados; los pilotos antiguos requieren regeneración para incorporar esas correcciones. No se ha redistribuido ni regenerado aquí el corpus externo. Véase [PILOTO_DATASET](docs/PILOTO_DATASET.md).
