# Agente CI semántica — reparación de dependencias

## Identidad y autorización

- Identidad: agente de IA de CI semántica; no representa a una persona.
- Autorización explícita: delegación del coordinador dentro del swarm autorizado por el usuario para reparar el bloqueo de CI necesario antes de integrar en `main`.
- Trabajo aislado en el worktree `semantic-lab`; el coordinador realizará commit, push, verificación global e integración.

## Tarea de la sesión

- Objetivo: corregir de forma mínima la instalación de dependencias de prueba en GitHub Actions.
- Estado: terminado; pendiente de commit, push y nuevo run por coordinación.

## Alcance y reservas

- Propiedad exclusiva de esta tarea: `.github/workflows/ci.yml` y este registro.
- Solo lectura: `pyproject.toml`, `requirements-demo.txt`, tests, código y registros del resto del equipo.
- La reserva histórica de `.github/workflows/*` del agente de operaciones queda transferida puntualmente por la delegación actual; no se modifica su registro.
- No modificar dependencias de runtime, modelos, contratos, código ni pruebas; no hacer commit ni push.

## Diagnóstico

- El run `43559606234` instaló solo `requirements-demo.txt` y falló durante la colección de cinco módulos de prueba.
- Errores observados: `ModuleNotFoundError` para `joblib`, `scipy` y `sklearn`.
- `pyproject.toml` ya declara `joblib`, `scipy` y `scikit-learn` en el extra `test`; `requirements-demo.txt` fija el stack demo pero no incluye esas tres dependencias.
- Hipótesis confirmada por configuración y log: CI no instala el extra que corresponde a la suite que ejecuta.

## Decisión

- Instalar `.[test]` después del entorno demo y usar `requirements-demo.txt` como constraints para conservar las versiones fijadas compartidas.
- No instalar `semantic-models`, Torch ni pesos/modelos.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Log remoto | `gh run view 43559606234 --log-failed` | salida 2; faltan `joblib`, `scipy` y `sklearn` en colección | evidencia del run anterior, no del workflow reparado |
| Resolución del extra | `python -m pip install --dry-run --ignore-installed --disable-pip-version-check --constraint requirements-demo.txt '.[test]'` | salida 0; resuelve `joblib 1.6.0`, `scipy 1.18.1` y `scikit-learn 1.9.1`, conserva las versiones fijadas compartidas y no incluye Torch/modelos | dry-run local Windows; no sustituye el nuevo run Ubuntu de Actions |
| Sintaxis YAML | `python -c "import yaml; ..."` sobre `.github/workflows/ci.yml` | salida 0; documento parseado y job `test-and-package` presente | `actionlint` no está instalado |
| Higiene del diff | `git diff --check -- .github/workflows/ci.yml team/agente_semantica_ci.md` | salida 0, sin diagnósticos | no ejecuta CI |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: commit/push, suite completa y nuevo run de GitHub Actions por coordinación.
- Reservas liberadas: `.github/workflows/ci.yml` y este registro tras esta entrega.
- Entrega: el coordinador ejecutará la suite completa y el nuevo CI.
