# Verificación de la primera demo

Fecha: 2026-11-13. Rama de integración: `demo/first-executable`. Base: `c09a6f9`, `main` actualizado con fast-forward. Agentes de implementación GPT-6.1 Sol; revisión final solicitada a GPT-6 Astra. No se ha publicado ni desplegado.

## Entorno y comandos observados

Windows, PowerShell, Python 3.14.2 y Node 25.8.1. Entorno virtual nuevo creado con `python -m venv .venv`; instalación `python -m pip install -e ".[test]"` dentro del entorno terminó correctamente. Versiones congeladas en `requirements-demo.txt`.

Servidor y frontend arrancaron con:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

`GET /api/v1/health` devolvió HTTP 200. El puerto 8000 estaba restringido por Windows; se comprobó 8765. El frontend se sirve desde el mismo proceso.

Arranque live comprobado con una clave local preexistente, sin imprimirla:

```powershell
$env:OPENAI_MODEL="gpt-6.1-sol"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --env-file .env
```

## Pruebas automatizadas

Verificación final integrada y repetida por GPT-6 Astra: `python -m pytest -q`: **55 passed**; `npm test --prefix frontend`: **35 passed**. `compileall` terminó correctamente y `pip check` no encontró dependencias incompatibles. Hay un aviso de deprecación del adaptador TestClient/httpx de Starlette; no falla la suite.

Cobertura comprobada: conversión pulgadas/mm y unidades desconocidas, conservación del espesor ausente, distinción vistas/cantidad, trapecio fuera del subconjunto rectangular, cotas angulares o conflictivas, límite de entidades, esquema Pydantic estricto, escenarios excluyentes, derivación desde premisas, revisión obsoleta, tarifa compatible, costes de todas las piezas y coste fijo una vez, exportación completa, datos públicos sin diagnósticos de abstención, hash/ruta/manifiesto y consumo de bytes verificados.

El E2E de evaluación ejecuta la API real con el proveedor desactivado y las referencias privadas inaccesibles durante el runtime. Congela el resultado antes de compararlo con el oráculo independiente. Las referencias solo las abre el test evaluador. No se afirma rendimiento ciego ni precisión sobre muebles reales.

## Recorrido de navegador observado

- Carga del DXF propio por el formulario y peticiones reales a FastAPI; 3 vistas, 15 paths, 4 cotas observadas y 2 escenarios.
- Selección de fila y resaltado por IDs; propuestas de laterales, tapa, base y baldas, con espesor desconocido.
- Decisión de ensayo registrada como agente coordinador, sin atribuirla a un técnico humano real: montaje entre laterales, espesor 18 mm, material/acabado sintéticos y motivo.
- Revisión 2: largos de tapa/base/baldas 864 mm; estados por campo observado/calculado/confirmado.
- Comparables explicados con dimensiones de conjunto; estimación 127,84 EUR: 40 fijos y 87,84 material a 50 EUR/m². Factor 1,464 mostrado sin ocultar precisión necesaria.
- Descarga JSON desde botón y comprobación HTTP 200 del bundle: resultado revisión 2, 4 grupos de piezas, 3 comparables, estimación y eventos humanos/económicos.
- Consola del navegador sin errores ni warnings en el recorrido.
- Live real con GPT-6.1 Sol: HTTP 201, `needs_review`, 2 escenarios. El adaptador usa evidencia vectorial, no imágenes. El proveedor no se sustituyó por mocks ni por replay.

El control de subida del conector de navegador rechazó la ruta local por su comprobación de workspace. Para el ensayo se introdujeron los mismos bytes del DXF propio en un objeto File del input; después se ejecutaron el formulario y los endpoints normales. No se inyectaron resultados de inferencia.

Fallos encontrados y corregidos durante integración: DIMLFAC 100 del generador, cotas no lineales tratadas como mm, ocultación de propuestas cuando pieces estaba vacío, URLs estáticas incorrectas, overlay visible pese a hidden, estados antiguos, coste solo de la primera pieza, ancho del comparable confundido con largo de lateral y exportación sin estimación. Las regresiones pertinentes están versionadas.

## Estado de revisión final

**Dictamen GPT-6 Astra: SHIP**, tras revisar y revalidar las correcciones, sin hallazgos críticos ni importantes pendientes. Código revisado hasta `5c340a7`.

Astra reprodujo dos fallos importantes: la revisión manual podía sumar escenarios incompatibles y la descomposición admitía trapecios por su caja envolvente. Las regresiones ahora verifican `422 incompatible_scenario_selection` sin alterar la revisión vigente y `422 unsupported_geometry`. También se conserva explícitamente el escenario elegido por el agente en ejecución, resultado y traza.

El navegador verificó restauración por URL y recarga, revisión 3 con espesor 20 mm y montaje cubriendo laterales (1160/900/860 mm), invalidación de la estimación anterior y nuevo total 127,60 EUR. Cargar la variante incompleta limpió formulario/presupuesto y mostró solo tres cotas, con grosor desconocido. La versión final live registró las herramientas reales `inspeccionar_evidencia` y `entregar_despiece`, sus referencias y `scenario-between-sides`, en la ejecución `run-35bdf551d7624e65a1cd046e7861ccb7`. No se expusieron argumentos libres, prompts ni secretos.

`git diff --check c09a6f9` informa espacios de descripciones de tipos de línea generados por ezdxf y líneas finales adicionales en algunos artefactos. Es ruido de formato conocido, no una prueba limpia ni un fallo funcional. Se conserva el DXF reproducible tal como lo genera ezdxf.

## Límites

Un caso sintético propio y su variante; la construcción reservada puede contener componentes que la entrada no determina. La demo propone una construcción compatible, no adivina la referencia. La corrección humana aquí se ensayó por agentes; no se ha medido ahorro con técnicos. Histórico y tarifas inventados, horas desconocidas, material/preparación únicamente. Comparación visual directa, embeddings, división/unión de componentes desde UI, corpus PlankAssembly, DWG/PDF y procesamiento multiusuario siguen pendientes. Replay no habilitado. Los pilotos mecánicos antiguos requieren regeneración para eliminar las pistas de sus metadatos; aquí se corrigieron código y pruebas, sin redistribuir datos externos.
