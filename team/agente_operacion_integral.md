# Agente de operación integral — copias y preparación de release

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA de operación integral; no representa a una persona.
- Rol: respaldo/recuperación y preparación operativa del swarm GPT-6.1 Sol.
- Archivo creado y designado explícitamente: `team/agente_operacion_integral.md`, delegación renovada el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: ampliar copias consistentes para los almacenes de mueble general e histórico, conservar todos los originales/derivados bajo `documents/`, probar restauración consultable y preparar la actualización del host sin desplegarla.
- Referencia del plan: cierre operativo de T11–T13 y `docs/superpowers/plans/2026-11-14-transcript-completion.md`.
- Estado: en curso.

## Alcance y reservas

- Archivos o carpetas que puedo editar: `tools/backup.py`, `tests/test_backup.py`, `deploy/production.env.example`, documentación operativa coordinada y este registro.
- Dependencias que solo leeré: `backend/`, `frontend/`, contratos, adaptadores de ingesta, histórico e integración.
- Archivos compartidos que requieren coordinación: rutas de SQLite y variables de entorno con backend general, histórico e integración.
- Solapes detectados y acuerdo para resolverlos: `team/agente_operacion.md` reservó estos archivos para la entrega privada ya terminada; esta delegación explícita amplía esa operación para el release nuevo, sin tocar sus otros artefactos.

## Hecho en el último bloque

- Backup v2 implementado con snapshot online de `vexplorer.sqlite3`, `general_furniture.sqlite3` e `history.sqlite3`, documentos recursivos, alias externos seguros y restore v1 compatible.
- Restore probado consultando filas reales tras copiar bases abiertas en WAL; originales PDF/DWG, preview y manifiesto de conversión conservados.
- LibreDWG 0.14 oficial verificado localmente contra dos pares DWG/DXF y compilado/empaquetado para Linux con licencia GPL; binario aislado preparado en el host sin cambiar env ni reiniciar.
- Host inspeccionado en solo lectura: release actual activo, dependencias coherentes, ODA ausente y disco al 95%.

## Siguiente bloque

- Esperar `CLEARANCE`, benchmark/autonomous smoke, suite final y commit raíz; generar el paquete exclusivamente desde ese commit y ejecutar el runbook final sin reutilizar candidatos anteriores.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | No desplegar ni reiniciar antes de autorización final de coordinación | Evitar alterar el release aceptado antes de la revisión Astra y verificaciones conjuntas | Delegación de `/root` |
| 2026-11-14 | Cada SQLite se copiará con la API online, nunca como archivo crudo | WAL puede contener transacciones confirmadas no volcadas al archivo principal | Requisito operativo delegado |
| 2026-11-14 | Usar LibreDWG como fallback comercialmente desplegable y conservar ODA desactivado | ODA comunitario limita a no comercial; LibreDWG es GPLv3 y el adapter valida el DXF resultante | Fuentes oficiales y smoke con pares reales |
| 2026-11-14 | La aceptación manual de 16 checks es regresión, no evidencia autónoma | La entrega exige proposer live, crítico Astra multimodal y reparación sin paso humano | Ampliación explícita del usuario |

## Dependencias / avisos

- Necesito de: backend general/histórico/integración para nombres finales y defaults.
- Afecta a: package de release y procedimiento de actualización/restauración.
- Aviso realizado: consultas enviadas a los tres responsables antes de editar código.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Backup multistore RED | `.venv/Scripts/python.exe -m pytest tests/test_backup.py -q` | 10 fallos esperados: formato v1, DBs omitidas y API sin aliases | Antes de implementación |
| DB inválida RED | `.venv/Scripts/python.exe -m pytest tests/test_backup.py::test_backup_rejects_invalid_additional_database_without_publishing_archive -q` | fallo esperado: `sqlite3.DatabaseError` escapaba | Antes de normalizar error |
| Backup GREEN | `.venv/Scripts/python.exe -m pytest tests/test_backup.py -q` | 28 passed | Incluye namespaces/aliases de archivo adversos |
| Focal conjunta | `.venv/Scripts/python.exe -m pytest backend/tests/test_ingesta_pdf.py backend/tests/test_ingesta_dwg.py tests/test_backup.py tests/test_evaluation_metrics.py -q` | 48 passed | Sin red |
| Suite Python | `.venv/Scripts/python.exe -m pytest -q` | 520 passed, 1 warning deprecado de Starlette/httpx | Evidencia fresca posterior al hardening de backup |
| Lint focal | `ruff check tools/backup.py tests/test_backup.py` | correcto | Ruff no está en venv; ejecutado desde instalación disponible |
| LibreDWG Windows real | `dwg2dxf 0.14` + `parse_dxf` en dos pares CADBLOCK | 130/896 entidades; unidades, tipos y bounds iguales a pares DXF | Warnings LibreDWG en clases no respaldadas; no prueba fidelidad universal |
| LibreDWG Linux remoto | conversión aislada + lector del release actual | `m`, escala 1000, 130 entidades, 0 warnings del parser | Servicio y env no modificados |
| Package candidato | extracción nueva + `GET /api/v1/health` | 200; 119 entradas, SHA-256 `78061f34cf1364c29d440043b0752802cf28172db5d4d6ef264a800e0aac22f9` | Obsoleto: archivos de app cambiaron después; no desplegar y regenerar tras freeze |
| Empaquetador aislado | dry run de `build-final-package.ps1` sobre `b877594` | Worktree detached limpio, tar desde commit y health 200 | Artefacto/worktree de ensayo eliminados; esperar checkpoint final |

## Bloqueos y cierre

- Bloqueos: despliegue requiere `CLEARANCE` final de coordinación/Astra, smoke autónomo/benchmark, suite final y commit raíz; el árbol continúa cambiando.
- Pendientes: package inmutable del commit final, backup/restore remoto previo, env autónomo, aceptación live y carga API de datasets públicos aprobados.
- Reservas liberadas: no.
- Entrega a otra persona: pendiente.
