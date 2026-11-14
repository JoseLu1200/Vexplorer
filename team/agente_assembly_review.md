# Agente assembly review — revisión independiente

## Identidad y alcance

- Agente delegado `assembly_review`; revisor de solo lectura del contrato, geometría, runtime, persistencia, visor y evaluador del montaje general.
- Revisión limitada al diseño y plan aprobados del 2026-11-14 y a los archivos de producto relacionados. No se consultaron referencias privadas.
- Última actualización: 2026-11-14, congelado final.

## Veredicto

No quedan hallazgos Critical/Important de implementación pendientes. Se aprueba el cierre técnico del alcance con una limitación de producto explícita: el caso real `plank-030` conserva 16 colocaciones que concuerdan con la referencia en dimensiones, posición y orientación tras una sola alineación global, pero el validador público las rechaza por penetraciones AABB mayores de 1 mm sin geometría observada de mecanizado que las explique. No es un montaje aceptado ni una aprobación para fabricar.

## Hallazgos corregidos durante la revisión

- Visor: aplica la rotación firmada al `THREE.Mesh`, conserva identidad por ocurrencia y usa el AABB mundial autoritativo para el centro sin deformar las dimensiones locales.
- Core: exige escala métrica, transformación de determinante +1, cantidades/ocurrencias completas, evidencia física no reutilizada salvo oclusión explícita, marcos coherentes, residuo de contorno separado del ruido numérico y tolerancia de penetración separada del contacto.
- Core: se retiró el bypass crítico que permitía justificar colisiones con una afirmación de mecanizado no verificada. Un solape mayor de 1 mm sigue bloqueando.
- Runtime: esquema estricto compatible con Responses, argumentos JSON validados correctamente, contexto autoritativo con revisión esperada e imágenes públicas acotadas, una sola tool call, fuentes permitidas, plazos posteriores a proveedor/evaluador y diagnósticos seguros persistentes.
- Persistencia: CAS por revisión y cancelación durable atómica con el `INSERT` aceptado; una cancelación no puede perder la carrera y publicar después una escena aceptada.
- Alternativas: se conservan alternativas aceptadas distintas y la ambigüedad es visible.
- Evaluador: una sola rotación ortogonal propia, una sola traslación global refinada y una biyección global; informa penetración absoluta y penetración no explicada sin cambiar el criterio relativo aprobado.
- UI: un candidato rechazado nunca sustituye la escena normal. Su inspección 3D requiere opt-in, queda marcada como rechazada/no validada, se reinicia al cambiar contexto y deshabilita acciones productivas. El selector explícito de eje vertical aplica una única rotación global propia a todas las posiciones y orientaciones, sin modificar el payload evaluado ni inferir el eje.

## Evidencia fresca del congelado

```text
python -m pytest -q backend/tests/test_general_furniture_assembly.py tests/test_assembly_evaluation.py backend/tests/test_general_furniture_repository.py backend/tests/test_general_furniture_assembly_live.py
57 passed in 6.87s

python -m pytest -q backend/tests/test_general_furniture_assembly.py backend/tests/test_general_furniture_assembly_live.py backend/tests/test_general_furniture_repository.py backend/tests/test_general_furniture_router.py backend/tests/test_integral_api_integration.py tests/test_assembly_evaluation.py
71 passed in 15.19s

npm test -- --runInBand
192 passed, 0 failed

git diff --check -- <archivos focales de montaje>
sin errores
```

## Caso real congelado

- El artefacto público `plank-030-r4-pre-evaluation.json` contiene revisión 4, candidato presente y 16 colocaciones, sin escena aceptada.
- La concordancia de referencia 16/16 no elimina la incertidumbre física: el evaluador relativo explica que los solapes también existen en la referencia, mientras que el runtime público carece de evidencia de rebajes/uniones y debe rechazarlos conservadoramente.
- No se recomienda gastar otra llamada de proveedor ni relajar reglas para convertir este resultado en éxito.
