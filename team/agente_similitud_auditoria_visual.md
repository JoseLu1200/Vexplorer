# Auditoría visual de muebles complejos

## Alcance y custodia

- Identidad: agente `complex_visual_audit`, solo auditoría y artefactos ignorados; sin cambios de runtime, datos publicados, commits ni despliegues.
- Runtime auditado: `.worktrees/cad-completion`, HEAD observado `53135a15f44c735a0abd6d7f9911a2c49f218acd`; los módulos cargados fueron los de ese worktree (`backend/app/main.py` y `backend/app/general_furniture/autonomous.py`).
- Fuente: PlankAssembly, revisión local documentada `d1d4308f0ee0aac2f9f407b3533ff83ecee22d34`, licencia declarada CC BY-NC-ND 4.0. El corpus oficial tiene entre 3 y 19 tableros físicos por modelo; no contiene casos de 30-50 piezas. Se usaron dos derivados DXF públicos del adaptador `blind20_v2`, con tres proyecciones ortográficas montadas y sin BOM, nombres de piezas, materiales ni programas 3D.
- Entrada del runtime: exclusivamente `plank-030.dxf` y `plank-016.dxf`. La referencia privada se abrió solo después de congelar cada propuesta para evaluación.
- Ejecución: jobs live aislados en `.runtime/complex-visual-audit/data-authoritative`; proponente `gpt-6.1-sol` y crítico `gpt-6-astra`. El primer intento previo en `data/` fue un upload/base run abortado por error del harness y queda excluido.

> **Limitación crítica de alcance:** este harness local ejecutó los jobs con un presupuesto de **300 s**. La configuración publicada observada en `/api/v1/config` declara `autonomous_review.limits.job_timeout_s=600`. Aunque los códigos y modelos sean los mismos, los resultados `0/2` y ambos `provider_request_timeout` pertenecen exclusivamente al ensayo local de 300 s. No demuestran que esos casos agoten el timeout ni fallen con la configuración publicada de 600 s; no se ejecutó esta muestra contra el despliegue publicado.

## Inspección visual de las fuentes

Se renderizaron e inspeccionaron con `view_image` hojas compactas de alto contraste:

- `source-plank-030-compact.png`: mueble alto y estrecho; costados largos, cuatro horizontales interiores, dos estantes, frentes, traseras y travesaños se repiten entre las tres proyecciones. La unión de bounds de la referencia reservada mide 600 x 568 x 2400 mm; 550 mm es el fondo de los costados, no la envolvente global.
- `source-plank-016-compact.png`: mueble ancho y bajo, con hueco/retranqueo central, compartimentos laterales, montante en T y varias tablas horizontales. Es una geometría diferente y más ambigua que `plank-030`. El ancho global de referencia es 1480 mm; la unión completa de bounds mide 1480 x 618 x 650 mm. Los 550 mm pertenecen a la base y los 645/632 mm a componentes concretos, por lo que no se presentan como envolvente general.

No hay cotas escritas, texto, material, acabado, herrajes ni detalle de uniones. Las dimensiones numéricas del resultado proceden de geometría vectorial; la asignación de esos spans a piezas es una hipótesis. Una construcción alternativa compatible con las vistas no es automáticamente un error.

## Caso plank-030 (referencia: 16 tableros)

El proponente congeló 16 tipos: 15 paneles visibles/propuestos y un tipo de kit antivuelco con cantidad 2. Agrupó correctamente las proyecciones: por ejemplo, tres contornos del costado se registraron como una ocurrencia, no como tres piezas.

Correspondencia dimensional con referencia, con diferencias solo de redondeo flotante (<0,001 mm):

- 2 costados: 2400 x 550 x 18 mm.
- 4 horizontales: 564 x 550 x 18 mm.
- 2 estantes: 563 x 515 x 18 mm.
- 2 traseras: 774 x 574 x 5 y 874 x 574 x 5 mm.
- 2 frentes: 597 x 347 x 18 mm.
- 2 travesaños: 600 x 50 x 18 mm.
- 1 de los 2 elementos de 564 x 100 x 18 mm.

Problemas:

- **Alta**: falta una segunda ocurrencia de 564 x 100 x 18 mm. El borrador contiene solo un `plinth`; la referencia contiene dos tableros con esas dimensiones.
- **Media**: agrega dos kits antivuelco no dibujados. Están correctamente rotulados `estimated`, con dimensiones y modelo desconocidos, así que no se presentan como hechos del plano; aun así elevan el total a 17 ocurrencias frente a 16 tableros de referencia y no deben confundirse con lista de corte.
- **Correcto**: material y acabado permanecen desconocidos para todos los paneles. La estimación de zócalo, ranura, tornillería y anclaje conserva rangos, premisas y autoridad `estimated`.

El crítico detectó un error semántico reparable, pero el job del harness local terminó a los 300,10 s con `provider_request_timeout`. No existe revisión aceptada ni artefacto oficial derivado en este ensayo; solo el borrador provisional congelado. Este resultado no prueba el comportamiento con el presupuesto publicado de 600 s.

## Caso plank-016 (referencia: 14 tableros)

El proponente congeló 9 paneles y el reparador semántico produjo una revisión 2, también de 9 paneles. Las nueve envolventes coinciden con la referencia dentro del redondeo (<0,001 mm):

- 1480 x 550 x 18; 1443 x 510 x 18; 934 x 587 x 5 mm.
- 2 x 632 x 230 x 18; 2 x 632 x 320 x 18 mm.
- 645 x 100 x 18 y 645 x 50 x 18 mm.

Problemas:

- **Alta**: omite 5 de 14 tableros de referencia: 470 x 572 x 18, 200 x 632 x 18, 1444 x 60 x 18, 320 x 632 x 18 y 924 x 70 x 18 mm. En la hoja fuente hay líneas correspondientes a elementos internos/longitudinales, pero las tres proyecciones solapadas hacen su identidad ambigua; la omisión es clara frente a la referencia, aunque no todas las funciones semánticas sean únicas desde el dibujo.
- **Correcto**: no duplica las proyecciones como piezas, conserva cantidades como `hypothesis` y deja material/acabado desconocidos.

Limitación de la visualización de auditoría: el entrepaño se describe con dos escotaduras propuestas, pero la hoja comparativa dibujada para este diagnóstico representa solo su envolvente rectangular. No es un defecto visual observado en un artefacto oficial: el crítico no cerró la revisión y el producto no generó plano de pieza. Por tanto, la forma interior no queda verificada visualmente en esta prueba.

El job del harness local hizo propuesta, crítica, reparación semántica y segunda crítica, pero terminó a los 300,12 s con `provider_request_timeout`. Tampoco hay resultado aceptado ni planos oficiales en este ensayo. No se evaluó el mismo caso con el presupuesto publicado de 600 s.

## Diagnóstico global

- **Crítica en el ensayo local de 300 s (no atribuible al despliegue publicado)**: 0/2 casos complejos completaron el flujo autónomo dentro del presupuesto local. Los borradores son inspeccionables y trazables, pero este harness no obtuvo revisión final ni SVG/DXF oficiales. La configuración publicada dispone de 600 s; sin repetir estos casos allí, no puede concluirse que el flujo publicado falle o agote su timeout.
- **Recuperación parcial de UX**: tras reiniciar la aplicación contra el almacenamiento aislado, `GET /api/v1/runs/{run_id}/general` devolvió 200 para ambos fallos (revisiones de propuesta 1 y 2; 16 y 9 componentes). No existe revisión autónoma (`review_revision=0`), por lo que el endpoint de derivados rechaza correctamente la solicitud y no fabrica planos oficiales a partir de un borrador sin aceptar.
- **Correcto (navegador integrado)**: en el target local integrado de la misma generación, la restauración de `run-b8aa342758664bf6b847c1ea2de1c057` mediante `?run=...` no produjo errores de consola, recuperó la propuesta 2 con nueve piezas y mantuvo deshabilitadas las pestañas **Construcción**, **Por pieza** y **Despiece**. Esto confirma una recuperación segura del borrador sin habilitar derivados no revisados. Es una observación del target local integrado en `127.0.0.1:8777`, no una captura del despliegue publicado.
- **Media (presentación de cotas)**: la tabla restaurada muestra floats crudos como `1443.000000835382 mm`, `17.99993303007176 mm` y `631.9999986823065 mm`. Los datos son coherentes con la geometría, pero la precisión aparente es injustificada y dificulta la lectura. La interfaz debería presentar redondeo y/o tolerancia apropiados sin destruir el valor raw trazable.
- **Media (estado UX incompleto)**: tras restaurar el job fallido, la interfaz muestra «Geometría extraída. Revisa las hipótesis antes de exportar» y «Revisión necesaria», pero no explica que el motivo de no disponer de resultado final fue `provider_request_timeout`. El borrador es recuperable, aunque falta una indicación accionable del fallo de revisión y de la posible reanudación.
- **Alta (cobertura)**: en esta muestra, el caso ancho y visualmente más ambiguo recupera 9/14 tableros; el armario alto recupera 15/16 paneles y agrega herrajes hipotéticos. Dos casos no permiten atribuir causalidad ni generalizar el rendimiento a todos los muebles densos o retranqueados.
- **Positiva (medidas)**: para las piezas recuperadas, las dimensiones corresponden a la referencia dentro de tolerancia de redondeo. No se observaron intercambios largo/ancho que alterasen la envolvente física.
- **Positiva (autoridad)**: no inventa material o acabado; separa observado/deducido/estimado y explicita premisas. El kit antivuelco es inferencia no fundada en el dibujo, pero está debidamente marcado y sin medidas inventadas.
- **Límite del test**: PlankAssembly es sintético y sus vistas no incluyen cotas, mecanizados ni uniones reales. Estos dos casos no validan fabricabilidad, materiales, herrajes ni muebles de 30-50 piezas; prueban asociación de proyecciones, dimensiones de envolvente y robustez del pipeline hasta 16 piezas de referencia.

## Prioridades sugeridas

1. Incorporar una comprobación de cobertura que enumere cada contorno o proyección relevante todavía sin asignar a un componente, sin convertir automáticamente cada contorno en una pieza. La revisión debe poder explicar si es otra vista, una arista interna, una pieza omitida o evidencia ambigua.
2. Separar en la salida y los conteos la BOM de paneles/lista de corte de los herrajes o elementos auxiliares estimados. Así, dos kits antivuelco no alteran silenciosamente la comparación de 16 tableros físicos.
3. Presupuestar por fase el tiempo del proponente, crítico y reparador, y persistir checkpoints reanudables. Si la revisión agota su presupuesto, debe poder retomarse desde la propuesta o reparación ya guardada sin repetir llamadas ni perder el borrador accesible.
4. Mostrar en la tabla una precisión legible coherente con unidad y tolerancia, conservando por separado el float raw para trazabilidad y cálculo.
5. Al restaurar un job fallido, mostrar el motivo terminal (`provider_request_timeout`), la fase alcanzada y una acción segura para reanudar o revisar manualmente el borrador.
6. Mantener la distinción observada/deducida/estimada y exigir revisión antes de producir derivados oficiales. Ampliar después la evaluación con planos reales que incluyan cotas, mecanizados, uniones y referencias técnicas; los resultados actuales no validan fabricabilidad.

## Evidencia reproducible

- Fuentes: `.runtime/complex-visual-audit/source-plank-030-compact.png` y `source-plank-016-compact.png`.
- Comparativas inspeccionadas: `comparison-plank-030.png` y `comparison-plank-016.png`. Los rectángulos de la derecha son envolventes dibujadas por esta auditoría a partir del borrador, no planos oficiales del producto.
- Borradores: `partial-run-79f4dce08b034eea9d54753d61facceb.json` y `partial-run-b8aa342758664bf6b847c1ea2de1c057.json` (este último en revisión 2).
- Estados finales: `plank-030/job-latest.json`, `plank-016/job-latest.json` y `runtime-provenance.json`.
- Recuperación post-fallo: `failed-run-recovery.json`.
- Navegador local integrado restaurado: `.runtime/complex-visual-audit/ui-restored-plank-016.png` (inspeccionado en la sesión de auditoría; no acredita el despliegue publicado).

