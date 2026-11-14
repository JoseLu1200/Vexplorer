# Verificación de producción pública — 2026-11-14

Estado: desplegado y verificado en https://gex-dashboard.hopto.org/vexplorer/, sin inicio de sesión, conforme a la decisión expresa del usuario. No se modificó el checkout de la otra sesión ni se sustituyó su trabajo: se integró `origin/main` en el release.

## Identidad del release

- Commit ejecutado: `d0ea7a85e787f4358ab4dbb05ea0250395f2083b`.
- Padres: `b6bc4af892aeec9a85511af363feb9894ff02cf4` y `0d9dee742e6a72f9e8d707551ebb63e2acd0ff82`.
- Directorio activo: `/home/kripta/apps/vexplorer/releases/cad-d0ea7a85e787`.
- Archivo de distribución SHA-256: `02c05a5dd7afa725ab321aa0a838e4afe2888d64b3b47e571c4300b75e0bacd6`.
- Manifest SHA-256: `317c42f831e691d2457f443755a880b382974565d0e241c23a2e2587a0f6c118`.
- CI del release: [43592672878](https://github.com/JoseLu1200/Vexplorer/actions/runs/43592672878), aprobada.
- Servicio activo, un worker y escucha exclusivamente en `127.0.0.1:18792`.

Las revisiones documentales posteriores no cambian el código de este release.

## Correcciones verificadas

El primer F02 live terminó pero produjo piezas sin cotas en los derivados: el crítico había omitido sus decisiones por campo, aunque la propuesta contenía valores. Se conserva ese FAIL. La corrección exige cobertura explícita, comprobaciones visuales dirigidas al campo y una nueva respuesta del crítico cuando omite decisiones; no acepta automáticamente valores por superar geometría determinista.

Un segundo FAIL identificó una confusión entre categoría constructiva de herraje e identificación comercial. Se aclaró que aceptar `kind=hardware` como hipótesis no identifica un fabricante ni certifica especificaciones. No se relajó el auditor ni se forzó la aceptación de campos desconocidos.

Se conservaron el panel 3D y la UX incorporados por `main`. El recorrido 3D comparte ahora admisión pública con CAD, exige idempotencia, limita sucesores y almacenamiento, y entra en las copias y comprobaciones de trabajos activos.

## Pruebas y ejecuciones reales

| Comprobación | Resultado observado |
|---|---|
| Suite Python completa | 895 aprobadas; dos avisos de deprecación externos |
| Suite frontend completa | 194 aprobadas |
| Ruff sobre Python modificado | Aprobado |
| Revisión GPT-6 Astra | Sin bloqueantes P0/P1 en el alcance revisado |
| F02 en candidato exacto, sobre restauración | 11 PASS y un SKIP del histórico privado; nueve tipos de piezas fabricadas, 27 medidas numéricas, dos tipos de herrajes con cinco campos pendientes; 11 SVG y 11 DXF por pieza |
| F01 nuevo desde HTTPS público | 11 PASS y un SKIP del histórico privado; seis tipos de piezas fabricadas, 18 medidas, un tipo de herraje con tres campos pendientes; siete SVG y siete DXF por pieza |
| Reconstrucción 3D nueva desde HTTPS | Nueve componentes, 38 artefactos descargados; reenvío idempotente conserva el mismo job |
| Navegador real, sin mocks | Fuente, construcción y piezas renderizan; cotas/rangos/premisas legibles; cero peticiones privadas, errores de consola/página o respuestas fallidas |

F02: `job-477548e4a3f34a41bafdc1a7dc7abd7e`, `run-2c017f406d8542f6af222d7b18472c14`, P1/R1. F01 público: `job-c274ad8111844cc3ad5ceb22b4062f5a`, `run-475e0cc1ab924aa4b4257c8eae88d55d`, P1/R1. En ambos se comprobaron hash del original, imágenes PNG realmente entregadas, Sol proponente/Astra crítico separados, procedencia de estimaciones y artefactos ligados a la revisión exacta.

3D: `bc9ac84f882044dd874f3e0606612b15`, estado honesto `needs_review`, `certified_for_manufacturing=false`. `assembly.glb`: 9.380 bytes, SHA-256 `b344d35620dd6b6001c00a31466ae6d6d002454e14ef0244b8c723145525d058`.

También se ejecutó ingesta DWG genuina con LibreDWG 0.14 en el candidato anterior: original preservado byte a byte; DXF R2018 normalizado, unidades metros/escala 1000 mm, 130 entidades (121 polilíneas, seis cotas y tres textos). Coincidió con su DXF público emparejado en unidades, tipos y límites. El recorrido `geometry_only/general_furniture` pasó sin llamadas de modelo. El recorrido rectangular legado rechazó ese mismo dibujo con `unsupported_geometry`; no se oculta esa limitación.

## Reinicio, copia y restauración

El recolector comparó códigos y SHA-256 de assets, configuración, sesión, job, run, revisiones/derivados CAD, DXF de pieza, estado 3D y GLB en cuatro momentos:

1. Antes del reinicio.
2. Después de reiniciar únicamente Vexplorer.
3. Después de ejecutar el servicio real de backup.
4. Sobre otra instancia arrancada con los datos restaurados.

Todas esas respuestas fueron idénticas. El histórico público y una mutación con origen ajeno devolvieron 403 en las cuatro fases. Los ocho endpoints vecinos conservaron sus códigos: `/` 200, `/nexia/` 200, `/carta/` 404, `/evocon/` 200, `/altare/` 200, `/j-aautomation/` 308, `/webmail/` 404 y `/api/` 404.

Copia real: `/home/kripta/apps/vexplorer/shared/backups/scheduled-20261114T121333Z.zip`, SHA-256 `376c1c1d7938f7be04d26beb3103fdf720521d39f5685c3b482162b9991c5f73`. Se verificó, restauró y descargó al equipo local con el mismo hash. Destino ensayado: `/home/kripta/apps/vexplorer/shared/restores/scheduled-evidence-20261114T121329Z`.

El temporizador quedó habilitado y activo; el servicio de copia devolvió `Result=success`. Los valores del env fuera de las claves del despliegue se compararon y permanecen idénticos. El hash del archivo de usuarios coincide con el registrado antes del cambio.

## Evidencia y alcance

Resumen estructurado: [production_public_2026-11-14.json](../evaluation/results/production_public_2026-11-14.json). Los informes completos, capturas y copia descargada permanecen fuera de Git en `.runtime/prod-ready/`, `.runtime/qa-final-f02/` y `.runtime/qa-production-final/`. El informe remoto está en `incoming/evidence-20261114T121329Z/report.json` bajo la raíz de la aplicación.

F01/F02 son controles propios de desarrollo, no un corpus industrial independiente. Este cierre acredita funcionamiento y operación del software; no precisión industrial universal ni fabricación certificada. Se mantienen como pendientes materiales, cargas, fijaciones y especificaciones no justificadas. La evaluación estricta anterior y sus FAIL siguen documentados en [VERIFICACION_CAD_COMPLETION_2026-11-14](VERIFICACION_CAD_COMPLETION_2026-11-14.md).
