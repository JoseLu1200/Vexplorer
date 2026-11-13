# Vexplorer — primera demo local

Vexplorer convierte un plano DXF pobre de una **estantería rectangular** en dos propuestas de montaje, permite revisarlas y calcula una estimación provisional con histórico y tarifas sintéticos. La demo usa un caso propio de desarrollo; no acredita precisión industrial ni ahorro de tiempo con técnicos.

Recorrido implementado: **plano 2D → evidencia → hipótesis de piezas → revisión humana → comparables → estimación explicada → ficha JSON/CSV y traza**.

## Instalación y arranque (PowerShell)

Desde la raíz del repositorio, con Python 3.11 o posterior:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

Abrir **http://127.0.0.1:8765**. FastAPI sirve también el frontend JS/HTML: no hay otro proceso ni compilación de assets. `geometry_only` funciona sin credenciales. Se han comprobado estos comandos en Windows con Python 3.14.2; [requirements-demo.txt](requirements-demo.txt) registra las versiones de ese entorno. Para repetir esas versiones en un entorno compatible, instalar con `-c requirements-demo.txt`.

Los documentos, resultados y revisiones se conservan en `.vexplorer-data/`, ignorado por Git. Instancia local de un operador, sin autenticación multiusuario; mantener el bind en `127.0.0.1`. No se ha desplegado al VPS.

## Guion de demo

1. Cargar [estanteria_montada.dxf](data/planos_demo/estanteria_montada.dxf) y pulsar **Analizar DXF** en modo **Solo geometría**.
2. Seleccionar **Baldas interiores**. Revisar sus regiones de origen, las tres vistas y las cotas observadas. Las propuestas son hipótesis; el espesor y los largos que dependen del montaje permanecen desconocidos.
3. Comparar **Tapa y base entre laterales** con **Tapa y base cubren laterales**. Son escenarios excluyentes.
4. Para el ensayo, elegir el primero, indicar persona revisora, espesor `18`, material `tablero sintético`, acabado `melamina sintética` y motivo. Estos valores son una decisión técnica de demostración, no datos añadidos por el modelo.
5. Registrar la decisión. La revisión 2 conserva la 1 y calcula `900 − 2 × 18 = 864 mm` para tapa, base y baldas. Cambiar el espesor o el montaje crea otra revisión.
6. Consultar los tres comparables y calcular la estimación. En ese escenario: área total `1,7568 m²`, material a `50 EUR/m²` = `87,84 EUR`; preparación fija `40 EUR`, aplicada una sola vez. Total provisional **127,84 EUR**. Las horas permanecen desconocidas.
7. Exportar **ficha JSON** para conservar resultado, revisión, comparables, estimación y acciones. El CSV ofrece la tabla de piezas. Abrir la traza para revisar las acciones.
8. Cargar [estanteria_incompleta.dxf](data/planos_demo/estanteria_incompleta.dxf). Falta la observación corta: el espesor permanece desconocido hasta que se aporte una confirmación humana.

La entrada no contiene una BOM ni nombres de piezas. La referencia propia está en [evaluation/reference](evaluation/reference/README.md), reservada a las pruebas del evaluador; las herramientas y endpoints del producto no la sirven ni la leen. El caso es de desarrollo inspeccionado, no un benchmark ciego. El test congela la salida antes de abrir la referencia.

## Modos

- **geometry_only**: reglas geométricas y dos escenarios explícitos de la familia admitida; no llama a un proveedor.
- **live**: OpenAI Responses con herramientas nativas `inspeccionar_evidencia` y `entregar_despiece`, bucle propio y validación local. El modelo inspecciona datos vectoriales estructurados y propone uno de los escenarios disponibles. **No recibe imágenes ni demuestra visión directa o descomposición libre de cualquier mueble.**
- **recorded_replay**: no habilitado; el servidor lo rechaza porque no existe un mecanismo de replay admitido con grabaciones verificadas.

Para live, configurar `OPENAI_API_KEY` en un `.env` local ignorado por Git. [`.env.example`](.env.example) muestra los nombres, sin credenciales. Con la clave ya configurada:

```powershell
$env:OPENAI_MODEL="gpt-6.1-sol"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --env-file .env
```

Los errores de proveedor se muestran como tales; no se convierten en resultados geométricos etiquetados live. Límites: 15 llamadas de modelo, 30 herramientas, 2 reparaciones estructurales y 120 segundos para la fase del agente. Nunca incorporar `.env` a Git.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
.\.venv\Scripts\python.exe -m compileall -q backend tools
```

Node solo es necesario para las pruebas JavaScript. La aplicación no necesita npm para arrancar. Resultados observados, recorrido de navegador y revisión final en [VERIFICACION_DEMO.md](docs/VERIFICACION_DEMO.md).

Los DXF propios se pueden regenerar con:

```powershell
.\.venv\Scripts\python.exe -m tools.build_demo_fixture
```

Las pruebas cubren unidades, vistas frente a cantidades, espesor ausente, cotas conflictivas, referencias aisladas, revisiones, geometría variable y cálculo económico independiente. Las pruebas del proveedor usan un doble de la frontera HTTP; no sustituyen el motor ni se presentan como inferencia live.

## Alcance y trabajo pendiente

- Subconjunto DXF: modelspace, LINE, LWPOLYLINE recta, TEXT/MTEXT y cotas lineales admitidas. Se requieren vistas FRONT/TOP/SIDE o RIGHT coherentes y reconocibles. No hay lector general de croquis, PDF, DWG, bloques, curvas o muebles arbitrarios.
- La revisión permite elegir montaje, cambiar espesor y aportar material/acabado; dividir/unir componentes y confirmar elementos ocultos desde la interfaz quedan pendientes.
- Histórico de tres ejemplos inventados, recuperación por atributos y cálculo de material/preparación. Sin embeddings, tiempos industriales, operaciones de mecanizado, acabado cotizado, impuestos ni precisión empresarial validada. No es un presupuesto de fabricación completo.
- Ejecución local síncrona y traza persistida; no se afirma procesamiento distribuido ni streaming de tokens o imágenes.
- PlankAssembly sigue separado: no se han publicado datos ni derivados. Su adaptación futura exige preservar índices, excluir la envolvente, manejar normales ausentes y resolver condiciones de uso; ver [PLANKASSEMBLY](docs/PLANKASSEMBLY.md).
- La comparación de métodos, evaluación con técnicos y medición de ahorro siguen pendientes; ver [COMPARATIVA_METODOS](docs/COMPARATIVA_METODOS.md).

## Documentación y coordinación

[Diseño e integración de esta demo](docs/DEMO_IMPLEMENTACION.md), [registro coordinador](team/agente_coordinador.md), [A geometría](team/agente_geometria.md), [B backend](team/agente_backend.md), [C frontend](team/agente_frontend.md), [D evaluación](team/agente_evaluacion.md).

Los documentos [initial-plan.md](initial-plan.md), [PLAN.md](PLAN.md), [ARQUITECTURA](docs/ARQUITECTURA.md) y [CONTRATOS_DATOS](docs/CONTRATOS_DATOS.md) conservan el diseño amplio y sus pendientes. El contrato ejecutable de esta demo es **0.2.0**, acordado por A/B y comunicado a C; su fuente única es [modelos.py](backend/app/contratos/modelos.py). No todas las tareas T1–T13 del plan amplio están terminadas.

El preparador mecánico anterior continúa disponible. Esta entrega elimina sus diagnósticos de abstención del contexto público, verifica la referencia contra el manifiesto y consume los bytes verificados; los pilotos antiguos requieren regeneración para incorporar esas correcciones. No se ha redistribuido ni regenerado aquí el corpus externo. Véase [PILOTO_DATASET](docs/PILOTO_DATASET.md).
