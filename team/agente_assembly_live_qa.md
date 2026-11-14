# Agente assembly live QA — freeze y verificación HTTP

## Identidad y autorización

- Nombre declarado por delegación: agente de IA `assembly_live_qa`; no representa a una persona.
- Rol: herramienta y ejecución de aceptación en producción local, sin leer referencias privadas antes del freeze.
- Autorización: delegación de `/root` bajo la aprobación integral del usuario, 2026-11-14.

## Alcance propio

- Nuevos `tools/verify_general_assembly.py`, `tests/test_verify_general_assembly.py`,
  artefactos bajo `.runtime/assembly-verification/` y este registro.
- Solo lectura sobre contratos, runtime, frontend, DXF públicos y revisiones persistidas.
- El reinicio del servicio y el navegador pertenecen a otros agentes; no se duplican.

## Garantías implementadas

- Dispara un único `POST .../general/assembly/retry` ligado a la revisión exacta.
- Espera el job durable, recupera el intento persistido y vuelve a consultar `derived`
  para la misma propuesta/revisión.
- Congela JSON canónico `*-pre-evaluation.json` y sidecar SHA-256 antes de cualquier
  evaluación privada, sin permitir sobrescritura.
- Conserva intentos rechazados y su traza pública. Rechaza una escena que sirva
  posiciones numéricas cuando el intento no fue validado.
- No carga credenciales de proveedor, prompts ni referencias privadas. Basic Auth,
  si se usa, procede solo del entorno o entrada interactiva y no se persiste.

## Casos preparados

| Caso | Entrada pública | Uso previo relevante | Resultado esperado |
|---|---|---|---|
| Complejo principal | `../plankassembly_adapter_blind20_v2/plank-030.dxf`, run persistido `run-9eb5e3aca8a04331ac0b0d3e5e2f2f40` | Extracción/BOM ya demostrada; no montaje espacial | Validado o fallo geométrico explícito; nunca se fuerza éxito |
| Segundo no usado para ajustar montaje | `../plankassembly_adapter_blind20_v2/plank-016.dxf` | Inspección visual anterior; su job general anterior terminó por timeout y no produjo revisión utilizable | Nueva ejecución autónoma y después freeze de montaje |
| Control insuficiente | `data/planos_demo/mueble_demo_unidades_desconocidas.dxf` | Fixture negativo público con unidad/medidas métricas desconocidas | Abstención; ninguna posición montada servida |

`plank-016` se elige por geometría distinta de `plank-030` y porque no fue usado
para ajustar esta implementación de montaje. La inspección visual histórica se
declara para no presentarlo como holdout ciego. El control insuficiente tiene SHA-256
`511adc7948119238825d9ff3aeb8c05c52f73c5fb6e2257aa3fcaac83b5b936d`.

## Evidencia TDD y estado

| Fase | Comando | Resultado |
|---|---|---|
| RED | `.venv\\Scripts\\python.exe -m pytest tests\\test_verify_general_assembly.py -q` | Error de colección esperado: módulo aún inexistente |
| GREEN | mismo comando | 4 passed |
| Lint | `python -m ruff check tools\\verify_general_assembly.py tests\\test_verify_general_assembly.py` | All checks passed |
| Diff | `git diff --check -- tools\\verify_general_assembly.py tests\\test_verify_general_assembly.py` | Sin salida |
| Cierre fresco | `.venv\\Scripts\\python.exe -m pytest tests\\test_verify_general_assembly.py -q` | 4 passed |
| Hashes live | Recalcular SHA-256 de cada `*-pre-evaluation.json` frente a sidecar | 8/8 coinciden |

## Invocación preparada tras el reinicio coordinado

```powershell
.venv\Scripts\python.exe tools\verify_general_assembly.py `
  --base-url https://localhost:8765 `
  --run-id run-9eb5e3aca8a04331ac0b0d3e5e2f2f40 `
  --case-id plank-030 `
  --expected-outcome any `
  --output-dir .runtime\assembly-verification
```

Se usa `any` en la primera ejecución para preservar honestamente tanto éxito como
rechazo; la aceptación geométrica se juzga después sobre el artefacto congelado.

## Pendientes

- Esperar aterrizaje final de runtime/core y reinicio único de `/root`.
- Ejecutar los tres casos, sin doble gasto, y comunicar hashes antes de evaluación.
- Conservar fallos y relatar bugs concretos al propietario correspondiente.

## Historial live congelado

Todos los artefactos siguientes se escribieron antes de cualquier lectura de
referencia privada. Los sidecars SHA-256 están en el mismo directorio.

| Caso | Assembly rev | Estado runtime | SHA-256 | Diagnóstico público |
|---|---:|---|---|---|
| `plank-030` | 1 | incomplete, 0 placements | `08114217c4fabb37c928f0babc06f1681c168828149cd30a48d4a75fda2577ac` | HTTP 400 `invalid_function_parameters`; esquema de tool sin strictify |
| `plank-030-r2` | 2 | incomplete, 0 placements | `1fd95f46c0355eb372b1a24b9d1874b031a4588bcb3507f0f3069b9778e57165` | agotó llamadas; argumentos JSON se validaban como objetos Python strict |
| `plank-030-r3` | 3 | incomplete, 0 placements | `187dd7f001b03742c8ef29e853d9ec2b5083d393219e57091296da07128c9f65` | preflight `assembly_reviewed_dimensions_required`, 0 llamadas |
| `plank-030-r4` | 4 | rejected, 16 placements candidatos | `3e7c393091b3afcf65d7285ab100eb33a19c192dcffec3357df1e8ef16f52c75` | llegó a geometría; box residual, identidades compartidas y penetraciones; 5 llamadas/5 tools |
| `plank-016-r2` | 2 | incomplete, 0 placements | `725fc703cf6ee60439a596d35c2cb13e69cfcf1ce100e63ca2a4031f766af459` | `assembly_confirmed_quantity_required`, 0 llamadas; no se inventó cantidad |
| `unknown-units-control-r2` | 2 | incomplete, 0 placements | `369d800aef16d2787241d2f520132a3339455eb646ab5751852db89874de9be0` | `assembly_metric_scale_required`, 0 llamadas; escena sin posiciones |
| `unknown-units-control-r3` | 3 | incomplete, 0 placements | `0466f44d88266dfd385bfaf2ac0cb7d46aba827e89a66b9ecff896d792deddae` | causa precisa persistida en issue/traza: `assembly_metric_scale_required` |
| `plank-016-r3` | 3 | incomplete, 0 placements | `2fd1646a06490096b0019d389ac7971483908cc0a77ac8735fc5698e673e1dcf` | causa precisa persistida: `assembly_confirmed_quantity_required` |

El informe independiente de rev4 está en
`.runtime/assembly-verification/plank-030-r4-assembly-report.json`; no reemplaza
el estado runtime rejected. La referencia permaneció fuera del proceso de
inferencia y solo el evaluador independiente la abrió después del freeze.

La revalidación determinista posterior, solo con candidato congelado y evidencia
pública, está en
`.runtime/assembly-verification/plank-030-r4-core-revalidation.json`
(SHA-256
`b4cc6fa7b54360203d2b8aa63214f41e909a5f26f7d8a965bdaa83d499731c48`).
No muta rev4: conserva 16 placements pero sigue `rejected` con ocho
`aabb_penetration`, una `shared_contour_identity` y penetración máxima
4.999943339249739 mm. Se corrigieron únicamente falsos positivos numéricos y
spam de identidad; no se usó una hipótesis de mecanizado para dispensar
colisiones mayores de 1 mm.

`plank-016` abstuvo correctamente: su revisión pública contiene once
cantidades hipotéticas pero solo nueve ocurrencias provisionales. La continuidad
de una balda y la identidad de un travesaño solapado permanecen sin resolver, por
lo que no se inventaron dos instancias.

Hallazgos de integración comunicados a sus propietarios:

- La revisión pública del caso principal usa dimensiones/cantidades hipotéticas
  pero respaldadas y ocurrencias provisionales; el preflight se corrigió para
  aceptar solo hipótesis con procedencia exacta y seguir rechazando libres/desconocidas.
- El runtime perdía detalles seguros posteriores al primer candidato rechazado
  porque no persistía un intento terminal adicional al agotar presupuesto.
- Los `ValueError assembly_*` de preflight se registraban con código preciso en
  eventos pero se degradaban a `assembly_runtime_failed` en el intento/UI.
- `plank-016` tuvo un intento general anterior con timeout y una inspección visual
  declarada; no se presenta como holdout ciego ni se usó para ajustar el montaje.
