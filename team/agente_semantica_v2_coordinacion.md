# Coordinación semántica v2

Identidad: agente IA coordinador /root, autorizado explícitamente por el usuario el 2026-11-14 junto con registros nuevos agente_semantica_v2_*.md.

Objetivo: investigar y corregir roles, ocurrencias y montaje; ampliar corpus independiente y medir recuperación real sin convertir finalización técnica en aprobación de fabricación.

Asignación actual: inferencia posee live.py, autonomous.py, proposal.py, visual_evidence.py y pruebas; montaje posee assembly_semantics.py y pruebas; dataset posee prepare_semantic_corpus.py, pruebas y documentación corpus; evaluación posee semantic.py, adaptadores, sellado, runner y pruebas. Coordinación posee integración/documentación y review.py si resulta necesario. No se cambian contratos sin acuerdo A/B y aviso C. Registros anteriores son históricos y cambios locales se preservan.

Estado: diagnóstico paralelo. Copia del código previo en .runtime/semantic-v2-original para comparación. No se hacen commits ni despliegues en este incremento.

Validación prevista: tests de regresión primero, suite integrada, corpus mayor reproducible con separación proyecto/topología, ejecución live original/corregida con mismo proveedor sobre entradas públicas y freeze anterior al scoring. Reportar cobertura, TP/FP/FN y denominadores completos, errores de ejecución y límites de datos sintéticos.

Baseline verificada: python -m pytest -q → 701 passed in 88.10s. Snapshot código previo con SHA-256 por archivo en .runtime/semantic-v2-original/snapshot-sha256.json.

Detectada sesión concurrente independiente de montaje 3D: team/agente_assembly_*.md, evaluation/assembly.py y pruebas nuevas. No se modifican sus archivos. Benchmark corregido aislado en .runtime/semantic-v2-corrected-code antes de nuevas mutaciones; original en snapshot separado. Los fallos de colección de assembly ajeno no se atribuyen al incremento semántico.

Verificación final integrada observada: python -m pytest -q → 765 passed in 145.12s. Ruff producto/evaluación/tools modificados All checks passed; git diff --check limpio. Snapshots original172 y corregido176 archivos .py sin discrepancias hash; configuración de30 inputs, modelos y budgets idéntica. Benchmark aún en curso.

Auditoría de diferencias entre snapshots: modelos.py incluye ampliaciones aditivas concurrentes de montaje3D/escena. No cambian contratos de propuesta/crítico ni se invoca assembly_live en este runner; se conservan hashes para transparencia. La comparación semántica ignora los nuevos campos opcionales de escena.

Verificado en ambos snapshots: hash canónico de todos los parameters de herramientas de propuesta y revisión idéntico, 4e773c074cb114a1b5c7c43a79aeba5e0f83e0d955523d5b16e84f16e017ecb6. La ampliación concurrente de modelos no cambia la interfaz evaluada.

Hallazgo visual dev antes de scoring: sx001/source0 muestra V1/top y V2/side superpuestas. Generador usa width+depth+200 para tercera vista aunque segunda ocupa width. Se solicita fix v2 con test separación espacial, preservación v1 y generación rev3 nueva; rev2 runs se conservan diagnóstico de layout defectuoso y NO puntúan como benchmark principal. Referencias de scoring aún cerradas. Runtime permanece congelado.

Cierre tests posterior a fixes generador/anotación: python -m pytest -q →793 passed in128.36s. Configuraciones principales idénticas en30entradas/modelos/presupuestos; diferencia públicosrev3 vsrev4erratum=0. Queda scoring tras ambosfreezes.

Entrega final:30/30 ejecuciones porversión; 0/30 casoscompletos contra referencia. Reviewed F1 roles .2184→.2543, ocurrencias .1972→.2529, relaciones0→0 con90tripletas noadmitidas (gold cerrado/noexhaustivo y vocabulariosdesalineados). No se declara problemafuncionalresuelto. Informe docs/RESULTADOS_SEMANTICA_V2.md; resultados .runtime/semantic-v2-results/summary.md y derivation-manifest.json. Nativefreezes anteriores referencias; re-freeze adapter posterior apertura documentado. Testsúltimos52focales pasan, suite previa793pasa; sin commit ni despliegue.

## Integración y producción autorizadas (2026-11-14)
El usuario solicita explícitamente git add, commit, push, integración en main y despliegue en producción. Se coordina con la sesión de integración general y montaje para mantener un único integrador y preservar CAD, semántica y montaje. Se incluyen los cuatro documentos finales pendientes; el código ya está registrado en 48dac99 y sucesores.
