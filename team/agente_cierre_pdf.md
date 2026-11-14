# Cierre PDF raster y frontera del proveedor

## Identidad y autorización

Agente de IA `cierre_pdf`, delegado por el agente raíz conforme a la solicitud explícita del usuario del 2026-11-14. No representa una identidad humana.

## Alcance y reservas

- Propiedad exclusiva durante este incremento: módulos de proveedor que resulten implicados (`backend/app/agente/provider.py`), `backend/app/general_furniture/live.py` solo si es necesario, nuevas pruebas de frontera/raster, `docs/VERIFICACION_PDF_RASTER.md` y este registro.
- No editar `backend/app/general_furniture/autonomous.py` ni contratos; pertenecen a `cierre_abstencion`.
- Preservar desconocidos métricos en raster sin escala, procedencia visual y límites de llamadas/tiempo.
- No registrar claves, prompts completos, payloads sensibles ni razonamiento interno.

## Tarea

Reproducir y explicar `provider_response_incomplete` del ensayo raster instrumentado, corregir la causa en la frontera del proveedor mediante TDD y dejar una aceptación HTTP local reproducible que complete el recorrido sin inventar dimensiones.

## Dependencias / avisos

- Coordinar cualquier cambio de interfaz con `cierre_abstencion`; no invadir su módulo.
- Avisar al agente raíz antes de cualquier llamada real pagada y limitarla a una o dos ejecuciones justificadas.
- Los cambios locales UX/auth y de otros agentes se preservan; no se harán commits, push ni despliegue.

## Estado

Cerrado y verificado. Las dos respuestas completas históricas consumieron 1.733 y 62 tokens de salida frente a 16.384, pero eso no permite inferir el consumo de la tercera respuesta incompleta: la telemetría antigua descartó `incomplete_details` y no conservó su `usage`. El submotivo histórico sigue sin observarse. Sí está observado que la primera propuesta fue rechazada por referencias de vista/documento incompatibles con el ledger raster, lo que forzó llamadas correctivas antes del fallo adicional del proveedor. El arreglo unifica la autoridad anunciada/aceptada y la aceptación real actual termina el recorrido sin dimensiones inventadas.

## Registro

- 2026-11-14: leídas reglas, plan de cierre, registros activos, contrato de pruebas y evidencia instrumentada.
- 2026-11-14: activados depuración sistemática, TDD y verificación basada en evidencia; sin cambios de producto todavía.
- 2026-11-14: RED→GREEN en frontera del proveedor, autoridad raster, referencias documentales, trazas/counters de error, diagnóstico HTTP sanitizado y relaciones de montaje aditivas en el prompt live.
- 2026-11-14: focal final `35 passed, 1 warning`; compilación y `git diff --check` correctos. Root ejecutará la suite global tras estabilizar todos los dominios.
- 2026-11-14: aceptación HTTP real única: fuente SHA-256 `7738983984818c30582ed989160386a3e51a1bef8ac522edae2043c69bf023a2`; job succeeded, run `run-7267675e450042d7af5ad956fdc0593b`, seis componentes, 18/18 ejes métricos unknown/null, cero vistas de ledger inventadas; informe SHA-256 `164cf7b5aa1e0080b9b60117c58493404533b845e238f0f7f1594ee369d1051c`. Servidor aislado detenido.
- 2026-11-14: el código exactamente cargado para ese ensayo quedó fingerprinted en `.runtime/pdf-raster-acceptance/code-manifest.json`. Después, sin reatribuir el resultado anterior, se refinó el prompt público con vocabulario canónico de roles y relaciones de montaje visibles/unknown/alternativas; assembly vacío solo cuando no hay par respaldado y se registra `assembly_not_identifiable`. Focal actual: 35 passed.
- 2026-11-14: corrección posterior solo en el árbol aislado `.worktrees/poc-closure`, sin proveedor: prompt/esquema/contexto publican gramática canonical `view|observation|contour|evidence|dimension:<id>`, refs documentales exactas y alias raw únicamente por compatibilidad cerrada/unívoca. El benchmark conserva traza/counters seguros de `GeneralLiveError` tanto antes como después de congelar baseline. RED observado en ambas regresiones; focal live+runner `18 passed`, `compileall` y `git diff --check` correctos.
- 2026-11-14: auditor raster reforzado offline en el árbol aislado: exige los tres estados dimensionales exactamente `unknown` además de valores nulos, y rechaza antes del job cualquier `geometry_analysis`, `scale_provenance` o `normalized_dxf` que otorgue autoridad métrica. Regresiones RED→GREEN cubren `conflict`/`hypothesis` nulos y las tres formas de autoridad; `6 passed`. El informe histórico conserva 18/18 estados `unknown`, y el manifiesto hijo conserva `geometry_analysis=false`, `scale_provenance=null`, `normalized_dxf=null`; no hubo nueva llamada pagada.
