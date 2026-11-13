# Vexplorer — planos, piezas y reconstrucción revisable

Vexplorer permite explorar un plano DXF, consultar sus vistas y cotas, proponer piezas de una **estantería rectangular**, revisar el montaje y reconstruir sus tableros en 3D. Una biblioteca local recupera y agrupa muebles mediante atributos geométricos o embeddings semánticos reales. Conserva la estimación provisional con tarifas sintéticas de la primera demo.

Recorrido: **plano y cotas → piezas y explicación → revisión → reconstrucción 3D → similares y grupos → ficha, estimación y traza**. Los casos son propios y de desarrollo; no acreditan generalización, precisión industrial ni ahorro medido con técnicos.

La [auditoría de API y navegador del 14/11/2026](docs/AUDITORIA_APP_2026-11-14.md) documenta lo observado en `dab7ce5`, sus fallos reproducibles y sus límites. Esa versión parte de vistas del conjunto montado; **no resuelve todavía el nuevo recorrido desde vistas DXF de piezas separadas**.

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

## Guion de demo

1. Cargar [estanteria_montada.dxf](data/planos_demo/estanteria_montada.dxf) y pulsar **Abrir** en modo **Solo geometría**.
2. Explorar **Todas**, **Alzado**, **Planta** y **Lateral**. Usar zoom, arrastre, encuadre y controles de geometría/textos/cotas. **CAD original** muestra la representación SVG nativa de ezdxf; sus coordenadas de página no son medidas del ledger.
3. Seleccionar **Baldas interiores** para localizar su evidencia. El inspector muestra fuentes, premisas, fórmulas e incógnitas. El espesor y los largos condicionados al montaje permanecen desconocidos antes de la revisión.
4. En **Revisar**, comparar los dos montajes excluyentes. Para el ensayo, elegir **Tapa y base entre laterales**, indicar persona revisora, espesor `18`, material `tablero sintético`, acabado `melamina sintética` y motivo. Son premisas de demostración aportadas en la revisión.
5. Registrar la decisión: revisión 2, con `900 − 2 × 18 = 864 mm` para tapa, base y baldas. Abrir **3D**: seis ocurrencias físicas, órbita, selección y **Despiece 3D**. Las cajas son esquemáticas y las colisiones no se evalúan. Cambiar montaje o espesor crea otra revisión y descarta la escena anterior.
6. En **Biblioteca**, guardar la revisión. Repetir con [mueble_demo_002.dxf](data/planos_demo/mueble_demo_002.dxf) y [mueble_demo_003.dxf](data/planos_demo/mueble_demo_003.dxf), revisar y guardar. Buscar similares y agrupar en modo **Geométrico · offline**. [mueble_demo_004.dxf](data/planos_demo/mueble_demo_004.dxf) es el original trasladado: conserva el descriptor.
7. Con proveedor configurado, elegir **Semántico · modelo real** y guardar cada revisión para generar su embedding. Buscar y agrupar usa los vectores guardados; no llama al modelo en cada consulta. Se identifica modelo, dimensión y método; el coseno no es una probabilidad.
8. En **Coste**, consultar comparables sintéticos y calcular: material `1,7568 m² × 50 EUR/m² = 87,84 EUR`; preparación `40 EUR`, una sola vez; total **127,84 EUR**. Horas desconocidas. Exportar ficha JSON con escena, explicaciones, descriptor, biblioteca, resultado y traza; CSV para la tabla de piezas.
9. Probar [estanteria_incompleta.dxf](data/planos_demo/estanteria_incompleta.dxf), [unidades desconocidas](data/planos_demo/mueble_demo_unidades_desconocidas.dxf) y [trapecio](data/planos_demo/mueble_demo_trapecio.dxf). Se conserva el plano cuando no hay despiece admitido; sin unidad no se añaden milímetros, y sin revisión no se generan sólidos.

La entrada no contiene una BOM ni nombres de piezas. La referencia propia está en [evaluation/reference](evaluation/reference/README.md), reservada a las pruebas del evaluador; las herramientas y endpoints del producto no la sirven ni la leen. El caso es de desarrollo inspeccionado, no un benchmark ciego. El test congela la salida antes de abrir la referencia.

## Modos

- **geometry_only**: reglas geométricas y dos escenarios explícitos de la familia admitida; no llama a un proveedor.
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

Node prepara los módulos locales de Three.js y ejecuta las pruebas JavaScript; el servidor de uso es Python. Resultados de la primera demo en [VERIFICACION_DEMO.md](docs/VERIFICACION_DEMO.md) y de esta ampliación en [VISOR_RECONSTRUCCION_SIMILITUD.md](docs/VISOR_RECONSTRUCCION_SIMILITUD.md).

Los DXF propios se pueden regenerar con:

```powershell
.\.venv\Scripts\python.exe -m tools.build_demo_fixture
```

Las pruebas cubren unidades, vistas frente a cantidades, espesor ausente, cotas conflictivas, referencias aisladas, revisiones, geometría variable y cálculo económico independiente. Las pruebas del proveedor usan un doble de la frontera HTTP; no sustituyen el motor ni se presentan como inferencia live.

## Alcance y trabajo pendiente

- Inferencia DXF: modelspace, LINE, LWPOLYLINE recta, TEXT/MTEXT y cotas lineales admitidas. Requiere vistas FRONT/TOP/SIDE o RIGHT coherentes. El SVG visual admite más grafismo, como bloques y curvas, pero eso no amplía las piezas inferibles. No hay lector general de croquis, PDF, DWG ni muebles arbitrarios.
- La revisión permite elegir montaje, cambiar espesor y aportar material/acabado; dividir/unir componentes y confirmar elementos ocultos desde la interfaz quedan pendientes.
- Biblioteca geométrica/semántica de revisiones guardadas, separada del histórico económico de tres ejemplos inventados. Agrupación por componentes conexos y umbral, sin evaluación estadística de relevancia. No se infieren tiempos industriales, mecanizados, acabado cotizado ni impuestos. No es un presupuesto de fabricación completo.
- Reconstrucción por cajas de tableros según montaje revisado y niveles observados, sin traseras ocultas añadidas, mecanizados, uniones detalladas ni certificación de colisiones. Las ejecuciones antiguas se abren, pero para obtener cotas enriquecidas y vínculo al CAD original deben analizarse de nuevo.
- Ejecución local síncrona y traza persistida; no se afirma procesamiento distribuido ni streaming de tokens o imágenes.
- PlankAssembly sigue separado: no se han publicado datos ni derivados. Su adaptación futura exige preservar índices, excluir la envolvente, manejar normales ausentes y resolver condiciones de uso; ver [PLANKASSEMBLY](docs/PLANKASSEMBLY.md).
- La comparación de métodos, evaluación con técnicos y medición de ahorro siguen pendientes; ver [COMPARATIVA_METODOS](docs/COMPARATIVA_METODOS.md).

## Documentación y coordinación

[Diseño inicial](docs/DEMO_IMPLEMENTACION.md), [ampliación del visor](docs/VISOR_RECONSTRUCCION_SIMILITUD.md), [proyectos open source evaluados](docs/OPEN_SOURCE.md), [coordinación](team/agente_coordinador.md), [A geometría](team/agente_geometria.md), [B backend](team/agente_backend.md), [C frontend](team/agente_frontend.md), [D evaluación](team/agente_evaluacion.md).

Los documentos [initial-plan.md](initial-plan.md), [PLAN.md](PLAN.md), [ARQUITECTURA](docs/ARQUITECTURA.md) y [CONTRATOS_DATOS](docs/CONTRATOS_DATOS.md) conservan el diseño amplio y sus pendientes. La ampliación **0.3.0** añade escena, biblioteca y modelos del visor, manteniendo lectura de resultados y envelope **0.2.0**. A/B acordaron los cambios y avisaron a C; [modelos.py](backend/app/contratos/modelos.py) es la fuente contractual. No todas las tareas T1–T13 están terminadas.

El preparador mecánico anterior continúa disponible. Esta entrega elimina sus diagnósticos de abstención del contexto público, verifica la referencia contra el manifiesto y consume los bytes verificados; los pilotos antiguos requieren regeneración para incorporar esas correcciones. No se ha redistribuido ni regenerado aquí el corpus externo. Véase [PILOTO_DATASET](docs/PILOTO_DATASET.md).
