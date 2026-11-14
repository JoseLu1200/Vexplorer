# Vexplorer

> Estado documental (2026-11-14): este archivo conserva requisitos y checkpoints históricos; las frases sobre ausencia de aplicación o contratos pendientes no describen el estado vigente. Consulta [README](README.md) y la auditoría completa. Las reglas de coordinación y arquitectura siguen aplicándose.

Hackathon: a partir de un plano (DWG/DXF) genera un **despiece** (lista de piezas con nombre, cantidad, largo, ancho, grosor y contornos de origen). Contexto y decisiones de arquitectura completos en [`initial-plan.md`](initial-plan.md): léelo antes de tocar nada.

La [transcripción](transcripcion-contexto-poc.md) concreta el objetivo: inferir piezas y secciones desde planos pobres, y orientar costes y tiempos mediante muebles históricos similares. [CASO_DE_USO_Y_EVALUACION](docs/CASO_DE_USO_Y_EVALUACION.md) distingue el hito técnico de la prueba de concepto completa, sin cambiar las reglas de equipo ni aprobar contratos nuevos.

## Stack

- **Python 3.11+**, backend con **FastAPI** (HTTP + SSE para la traza del agente en vivo).
- Agente LLM con el *tool use* nativo de la API y un **bucle propio** (~50 líneas). **Sin LangChain ni frameworks de agentes pesados.**
- Contrato de datos (piezas, contornos) con **Pydantic**. Es la única fuente de verdad del formato JSON.
- Geometría DXF: `ezdxf` (+ `shapely` si hace falta). La conversión DWG → DXF usa ODA File Converter (binario externo).
- Tests con `pytest`; lint/formato con `ruff`.
- Frontend (tabla, traza en vivo, visor three.js) es JS/HTML y vive aparte en `frontend/`. Lo lleva la Persona C.

> Las dependencias concretas se fijan en `pyproject.toml` cuando exista. Si falta una librería, añádela ahí y avisa en tu archivo de equipo; no instales cosas "en local" sin declararlas.

## Estructura prevista

```text
backend/app/
  api/           FastAPI: endpoints + SSE
  ingesta/       DWG→DXF, unidades, limpieza
  geometria/     motor determinista (sin IA): vistas, contornos, cotas → piezas candidatas
  herramientas/  funciones + esquemas JSON que ve el agente
  agente/        bucle del LLM (máx. ~15 iteraciones, timeout, logging total)
  validador/     comprobaciones deterministas (cotas generales, solapes)
  salida/        JSON → tabla/CSV + cajas 3D
  contratos/     modelos Pydantic compartidos (piezas, contornos)
backend/tests/
frontend/
data/planos_demo/   planos de prueba + respuestas cacheadas para la demo
team/               un .md por integrante (ver abajo)
```

La estructura se crea según se necesita; no generes carpetas vacías por adelantado.

## Reglas de arquitectura (no negociables sin acuerdo del equipo)

1. El **motor geométrico trabaja antes que el agente** y es determinista: nada de IA ahí.
2. La salida del agente es una **herramienta** (`entregar_despiece(piezas)`) con esquema estricto. Nunca se parsea texto libre.
3. **Trazabilidad:** cada pieza guarda los ids de los contornos de origen.
4. El **validador cierra el ciclo**: si falla, el error vuelve al agente como mensaje y este corrige.
5. **Plan B de demo:** si la API falla o tarda, se muestra el resultado del motor geométrico solo. Respuestas de los planos de demo en caché.
6. El agente tiene límite de iteraciones y de tiempo, y **registra todo** (alimenta la traza en pantalla).
7. **Cambiar el contrato de `contratos/` requiere acuerdo explícito entre Persona A y Persona B** (y aviso a C). Si te lo piden sin ese acuerdo, para y avisa.

## Flujo de equipo: archivo personal obligatorio antes de editar código

Cada integrante tiene su propio archivo en `team/<nombre>.md` (formato en [`team/_TEMPLATE.md`](team/_TEMPLATE.md), índice y roles en [`team/README.md`](team/README.md)). Sirve para que **todas las sesiones de Claude sepan en todo momento quién está haciendo qué**.

### Al empezar cualquier sesión

1. Lee `team/README.md` y **todos** los `team/*.md` (salvo `_TEMPLATE.md`). Ese es tu mapa de quién trabaja en qué y qué archivos/carpetas tiene reservados cada uno.

### Antes de editar código (cualquier archivo fuera de `team/` y de la documentación)

2. Pregunta quién es el usuario si no lo ha dicho. **No lo deduzcas** de `git config` ni de nada más.
3. Comprueba que esa persona ha **creado su archivo o designado uno existente** para esta tarea. Tiene que ser explícito por parte del usuario:
   - Si no hay archivo: **no edites código.** Ofrece crearlo desde `team/_TEMPLATE.md` y pide los datos que falten (nombre, rol, tarea, alcance). Créalo solo cuando el usuario lo confirme.
   - Si el usuario designa uno existente (p. ej. "usa `team/ana.md`"): úsalo, léelo y confirma que la tarea de la sesión encaja con lo que ahí pone. Si no encaja, propón actualizarlo antes de seguir.
   - Un archivo ajeno **no vale**: nadie edita bajo el archivo de otra persona.
4. Comprueba **solapes**: si el alcance (carpetas/archivos) de la tarea choca con el de otro integrante en `team/*.md`, avisa al usuario antes de editar y propón coordinarse. No pises el trabajo de otro.
5. Si la tarea pedida queda **fuera del alcance** declarado en el archivo, para y pregunta si se amplía el alcance (y se anota en el archivo) o si se hace otra cosa.

### Mientras trabajas

6. Mantén el archivo personal **al día** como parte del propio cambio: estado, qué se ha hecho, qué queda, decisiones y bloqueos. Actualízalo al terminar cada bloque de trabajo, no solo al final.
7. Edita solo **tu** archivo de `team/`. Los de los demás se leen, no se modifican.
8. Si tu trabajo depende de, o afecta a, algo de otra persona (contrato, endpoint, herramienta), anótalo en la sección "Dependencias / avisos" de tu archivo.

### Excepciones (no requieren archivo personal)

- Leer código, explicar, revisar y responder preguntas.
- Crear o editar tu propio archivo en `team/`.

Cualquier otro cambio de código sin archivo personal asociado está prohibido.

## Convenciones de código

- Tipado (`type hints`) en funciones públicas; modelos de datos con Pydantic, no dicts sueltos.
- Código en inglés o español, pero **consistente por módulo**; los nombres de herramientas del agente van en español como en el plan (`entregar_despiece`).
- Unidades siempre en **milímetros** dentro del backend; normalizar en la ingesta.
- Funciones del motor geométrico y del validador **puras y deterministas** (mismo plano → mismo resultado) para poder testearlas y cachear la demo.
- Toda herramienta del agente: esquema JSON estricto + test con datos falsos (*mocks*) que funcione sin llamar a la API.
- Sin secretos en el repo: claves de API por variables de entorno (`.env` ignorado por git).
- Commits pequeños y frecuentes; prefija el mensaje con el área (`geometria:`, `agente:`, `validador:`, `api:`, `frontend:`, `team:`).

## Comandos

Existe tooling local de preparación, todavía no backend ni frontend: `python -m pytest -q` y `python -m tools.prepare_evaluation --source ../engineering_dataset --audit-only`. Instalación y generación en [PILOTO_DATASET](docs/PILOTO_DATASET.md). El `pyproject.toml` de raíz declara solo estas herramientas; no afirmar comandos de servidor o lint aún inexistentes.

## Datos disponibles y estado de preparación

[PlankAssembly](docs/PLANKASSEMBLY.md) está descargado y auditado: 26.707 modelos oficiales de tableros, coordenadas en mm y referencia de componentes. El ZIP no incluye planos 2D; generación de vistas y exportación DXF están pendientes. La primera fila de `planks` es envolvente, y algunos JSON carecen de `normal`. El permiso de descarga no cambia la licencia CC BY-NC-ND 4.0 ni acredita permiso comercial adicional.

## Modelo de embeddings: solo EmbeddingGemma 2

Decisión del equipo (2026-11-14): el único modelo de embeddings para similitud es **EmbeddingGemma 2** (`google/embeddinggemma-2`, clave `embeddinggemma2`). Los demás (DINOv3, MiniLM, OpenAI `text-embedding-3-small`) ya se probaron en el [laboratorio semántico](docs/semantic-lab/README.md) y se descartan. No propongas ni añadas trabajo nuevo con ellos.

Estado del código tras la migración del runtime del 2026-11-14:

- El runtime textual de biblioteca e histórico usa EmbeddingGemma 2 desde un snapshot local fijado, 768 dimensiones, normalización L2 y prompt `SentenceSimilarity`. No descarga pesos en ejecución; si faltan el snapshot o las dependencias declara la capacidad no disponible.
- El runtime textual y el explorador mixto son espacios distintos. No se fabrican imágenes para registros históricos textuales ni se comparan vectores OpenAI heredados con EmbeddingGemma 2.
- El explorador semántico ya lee espacios preparados con `tools/prepare_semantic_explorer.py`, cuyo modelo por defecto es `embeddinggemma2`.
- `dinov3` y `minilm` solo quedan como opciones en `tools/semantic_lab/encode.py` y `tools/prepare_semantic_explorer.py` (laboratorio). DINOv3 en `tools/reconstruction3d/low_memory.py` es parte del pipeline de reconstrucción 3D, no un embedding de similitud: no se ve afectado.

El [piloto mecánico](docs/PILOTO_DATASET.md) conserva sus 17 casos y tooling; no procesa PlankAssembly. Estas constataciones no amplían automáticamente contratos, endpoints o formatos de entrada implementados. No hay resultados de inferencia ni histórico económico verificado.
