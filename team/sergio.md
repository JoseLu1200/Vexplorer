# sergio — coordinación de trabajo

## Identidad y autorización

- Nombre declarado por el usuario: Sergio Sande Cendán
- Rol: Coordinador / Evaluación e Integración (D / General)
- Archivo creado o designado explícitamente: Solicitado por el usuario ("crea mi archivo y ve metiendo toda la documentacion"), 2026-11-14 00:54 CET
- Última actualización: 2026-11-14 00:56 CET

## Tarea de la sesión

- Objetivo concreto: Descarga de cambios desde `main`, ejecución de suite de aceptación integrada (cantidades, incógnitas, reconstrucción, invariancia del descriptor y aislamiento de referencia), ejecución de tests de JavaScript de frontend y verificación de recorrido visual en navegador.
- Referencia del plan: T11–T13 / P0 / Aceptación integrada 0.3.0
- Estado: terminado

## Alcance y reservas

- Archivos o carpetas que puedo editar: `team/sergio.md` (y documentación personal autorizada)
- Dependencias que solo leeré: `team/*.md`, `backend/`, `frontend/`, `tests/`, `data/planos_demo/`, `evaluation/`
- Archivos compartidos que requieren coordinación: `CLAUDE.md`, `team/README.md`
- Solapes detectados y acuerdo para resolverlos: ninguno comprobado.

## Hecho en el último bloque

- `git pull origin main`: integración fast-forward completada sin conflictos (`b07b204` -> `dab7ce5`).
- Configuración de entorno local: virtualenv `.venv` con dependencias instaladas de `requirements-demo.txt`.
- Ejecución de suite de aceptación integrada de evaluación (`tests/test_demo_*.py`):
  - **Cantidades**: 6 ocurrencias físicas en lugar de 3 vistas (2 laterales, techo, base, 2 baldas).
  - **Incógnitas**: espesor desconocido conservado, bloqueo de piezas sólidas en `estanteria_incompleta.dxf`, unidades desconocidas y rechazo 422 de geometrías no soportadas (trapecio).
  - **Reconstrucción**: volumen calculado independiente (31.622.400 mm³), fórmulas de balda explícitas (900 - 2*18 = 864 mm) y versionado de revisiones 1 y 2.
  - **Invariancia del descriptor**: idéntico descriptor y fingerprint para mueble trasladado; similitud 1.0; agrupamiento determinista repetible.
  - **Aislamiento de referencia**: mock protector que deniega lecturas a `evaluation/reference/` durante runtime; las referencias privadas solo se leen tras congelar resultados.
  - **Resultado**: 28 pasaron (100%), 0 fallos.
- Ejecución de la suite total Python: 119 pruebas pasadas (`pytest -q`), 0 fallos.
- Ejecución de la suite de frontend: 46 pruebas pasadas (`npm test --prefix frontend`), 0 fallos.
- Recorrido y verificación visual en navegador real:
  - Servidor FastAPI arrancado en `http://127.0.0.1:8765`.
  - Navegador subagente abrió y verificó `http://127.0.0.1:8765`.
  - Elementos UI confirmados: Cabecera, selector de modo de análisis (`Solo geometría`), visor SVG con grilla y controles de zoom/paneo, barra de estado de documento activo, panel de pestañas (Inspector, Revisar, Biblioteca, Coste), tabla de despiece ligado al plano y cajón auditable de traza.
  - 0 errores de consola JavaScript, todas las peticiones con respuesta HTTP 200 OK.
  - Captura y hechos de navegación verificados por el host.

## Siguiente bloque

- Mantener actualizada la bitácora según los siguientes pasos de desarrollo o validación con cliente/técnico.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Creación de archivo personal `team/sergio.md` | Cumplimiento estricto del protocolo `CLAUDE.md` a petición explícita del usuario | Solicitud directa en chat |
| 2026-11-14 | Ejecución de frontend tests y navegación aislada | Validar extremo a extremo la experiencia de usuario y ausencia de regresiones en cliente | Verificación automatizada con Node y subagente navegador |

## Dependencias / avisos

- Necesito de: B (backend) y C (frontend) para cualquier cambio de esquema de API o componentes de UI.
- Afecta a: Verificación de estado del proyecto en la raíz.
- Aviso realizado: Ninguno requerido; trabajo en solo lectura de código y edición exclusiva de `team/sergio.md`.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Suite de evaluación integrada (D) | `.venv\Scripts\python.exe -m pytest tests/test_demo_workbench.py tests/test_demo_fixture.py tests/test_demo_isolation.py tests/test_demo_e2e.py -v` | 28 passed, 1 warning (StarletteDeprecation) | Sin fallos |
| Suite completa Python | `.venv\Scripts\python.exe -m pytest -q` | 119 passed, 1 warning | Sin fallos |
| Pruebas unitarias de Frontend | `npm test --prefix frontend` | 46 passed | 0 errores |
| Verificación navegador interactivo | Navegación a `http://127.0.0.1:8765` en subagente de navegador | UI 100% funcional, 0 errores en consola, 13/13 peticiones HTTP 200 | Host-observed facts confirmados |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: ninguno inmediato.
- Reservas liberadas: servidor local en puerto 8765 cerrado tras finalizar la inspección.
