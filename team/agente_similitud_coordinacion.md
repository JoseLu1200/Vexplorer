# Coordinación de reparación de similitud

Identidad: agente coordinador de IA, sin atribución de identidad humana. Autorización: solicitud explícita del usuario del 2026-11-14 de resolver los seis hallazgos mediante swarm GPT-6.1 Sol y revisión GPT-6 Astra; continuidad del esquema documentado en team/README.md.

## Alcance y propiedad

Coordinación, plan, integración, verificación y documentación de entrega. Motor: agente_similitud_motor; API: agente_similitud_biblioteca; UI: agente_similitud_interfaz; operaciones: agente_similitud_operacion; evaluación: agente_similitud_evaluacion. Cada agente mantiene su propio registro. Se preservan cambios preexistentes; las reservas históricas de tareas terminadas se transfieren únicamente para esta corrección. Contratos: un único escritor tras acuerdo motor/API y aviso a UI.

## Estado

Diagnóstico y desarrollo paralelo en curso. Confirmados orden por coseno, formato toFixed(3), diferencias parciales y agrupación por componentes conexos. Estado público y persistencia bajo inspección de operaciones. Sin cambios destructivos ni commits.

Actualización: el usuario precisó que Biblioteca pública debe contener solo muebles reales revisados; las tres ejecuciones remotas son demos, por lo que se conserva cero registros. La declaración de procedencia no certifica realidad ni identidad en un despliegue sin autenticación. El revisor Astra detectó además emparejamiento voraz subóptimo: sustituido por asignación húngara; comprobación independiente exhaustiva de 100 casos pequeños correcta.

Base pública descubierta durante integración: `cad-d0ea7a85e787`, distinta del checkout raíz `c94a888`. Se creó `.worktrees/similarity-public`, rama `fix/similarity-public`, desde `d0ea7a8` para portar exclusivamente esta corrección y conservar 35 rutas CAD posteriores. No se desplegará el snapshot viejo. El intento de worktree nativo falló por cwd padre sin Git; se utilizó fallback `git worktree add` en `.worktrees` ya ignorado.

Verificación raíz observada antes del traslado: 696 pruebas Python, 173 JavaScript; las pruebas completas se repetirán en la base pública integrada. QA navegador local comprobó diferencias por pieza, separación de scores y miniaturas reales de documentos. La revisión Astra y aceptación del candidato integrado siguen pendientes.

El usuario amplió la tarea con diagnóstico visual del generador en muebles complejos. Se auditan dos planos PlankAssembly de 14/16 piezas desde la base CAD, sin referencias privadas en la entrada del runtime; una salida distinta de la referencia no se considera automáticamente errónea cuando el plano admite alternativas. El flujo autoritativo usa trabajos autónomos `/jobs`, no el endpoint síncrono de preparación `/runs`.

## Verificación prevista

Pruebas focales, suites Python/JS, evaluación reproducible por familias, revisión Astra y comprobación de interfaz y publicación. No se equipara score técnico con compatibilidad económica ni certificación de fabricación.
