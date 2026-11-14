# Verificación del recorrido PDF raster

## Causa observada

La reproducción instrumentada histórica no acredita que el presupuesto de salida fuese la causa raíz. Sí acredita esta secuencia:

1. El proveedor devolvió una propuesta estructurada con dimensiones desconocidas.
2. La propuesta inventó `source_view_ids=["pdf-page-0001"]` aunque el ledger raster no contenía vistas y citó una referencia de documento anunciada que el materializador no admitía. El servidor la rechazó como `proposal_reference_outside_ledger`.
3. La inspección posterior del ledger vacío fue válida.
4. La tercera respuesta terminó con estado `incomplete`, pero el adaptador histórico descartó `incomplete_details`; su submotivo no puede recuperarse de ese artefacto.

Por tanto, el defecto reproducible del producto era la contradicción entre el contexto anunciado y las referencias que realmente aceptaba el materializador. El estado incompleto posterior fue un fallo adicional no diagnosticable con la telemetría antigua. La documentación oficial explica que un modelo de razonamiento puede devolver `incomplete_details.reason=max_output_tokens`, incluso sin salida visible; eso era una hipótesis, no un hecho observado en la traza histórica.

## Corrección

- En raster sin ledger métrico, el contexto y el esquema de herramienta anuncian explícitamente `source_view_ids=[]`, `bindings=[]`, ejes nulos y una lista cerrada de referencias documentales.
- El materializador acepta las mismas referencias de página y documento que se anuncian al modelo.
- El raster sigue siendo contexto visual: no autoriza medidas desde píxeles ni crea cotas métricas.
- La frontera del proveedor conserva solo metadatos operativos acotados: código, HTTP status, request/response ID y `incomplete_reason`. Nunca propaga cuerpo remoto, prompt, clave ni razonamiento.
- No se aumentó `max_output_tokens` ni se forzó globalmente un nivel de razonamiento para ocultar el defecto.

## Pruebas sin red

```powershell
.\.venv\Scripts\python.exe -m pytest -q backend/tests/test_agent_runtime.py backend/tests/test_backend_agent.py backend/tests/test_general_furniture_live.py
.\.venv\Scripts\python.exe -m pytest -q backend/tests/test_integral_api_integration.py::test_production_job_integrates_general_review_derived_and_history_persistently
```

La prueba de integración recorre upload PDF raster → selección de página → job durable → propuesta/revisión → resultado general. Comprueba que no aparece DXF normalizado, que se usan artefactos visuales y que el recorrido termina.

## Aceptación HTTP real acotada

Arrancar una instancia local desechable con la clave cargada desde `.env` sin imprimirla. El proceso debe apuntar a un directorio de datos aislado y utilizar los modelos configurados por el servidor. Después ejecutar una única aceptación pagada:

```powershell
.\.venv\Scripts\python.exe -m tools.audit_pdf_raster_live `
  --base-url http://127.0.0.1:8772 `
  --source ..\engineering_evaluation_pilot\agent_inputs\visual-001.pdf `
  --output .runtime\pdf-raster-acceptance\report.json `
  --invoke-paid-provider
```

El comando falla antes de enviar el job si el derivado raster declara análisis geométrico, procedencia de escala o DXF normalizado. Tras el job también falla si no hay componentes, si alguna propuesta inventa una vista de ledger, si aparece cualquier dimensión numérica o si un eje nulo no tiene estado exactamente `unknown`. El informe persiste hashes, IDs, estados, revisiones y estados dimensionales, sin payloads del proveedor.

## Evidencia previa y límites

Aceptación actual sobre el árbol compartido congelado:

- Fuente: `visual-001.pdf`, 57.735 bytes, SHA-256 `7738983984818c30582ed989160386a3e51a1bef8ac522edae2043c69bf023a2`.
- Servidor aislado local en el puerto 8793, detenido después del ensayo.
- Job `succeeded`; run `run-7267675e450042d7af5ad956fdc0593b`.
- Estado general `reviewed_incomplete`, propuesta 1/revisión 1.
- Seis componentes visuales; los 18 valores largo/ancho/espesor son `null` con estado `unknown`; ningún componente contiene `source_view_ids` inventado.
- El manifiesto persistido del documento hijo confirma `geometry_analysis=false`, `scale_provenance=null` y `artifacts.normalized_dxf=null`; por tanto, no hubo autoridad métrica normalizada.
- Derivados: paquete `incomplete`, escena `schematic_incomplete`, base de coste `partial`.
- Informe: `.runtime/pdf-raster-acceptance/report.json`, SHA-256 `164cf7b5aa1e0080b9b60117c58493404533b845e238f0f7f1594ee369d1051c`.
- Manifiesto del código exactamente cargado: `.runtime/pdf-raster-acceptance/code-manifest.json`. Conserva hashes de proveedor, live, main, contratos, materializador, autonomía y auditor; el `live.py` del ensayo tiene SHA-256 `2c15229a49c547ed64d4504c784a422dcdba21349592da04354027306a6a4e2e`. El refinamiento público posterior de vocabulario de roles/montaje no se atribuye retroactivamente a este run.

Una ejecución anterior del mismo arreglo en el worktree aislado `conditional-hours` terminó con job `succeeded`, propuesta P2/revisión R1 y derivados HTTP 200. Sus cinco componentes conservaron largo, ancho y espesor desconocidos; el artefacto local quedó en `.worktrees/conditional-hours/.runtime/raster-fix-http-20261114/qa-report.json` con SHA-256 `57059ac561723268cb97c94806e1e2f30ffc3d15f8d98e21bd6aae8f10578216`.

Esa aceptación demuestra el recorrido técnico para una página y un proveedor, no exactitud semántica, escalabilidad, validez industrial ni aptitud para fabricación. Las cantidades siguen siendo hipótesis visuales y material, acabado, uniones, mecanizados y dimensiones permanecen pendientes de evidencia o revisión humana.
