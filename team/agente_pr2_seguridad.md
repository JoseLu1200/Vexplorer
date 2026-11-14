# agente_pr2_seguridad — revisión e invalidación segura

## Identidad y autorización

- Nombre declarado por el usuario: agente_pr2_seguridad
- Rol: revisión de seguridad e integración PR2
- Archivo creado o designado explícitamente: autorización del swarm PR2 y transferencia del coordinador, 2026-11-14
- Última actualización: 2026-11-14, tras verificación enfocada

## Tarea de la sesión

- Objetivo concreto: invalidar de forma segura los embeddings de biblioteca al rotar el espacio y verificar concurrencia y fallos.
- Referencia del plan: revisión PR2 de precedentes 2.5/2.6
- Estado: terminado

## Alcance y reservas

- Archivos o carpetas que puedo editar: `backend/app/servicios/repository.py`, `backend/app/precedentes/regeneracion.py`, `backend/app/precedentes/espacio.py`, `backend/app/precedentes/api_embeddings.py`, pruebas enfocadas y este registro.
- Dependencias que solo leeré: contratos, aplicación principal y demás precedentes.
- Archivos compartidos que requieren coordinación: `repository.py`; transferencia explícita del coordinador.
- Solapes detectados y acuerdo para resolverlos: `hibrido.py` pertenece a otro agente y no se editará.

## Hecho en el último bloque

- Reproducido con tres pruebas rojas que la rotación no invalidaba, publicaba la referencia tras un fallo y competía con la regeneración.
- Añadida invalidación SQLite atómica por modelo/dimensiones antes de publicar la referencia.
- Rotación y regeneración comparten exclusión mutua dentro del proceso; los fallos devuelven un error genérico sin filtrar detalles.

## Siguiente bloque

- Entregar al coordinador el diff y sus límites operativos.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Borrar la caché de biblioteca por modelo/dimensiones antes de publicar la nueva referencia | Ante un fallo se conserva seguridad por defecto: vectores ausentes en vez de mezcla de espacios | transferencia del coordinador PR2 |

## Dependencias / avisos

- Necesito de: ninguna.
- Afecta a: regeneración y similitud semántica de la biblioteca de producción.
- Aviso realizado: hallazgo y secuencia recomendada comunicados al coordinador.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| TDD rojo | `python -m pytest -q backend/tests/test_precedentes_regeneracion.py -k "rotar_invalida or fallo_al_invalidar or rotacion_y_regeneracion"` | 3 fallos esperados | ejecución previa a la integración general |
| Suite enfocada | `python -m pytest -q backend/tests/test_precedentes_espacio.py backend/tests/test_precedentes_regeneracion.py` | 20 passed | no sustituye la suite global del coordinador |
| Sintaxis enfocada | `python -m py_compile backend/app/servicios/repository.py backend/app/precedentes/regeneracion.py backend/app/precedentes/espacio.py backend/app/precedentes/api_embeddings.py backend/tests/test_precedentes_regeneracion.py backend/tests/test_precedentes_espacio.py` | exit 0 | ejecutado durante la reconciliación |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: verificación global a cargo del coordinador.
- Reservas liberadas: archivos del alcance, 2026-11-14.
- Entrega a otra persona: coordinador PR2; el candado es local al proceso y la caché histórica está separada.
