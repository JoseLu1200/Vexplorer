# Aceptación local de producción

Fecha: 14 de noviembre de 2026. Responsable: IA D, evaluación independiente. El ensayo usa fixtures propios y `geometry_only`; no llama a proveedores de pago ni instala el producto en un servidor.

## Criterio operativo

`tools/audit_production.py` ejecuta el caso declarado en `evaluation/production_acceptance_cases.json` sobre una base SQLite nueva. El recorrido exige autenticación individual, trabajo durable, revisión atribuida al usuario autenticado, planos derivados, coste con catálogo configurado, exportación y lectura tras reiniciar la aplicación. Dos controles negativos cubren una petición sin autoridad y un plano con conflicto dimensional.

El oráculo económico de `tests/test_production_acceptance.py` no importa funciones de cálculo del producto. Multiplica cada cantidad publicada por una tarifa literal con `Decimal`, aplica redondeo HALF_UP por concepto, suma el subtotal y calcula el precio provisional a partir del margen. Así se detectan una tarifa equivocada, un concepto omitido y una fórmula de margen incorrecta. Las dimensiones proceden del resultado revisado; esta prueba no duplica las constantes geométricas del fixture.

El informe observado se guarda en `.runtime/production/acceptance-report.md`. Debe incluir cada comprobación y los identificadores de trabajo, ejecución y revisión. No incluye contraseñas ni contenido del archivo de usuarios.

La ejecución local terminó con ocho comprobaciones PASS. El servidor rechazó el acceso anónimo, sustituyó `spoofed-client-name` por `acceptance-auditor`, protegió el enlace directo al artefacto, conservó trabajo, revisión, planos y coste tras crear otra aplicación, y no invocó el proveedor inyectado. El conflicto de `mesa_demo_004.dxf` permaneció en `needs_review` después de aceptar la hipótesis.

El catálogo configurado `acceptance-erp-2026-11` produjo un coste completo de 313,58 EUR, 5,5 horas y `operation:cut-real` como mayor contribuyente. Aplicó `board-real` al tablero y el override `solid-real` al sistema de soportes. Con margen explícito del 20 %, el precio provisional fue 391,98 EUR. El test recalculó cada concepto y el precio con `Decimal`; no leyó constantes ni helpers de la implementación. Estas cifras prueban el cálculo y la persistencia con un catálogo no-demo; no son tarifas comerciales.

Comandos observados:

```powershell
C:\Users\Álvaro Schwiedop\Desktop\KriptaStudios\1hack\Vexplorer\.venv\Scripts\python.exe -m pytest tests/test_production_acceptance.py -q
C:\Users\Álvaro Schwiedop\Desktop\KriptaStudios\1hack\Vexplorer\.venv\Scripts\python.exe -m tools.audit_production --catalog .runtime/production/acceptance-catalog.json --data-dir .runtime/production/acceptance-data-final-v2 --report .runtime/production/acceptance-report.md
```

Resultado: 3 pruebas aprobadas, incluida la repetición sobre el mismo runtime, y ocho comprobaciones operativas PASS. FastAPI emitió el aviso conocido de deprecación de `httpx` en `TestClient`; no afectó el recorrido.

## Piloto mecánico regenerado

Los directorios `engineering_evaluation_pilot` y `engineering_evaluation_pilot_v2` quedan como registros históricos inválidos para una evaluación aislada. El primero no ofrece ZIP por caso. En v2, `agent_cases/visual-003.zip` revela `read_dimensions_with_abstention` y declara que faltan espesor y cantidad. Esa metadata anticipa la respuesta esperada.

Se generó `C:\Users\Álvaro Schwiedop\Desktop\KriptaStudios\1hack\engineering_evaluation_pilot_v3` sin sobrescribir los pilotos previos. La fuente auditada contiene 421 archivos, 65 casos y 93 rutas; el SHA-256 de su manifiesto es `60b45a6135f5e3fd3efdb363897eadccf5336753ca6ff2e1fc3a88b7fc5adefb`.

La salida v3 contiene 17 ZIP aislados y 68 entradas en `SHA256SUMS`. Cada ZIP contiene solo `input.dxf` o `input.pdf` y `case.json`; el hash de la entrada coincide con `case.json`. Ningún `case.json` contiene `abstention`, `thickness` ni `quantity are unknown`. El caso visual 003 publica la tarea genérica `read_dimensions`; `evaluator_reference.zip` conserva `thickness_from_input: null` fuera del paquete del agente. Esta preparación no ejecuta inferencia.

## Ensayo acotado de PlankAssembly

`tools/prepare_plankassembly.py` lee como máximo diez nombres del split elegido. Excluye `planks[0]`, conserva `source_index` y los valores de `attach` en el espacio original, y admite modelos sin `normal`. La salida pública contiene tres proyecciones ortográficas del conjunto como líneas DXF, sin textos, BOM, roles, nombres de origen ni vistas locales separadas. La referencia vive en otro directorio y conserva los programas fuente por hash, los índices y las normales disponibles.

Las pruebas usan dos programas propios, uno sin `normal`; también comprueban que DXF, ZIP y manifiestos sean idénticos entre dos ejecuciones. El ensayo local real tomó los seis primeros IDs de `valid` y produjo:

- `plankassembly_adapter_trial_v1`: seis DXF y seis ZIP; SHA-256 de `SHA256SUMS` `c560dd59db861c517785391efd740ad9aae592ab2cd718c2da45bf17410a65a7`.
- `plankassembly_adapter_trial_v1_private`: referencia separada; SHA-256 de `SHA256SUMS` `24668e261827a32c52cbb4728aabe2f61c0a793672a1144c38f484471d0f97e2`.

El hash de familia asignó cinco casos a `development` y uno a `holdout`; los seis hashes de familia fueron distintos. La muestra no prueba diversidad semántica, ausencia de duplicados ni inferencia. Ninguno de esos seis programas carecía de `normal`; el fixture propio prueba ese caso de formato. Los datos y derivados quedan fuera de Git por la licencia CC BY-NC-ND 4.0 y no se autorizan para redistribución.

## Límites pendientes de aceptación externa

El ensayo local no sustituye pruebas con tarifas, planos y tiempos proporcionados por la empresa. Tampoco prueba TLS en un host, restauración de una copia en infraestructura ajena, uso concurrente prolongado, proveedor LLM real ni validación de fabricación. El informe de aceptación debe marcar esos puntos como no verificados, sin convertirlos en resultados positivos.
