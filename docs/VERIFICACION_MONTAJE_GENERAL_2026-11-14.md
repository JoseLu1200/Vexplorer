# Verificación del montaje general — 2026-11-14

## Resultado honesto

La revisión congelada `plank-030-r4` contiene 16 colocaciones y coincide con la referencia geométrica bajo **una sola** rotación ortogonal propia, **una sola** traslación y una biyección sin reutilizar ocurrencias. Satisface el criterio relativo a referencia, pero el runtime la conserva correctamente como `rejected`: ocho pares de cajas penetran casi 5 mm y la evidencia pública no demuestra mecanizados o uniones que permitan certificarlos como libres de colisión.

Por tanto, `passes_reference_relative_acceptance=true` no equivale a aprobación de fabricación ni a `collision_free_at_tolerance`; este último es `false`.

## Artefactos congelados e historial

| Revisión pública | SHA-256 exacto | Estado runtime | Colocaciones | Resultado |
|---|---|---:|---:|---|
| `.runtime/assembly-verification/plank-030-pre-evaluation.json` | `08114217c4fabb37c928f0babc06f1681c168828149cd30a48d4a75fda2577ac` | `incomplete` | 0 | fallo conservado |
| `.runtime/assembly-verification/plank-030-r2-pre-evaluation.json` | `1fd95f46c0355eb372b1a24b9d1874b031a4588bcb3507f0f3069b9778e57165` | `incomplete` | 0 | fallo conservado |
| `.runtime/assembly-verification/plank-030-r3-pre-evaluation.json` | `187dd7f001b03742c8ef29e853d9ec2b5083d393219e57091296da07128c9f65` | `incomplete` | 0 | fallo conservado |
| `.runtime/assembly-verification/plank-030-r4-pre-evaluation.json` | `3e7c393091b3afcf65d7285ab100eb33a19c192dcffec3357df1e8ef16f52c75` | `rejected` | 16 | evaluado sin alterar el wrapper |

Cada `.json` tiene un sidecar `.sha256`. El evaluador consume directamente `assembly_attempt.report.placements`; no reconstruye ni reserializa la predicción antes de hashearla. La referencia sellada local es solo para el evaluador y no contiene datos publicables ni accesibles al runtime.

## Métricas independientes de `plank-030-r4`

Informe reproducible: `.runtime/assembly-verification/plank-030-r4-assembly-report.json`.

| Métrica | Resultado |
|---|---:|
| Referencia / predicción / emparejadas | 16 / 16 / 16 |
| Faltantes / extras | 0 / 0 |
| Cobertura / precisión | 1,0 / 1,0 |
| Ocurrencias dentro de 1 mm | 16 |
| Error máximo de centro | `1.14e-12 mm` |
| Error máximo de caras | `4.18e-7 mm` |
| Error dimensional máximo | `8.35e-7 mm` |
| Error máximo de centro normalizado por diagonal | `4.48e-16` |
| Error máximo de cara normalizado por diagonal | `1.65e-10` |
| Normales / ejes | todos concordantes; `0°` máximo |
| Alineación | una rotación global, determinante `+1`, y una traslación global |
| Emparejamiento | biyectivo; 0 referencias reutilizadas |
| Reproyección máxima frontal/superior/lateral | `4.18e-7 / 4.18e-7 / 1.14e-12 mm` |
| Penetración absoluta candidata | `4.999943 mm`; 8 pares mayores de 1 mm |
| Penetración absoluta de referencia | `4.999943 mm`; 8 pares mayores de 1 mm |
| Exceso candidato sobre referencia | `4.18e-7 mm`; 0 pares mayores de 1 mm |

La igualdad casi exacta de las penetraciones candidata y de referencia explica el `passes_reference_relative_acceptance=true`. No explica físicamente la unión desde la entrada pública; por eso se mantiene `collision_free_at_tolerance=false` y el rechazo conservador del runtime.

La revalidación pública suplementaria `.runtime/assembly-verification/plank-030-r4-core-revalidation.json` (`b4cc6fa7b54360203d2b8aa63214f41e909a5f26f7d8a965bdaa83d499731c48`) conserva las 16 posiciones y exactamente 9 incidencias: 8 `aabb_penetration` y una `shared_contour_identity`. No quedan incidencias por residuo de contorno ni entidad compartida espuria; ninguna incidencia restante es ruido de coma flotante. El artefacto congelado original permanece intacto.

## Segundo caso y control de abstención

| Caso congelado | SHA-256 | Estado / salida | Métrica |
|---|---|---|---|
| `plank-016-r2-pre-evaluation.json` | `725fc703cf6ee60439a596d35c2cb13e69cfcf1ce100e63ca2a4031f766af459` | `incomplete`, `abstained`, 0 colocaciones | intento previo conservado |
| `plank-016-r3-pre-evaluation.json` | `2fd1646a06490096b0019d389ac7971483908cc0a77ac8735fc5698e673e1dcf` | `incomplete`, `abstained`, 0 colocaciones | 0/14 emparejadas; abstención final reproducible |
| `unknown-units-control-r2-pre-evaluation.json` | `369d800aef16d2787241d2f520132a3339455eb646ab5751852db89874de9be0` | `incomplete`, `abstained`, 0 colocaciones | intento previo conservado |
| `unknown-units-control-r3-pre-evaluation.json` | `0466f44d88266dfd385bfaf2ac0cb7d46aba827e89a66b9ecff896d792deddae` | `incomplete`, `abstained`, 0 colocaciones | `assembly_metric_scale_required`; 0 llamadas al modelo |

El informe evaluator-only del segundo caso está en `.runtime/assembly-verification/plank-016-r2-assembly-report.json`. La revisión pública final declara `public_inputs_only=true`, 11 tipos y 9 ocurrencias de escenario acotadas por evidencia. Solo `shelf` y `rail_a` carecen de ID de escenario: la continuidad o segmentación de la balda y la identidad solapada o miembro adicional del rail permanecen indeterminadas. El candidato queda nulo con `assembly_confirmed_quantity_required`; la cobertura global no autoriza a fabricar esas ocurrencias para satisfacer una métrica.

El control sin unidades se juzga por abstención pública, no por comparación geométrica inventada. La revisión final termina con `assembly_metric_scale_required`, 0 colocaciones y **0 llamadas al modelo**.

## Reproducción

Después de verificar el sidecar y sellar una referencia con el SHA-256 exacto de la predicción congelada:

```powershell
.\.venv\Scripts\python.exe -m tools.evaluate_assembly `
  --predictions .runtime/assembly-verification/plank-030-r4-pre-evaluation.json `
  --references .runtime/assembly-verification/plank-030-r4-sealed-reference.json `
  --output .runtime/assembly-verification/plank-030-r4-assembly-report.json
```

El CLI abre y hashea primero la predicción; solo después abre la referencia evaluator-only y exige que `prediction_sha256` coincida. Usa las 24 rotaciones ortogonales propias, optimiza una traslación global y resuelve una asignación húngara determinista sin SciPy.

## Verificación de software

- Evaluador y core de montaje: 57 pruebas pasan; una advertencia deprecada externa de `TestClient`.
- Ruff de evaluador, CLI y regresiones: limpio.
- Suite completa final de backend/repositorio: 793 pruebas pasan en 138,82 s; 2 advertencias deprecadas ya existentes.
- Diagnóstico focal del runtime tras el parche: 45 pruebas pasan. Servicio reiniciado con PID 13172.
- Frontend: 192/192 pruebas pasan. El selector diagnóstico de eje vertical `Z` aplica en visualización `(x,y,z) -> (x,z,-y)`, una transformación global propia de determinante `+1` que no altera el payload evaluado. Para inspeccionar `plank-030` erguido se usa «Eje vertical de inspección Z».
- Navegador final: pasa. Evidencia erguida en `.runtime/assembly-verification/browser-complex-rejected-16-world.png`; muestra 16 instancias diagnósticas y selección individual de `shelves:1` agrupada con «Baldas». Zoom, órbita, explotar/restaurar exactamente, salida a esquema y recarga funcionan sin errores JavaScript, de red ni HTTP.

Al salir del diagnóstico, la etiqueta del selector puede conservar visualmente `Z` hasta la recarga aunque la escena ya se haya restablecido; recargar devuelve también el selector a `Y`. Es una discrepancia visual menor sin impacto geométrico ni sobre el payload congelado.

No se ejecutaron llamadas adicionales al modelo para esta evaluación. Ninguna coordenada ni dimensión privada se trasladó al runtime o a sus implementadores.
