# Agente de datos semánticos — laboratorio aislado

## Identidad y autorización

- Identidad: agente de IA de datos semánticos; no representa a una persona.
- Autorización: swarm GPT-6.1 Sol solicitado por el usuario el 2026-11-14, con revisión final GPT-6 Astra.
- Trabajo local aislado en `experiment/semantic-furniture`; sin despliegue ni cambios al producto.

## Alcance y reservas

- Propiedad exclusiva: `tools/semantic_lab/__init__.py`, `tools/semantic_lab/dataset.py`, `tools/semantic_lab/features.py`, `tests/test_semantic_lab_dataset.py` y este registro.
- Solo lectura: corpus externo `cadblock_2d`, especificación, plan y módulos del producto.
- Fuera de alcance: contratos, backend, frontend, evaluación/modelos ajenos, dependencias, commits y despliegue.

## Tarea

Preparar un benchmark reproducible de DXF reales con cuatro categorías proxy limpias, representaciones geométricas deterministas, renders sin texto/cotas y particiones por grupos previas a cualquier ajuste. Mantener rutas, nombres, categorías y títulos fuera de features, texto y embeddings.

## Decisiones y límites

- Las carpetas de CADBlock son etiquetas proxy editoriales, no verdad humana.
- Cada DXF completo es una muestra; sus múltiples vistas en modelspace no se cuentan como objetos físicos distintos.
- Los pares DWG no son muestras adicionales.
- Duplicados exactos y de render canónico comparten grupo; las familias inferidas por nombre, si se registran, son solo metadatos y no prueban independencia.
- Geometría con Z no nula se excluye de este benchmark 2D con motivo explícito.

## Estado

- Implementación terminada por TDD; sin cambios fuera de la reserva y sin commit.
- Manifiesto congelado en `D:/Vexplorer-semantic-lab/data/core/manifest.json` con SHA-256 `15f2448895806c85c0647da72413bfc8de39f5a6fe71d535121303f1d03f00fe`.
- Resultado: 118 candidatos, 117 muestras admitidas, una exclusión por geometría Z no nula; 89 grupos; partición 82/17/18.
- Etiquetas: beds 21, buffets 21, simple-tables 32, sofas 43. `buffets` representa equipamiento comercial de cocina/servicio, no aparadores domésticos; `simple-tables` también contiene sillas y oficina.
- QA visual: `qa_train_montage.png` y `qa_validation_montage.png` junto al manifiesto, fuera de Git.
- Modelos y evaluación recibieron directamente ruta, hash, distribución y advertencias anti-leakage.

## Verificación

- TDD observado: fallaron primero import/API, agrupación de variantes y neutralidad a anotaciones; después quedaron verdes.
- `python -m pytest tests/test_semantic_lab_dataset.py -q` → 5 passed.
- `python -m compileall -q tools/semantic_lab` → correcto, sin salida.
- `python -m pytest -q` → 457 passed in 55.84s.
- `git diff --check -- tools/semantic_lab tests/test_semantic_lab_dataset.py team/agente_semantica_datos.md` → correcto, sin salida.
