# TDD: comportamiento verificable antes de implementar

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

**Estado: estrategia futura, sin aplicación ni pruebas de producto ejecutadas.** La auditoría de `engineering-drawings-harness.zip` se documenta en [DATASET.md](DATASET.md). Sus 14 piezas CAD aisladas y 51 conjuntos PDF representan tareas distintas. P0 combina extracción real de DXF admitidos y fixtures propios para despiece de paneles; Bench Vise es piloto PDF P1, pendiente de acuerdo A/B. Cadblock quedó descartado como referencia de despiece.

[CONTRATOS_DATOS.md](CONTRATOS_DATOS.md) describe la propuesta `0.1.0`, no un contrato implementado. Los futuros modelos Pydantic en `backend/app/contratos/modelos.py` serán la única autoridad; los esquemas de herramientas se generarán desde ellos. A/B deben acordar cambios y avisar a C antes de congelarlos. Las pruebas no mantendrán otro esquema manual.

## Qué merece un ciclo

TDD protegerá errores observables: perder procedencia, atribuir mm a coordenadas sin unidad, contar vistas como ocurrencias, inventar espesor o publicar un borrador inválido. No se escribirán tests ceremoniales de títulos, getters triviales o constantes copiadas. La suite futura vivirá en `backend/tests/{unit,integration,contract,fixtures,e2e}/` y `frontend/tests/`; estas rutas no contienen aquí un producto ejecutable.

Una prueba contractual verifica estructura y referencias. Una geométrica compara medidas con un oráculo independiente. Una semántica contrasta identidad y cantidad con anotación humana. Ninguna sustituye las otras: un JSON válido puede describir una interpretación errónea.

## Primer ciclo: pulgadas con procedencia

1. **Rojo.** Materializar un DXF propio con unidades pulgadas y un segmento `(0,0)`–`(1,0)`. Pasarlo por el lector real. Esperar longitud `25.4` mm, coordenada fuente `1` y referencia a la entidad. Observar un fallo por conversión o procedencia, no por dependencias rotas.
2. **Verde.** Añadir la transformación mínima en `backend/app/geometria/`, conservando coordenadas originales, unidad y transformación.
3. **Refactorizar.** Separar resolución de unidades y transformación si simplifica el diseño. Ejecutar el caso y sus vecinos antes de ampliar a bloques o cotas.

El esperado `25.4` se escribe en el fixture; no se obtiene llamando a la función bajo prueba. Para comparaciones compatibles se proponen `abs_tol_mm=0.1` y `rel_tol=1e-6`, valores de cálculo configurables que no equivalen a tolerancias de fabricación.

El segundo ciclo elimina la unidad: esperar `needs_review`, medidas métricas sin resolver y preview con coordenadas `source`. No multiplicar por uno y etiquetar mm. Confirmar unidades cambia configuración y fingerprint, por lo que requiere otra ejecución, no una edición del ledger existente.

## Identidad, abstención y entrega

**Tres vistas, una ocurrencia.** Crear frontal `600 × 400`, lateral `18 × 400` y superior `600 × 18`, con asociación respaldada a una balda. Esperar tres observaciones, un candidato físico confirmado y cantidad `1`. La variante sin asociación suficiente mantiene ambigüedad. En P0, las alternativas solo compiten como interpretaciones de una misma ocurrencia; «una pieza frente a varias» requiere revisión y regenerar el ledger, no seleccionar hermanos aditivos dentro del mismo grupo excluyente.

**Espesor desconocido.** Una vista `600 × 400` no justifica `18`. Esperar `thickness=null`, revisión y ausencia de caja 3D completa. Una cota general de un objeto tampoco es espesor de componente: `entity_level=object|unknown` se conserva mediante disposiciones, sin fabricar piezas.

**Abstención revisable.** Construir un ledger íntegro con dos candidatas y evidencia insuficiente. Provocar falta de evidencia o agotamiento del presupuesto. El servidor debe construir `pieces=[]` y dos disposiciones `needs_review`, ejecutar el mismo validador y resolvedor y persistir Result revisión `1`, informe y evento terminal juntos. El borrador inválido del modelo queda como diagnóstico separado. La prueba falla si solo cambia el estado sin guardar un resultado consultable.

Añadir un caso sin candidatas: listas vacías, comprobación propuesta `R-018` con `unknown/review`, causa `no_supported_part_candidates` y estado `needs_review`. Después introducir una referencia rota en el ledger: esperar `failed` con `invalid_evidence_ledger`; la abstención no inventa evidencia para repararlo. Cancelación y timeout conservan sus estados y prioridad transaccional.

**Entrega idempotente.** `validar_borrador` y `entregar_despiece` comparten servicio determinista. Un ID inexistente produce rechazo sin aceptar ese borrador. Una entrega válida se persiste una vez; repetirla devuelve la misma revisión y una propuesta distinta posterior recibe `already_finalized`. Una abstención válida también debe producir una sola revisión, no una por reintento.

## Corpus real y dobles de prueba

Los fixtures propios atraviesan el parser DXF real, incluyendo handles, unidades, bloques y cotas. El corpus Orla añade 14 componentes con formatos relacionados; no representa 14 conjuntos despiezados. Los 419 registros del sidecar contienen 370 cotas y 49 estilos; 14 cotas son angulares, 50 tienen sobrescritura textual y cuatro `ARC_DIMENSION` reales quedan fuera de ese JSON. La futura extracción no debe perderlas silenciosamente ni tratar grados como mm. Once DXF no declaran unidad; solo tres declaran mm.

Las referencias del publicador no son un oráculo semántico independiente. Revisar nominales y marcos antes de afirmar exactitud; conservar por separado valor bruto, medida calculada, texto y factor. Mantener juntos assembly, componente, formatos, vistas y variantes al particionar. Las muestras ya inspeccionadas son desarrollo/demo. Ocultar títulos externos en la pista ciega, conservar las cotas legítimas del plano y no proporcionar al agente el JSON que se usa como respuesta esperada.

El proveedor falso se coloca únicamente en la frontera de red de `backend/app/agente/`. Devuelve llamadas nativas, errores y respuestas inválidas; no sustituye geometría, mediciones, `inspeccionar_candidata`, `obtener_evidencias` ni el validador. Así se reproduce un ID inventado sin ocultar el rechazo real. Las integraciones reales de proveedor quedan separadas, con modelo configurado, sin exigir redacción exacta de prosa. ODA ausente se simula como frontera externa y debe producir `conversion_unavailable`.

## Interfaz, revisión y extensiones

Probar hover consultando `GET ledger`, `GET drawing` y el artefacto autorizado descritos en [API_Y_EVENTOS.md](API_Y_EVENTOS.md). IDs y revisiones deben enlazar entidad, evidencia y selección incluso cuando `pieces=[]`. Una preview sin unidades conserva coordenadas fuente y aviso, sin campos `points_mm` inventados.

La revisión crea Result revisión `2` y conserva revisión `1`. `Run.state` terminal no cambia; la interfaz muestra `result.state` vigente. Nuevas unidades o asociaciones congeladas exigen otra ejecución. Este comportamiento merece regresión por su efecto en auditoría y presentación.

Las cadenas dimensionales generales `R-015` son P1 hasta estructurar eje, marco, términos, juntas y evidencia mediante acuerdo A/B y aviso a C. P0 siempre informa `not_applicable`. El ejemplo futuro `18+564+18=600` verifica diferencia `0`; con vano `560`, suma `596` y diferencia `4`. No se suman largos arbitrarios. La colisión genérica P0 también es `not_applicable`: solapes 2D y cajas esquemáticas no prueban colisión física.

Cada ciclo futuro conservará caso, comando, fallo por la razón correcta, cambio mínimo y salida posterior. La inspección de este paquete no proporciona esas ejecuciones. Los casos y prioridades de [TEST_PLAN.md](TEST_PLAN.md) permanecen pendientes hasta existir implementación y evidencia reproducible.

## Pruebas pendientes del adaptador de PlankAssembly

Usar fixtures propios mínimos para verificar exclusión de envolvente, mapeo de asociaciones, normales ausentes, escala de proyección y prevención de fugas. Los valores esperados deben estar calculados independientemente del generador. Después contrastar una muestra real admitida y documentar las diferencias. La [auditoría de descarga](PLANKASSEMBLY.md) ya existe; estas pruebas del adaptador y del agente aún no.

El tooling de preparación mecánica tiene 13 pruebas documentadas en [PILOTO_DATASET](PILOTO_DATASET.md). No atribuirlas a un lector de PlankAssembly, a reconstrucción ni a presupuestación.
