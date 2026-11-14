# Semantic Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** ejecutar y comparar métodos reales de recuperación, clasificación y agrupación de planos de muebles.
**Architecture:** laboratorio CLI aislado, manifiesto común, renders/características desde DXF; modelos opcionales producen vectores; evaluador separa train/validation/test.
**Tech Stack:** Python, ezdxf/Pillow, NumPy/scikit-learn; modelos locales según compatibilidad comprobada.
**Spec:** `docs/superpowers/specs/2026-11-14-semantic-lab.md`.

## Global Constraints
- Agentes de trabajo GPT-6.1 Sol; revisión final GPT-6 Astra.
- Propiedad de archivos disjunta; no editar contratos ni runtime productivo.
- Datos, pesos y artefactos grandes fuera de Git.
- No leakage de etiquetas, nombres, carpetas ni test a representación o selección.

## Review Focus
- Duplicados o variantes cruzando particiones.
- Etiquetas/rutas entrando accidentalmente a texto o vectores.
- PCA/escalado/hiperparámetros ajustados al test.
- Clusters de un elemento aparentando pureza perfecta.
- Modelo no ejecutado o fixture sintético presentado como evidencia real.

## Tasks
- [x] Scout datos/hardware/modelos y congelar corpus/configuración.
- [x] Dataset y representaciones geométricas reproducibles; tests de neutralidad de nombres y split.
- [x] Evaluador de clasificación/retrieval/clusters/PCA con pruebas de métricas y separación.
- [x] Ejecutar al menos una vía aprendida viable; registrar errores verificables de candidatos incompatibles.
- [x] Comparar en validación y confirmar una configuración congelada en test; CLI de consulta e informe.
- [x] Regresión y revisión final independiente Astra; corregir hallazgos antes de entregar.

## Ledger
- Worktree `experiment/semantic-furniture`, base `4209510`; dos scouts Sol en curso.
- Decisión: autorización de experimentar permite un spike local; la elección de ganador queda condicionada a resultados, no a una promesa de precisión.
- Preflight: corpus primario 118 candidatos de cuatro categorías editoriales (sofas/simple-tables/buffets/beds); las escenas living-room/dining-sets se excluyen del experimento primario por solapamiento de clases.
- Disco: pesos/entorno/artefactos en `D:/Vexplorer-semantic-lab`; no llenar C ni copiar datasets.
- Entorno de modelos independiente reutiliza torch global CUDA 12.8 mediante system-site-packages; versiones exactas se registrarán junto a resultados.

| Tareas | Interfaz/propiedad | Revisión previa |
|---|---|---|
| Datos / evaluación | JSON samples del spec | Etiqueta/ruta sólo metadata; grupos disjuntos comprobados por evaluador |
| Datos / modelos | image_path + text | El encoder recibe bytes/texto, nunca etiqueta o nombre del archivo |
| Modelos / evaluación | NPZ ids + embeddings | Verificar IDs únicos, cobertura, finitud e identidad del manifiesto |
| Componentes / producto | V2/V3 sólo lectura | Métrica experimental separada, sin contratos/API cambiados |
| Datos | dataset.py/features.py y test propio | Render neutral, agrupación previa al split, features sin fit |
| Evaluación | evaluate.py/query.py y test propio | Train fit, validation select, test opt-in final |
| Modelos | encode.py y test propio | Sin ediciones deps por agente; GPU sólo este agente |
| Componentes | components.py y test propio | Controles sintéticos explícitos, no benchmark real |

- Regla de coordinación: root mantiene pyproject/docs; cada agente mantiene sólo su registro, módulos y tests asignados. Ningún worker toca main ni crea commits.
- Cierre: ocho espacios aprendidos reales, 228 configuraciones validation, ganador EG2 mixto768+kNN5 sinPCA. Test único 16/18, macro-F1 0,826128, BA 0,833333, P@5 0,888889; no se retocó tras test.
- Revisión final GPT-6 Astra aprobada para spike aislado; corregidos masa cero LP, guard de config para futuras corridas, dependencia SciPy y cifra DINO. Limitaciones y evidencia histórica pre-guard explícitas en `docs/SEMANTIC_LAB_2026-11-14.md`.
- Regresión final root: 466 passed en 60,66 s; Ruff, compileall, diff-check y consulta CLI correctos. No commit/merge/despliegue.

## Ampliaciones posteriores cerradas

- El usuario solicitó documentación Markdown detallada y git add/commit/push de la rama, y añadió pruebas de otros datasets y comparación con Jev. El cierre inicial anterior se conserva como histórico.
- Se probaron 373 CAD adicionales, 30 vistas Plank, 14 DXF mecánicos y 53 casos de aplicación sobre snapshots identificados, además de la importación de cuatro presupuestos públicos.
- La comparación posterior de clasificadores añadió logística/boosting sobre EG2 y 320 solicitudes reales a Jev 1.14 texto/imagen. Se documenta como retrospectiva; no se reinterpreta como un nuevo test ciego ni se integra en el producto.
- La entrega ampliada aprobó 509 tests en 90,64 s y revisión Astra. El [índice final](../../semantic-lab/README.md) organiza metodología, resultados, reproducción, evidencia y verificación de publicación.
