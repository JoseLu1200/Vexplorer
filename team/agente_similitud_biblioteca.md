# Agente biblioteca y recuperación

Responsabilidad: integración API de biblioteca/similitud y recuperación durable de jobs en
`main.py`/`servicios/repository.py`, con contratos aditivos coordinados.

## Acuerdos vigentes

- Backend aprobó `technical_score`, warnings, complete-link, referencias equivalentes y el
  checkpoint de revisión con CAS; UI consume esos nombres sin reinterpretar el coseno.
- Recuperación: `POST /api/v1/jobs/{id}/resume` crea un intento nuevo
  `review_from_saved_proposal`, no continúa la llamada anterior ni repite el proponente.
- `GET /api/v1/jobs/{id}` expone `checkpoint` y `recovery`; `GET /api/v1/runs/{id}` añade
  `latest_job`, siempre actor-scoped. Una propuesta recuperada sigue siendo provisional.
- Timeout total: 300 s local y 600 s producción; cada intento de revisión queda limitado a
  300 s. Los presupuestos se exponen en `recovery`.
- `job_retries` conserva un único sucesor por fuente/actor. Mezclar `retry_from_start` y
  `resume_review` responde `job_recovery_action_conflict`.
- Contrato de evidencia acordado con backend: `GeneralEvidenceDisposition`,
  `evidence_dispositions` en propuesta/draft/review y targets cerrados
  `evidence_region:{candidate_region_id}`.

## Evidencia focal (2026-11-14)

- `test_job_recovery.py + test_private_jobs.py + test_general_furniture_evidence_accounting.py`:
  26 passed.
- `test_general_furniture_evidence_accounting.py + test_general_furniture_autonomous.py`:
  34 passed.
- Ruff en archivos propios: limpio; `py_compile` de main/repositorio/contratos: limpio.

