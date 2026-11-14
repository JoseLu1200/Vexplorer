# Demo con resultados ya procesados en la web app

**No hay visor nuevo ni llamadas a un modelo.** Se usa la web app existente, con un backup nativo de sus datos. Solo hace falta la instalación habitual de Vexplorer; no se carga de nuevo el DXF ni se lanza un análisis. El navegador sigue hablando con el backend de la aplicación, pero no con una API de IA.

Descarga [el paquete completo](https://github.com/JoseLu1200/Vexplorer/releases/download/datasets-demo-2026-11-14/vexplorer-demo-procesada.zip) o usa [los archivos del repo](../data/muebles_procesados_demo/). Los archivos JSON exportados son auditables; la forma soportada de cargar todos los resultados en la app es restaurar `demo-runtime.zip`, no subir JSON mediante «Cargar plano».

## Qué está preparado

| Caso | Estado guardado | Qué mostrar |
|---|---|---|
| Estantería 900 | Revisión 2, completada | 4 filas de despiece, 6 piezas físicas; baldas de 864 mm; esquema 3D y coste sintético |
| Estantería variante | Revisión 2, completada | Diferencias dimensionales y comparación geométrica |
| Mueble bajo | Revisión 2, completada | Otra configuración de la misma familia |
| Espesor desconocido | Revisión 1, pendiente | Plano y evidencia conservados; sin inventar despiece ni 3D confirmado |

Incluye los DXF, dibujos/ledger, revisión inicial, decisiones de ensayo, resultados, explicaciones, escenas, despieces CSV, comparables, estimaciones y trazas. La biblioteca tiene tres entradas **DEMO SINTÉTICA** con descriptores geométricos; no necesita embeddings. El histórico incluye **4 presupuestos publicados y 15 coeficientes publicados de tiempo**, con `origin=published`, referencias y limitaciones. No son costes reales cerrados de vuestra empresa.

## Restaurar y abrir (PowerShell)

Desde la raíz de un checkout que incluya estos datos, con las dependencias habituales instaladas:

```powershell
python -m tools.backup restore --archive data/muebles_procesados_demo/demo-runtime.zip --destination .runtime/demo-procesada
$env:VEXPLORER_ENV = "local"
$env:VEXPLORER_AUTH_ENABLED = "false"
$env:VEXPLORER_ROOT_PATH = ""
$env:VEXPLORER_DATA_DIR = (Resolve-Path .runtime/demo-procesada).Path
$env:VEXPLORER_HISTORY_DB = Join-Path $env:VEXPLORER_DATA_DIR "history.sqlite3"
$env:OPENAI_API_KEY = ""
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18863
```

El destino debe ser nuevo: el restaurador verifica hashes, SQLite y rutas y no sobrescribe un directorio existente. El ZIP descargable tiene la misma estructura `data/muebles_procesados_demo/`; puede extraerse en una carpeta de trabajo y pasar su ruta al comando.

Abrir estos enlaces, que corresponden a la instantánea publicada:

- [Estantería 900](http://127.0.0.1:18863/?run=run-37671509ad734b64ba80e0f5ae3b5d73).
- [Estantería variante](http://127.0.0.1:18863/?run=run-939b010819244d97b40a4f806779b1c3).
- [Mueble bajo](http://127.0.0.1:18863/?run=run-6c689b556df4484b9887436eafe7a7fa).
- [Espesor desconocido](http://127.0.0.1:18863/?run=run-4af4c91059af4e3fa05d3f08d3cd5df7).

Los IDs también están en [manifest.json](../data/muebles_procesados_demo/manifest.json). Son válidos después de restaurar; no apuntan a ejecuciones existentes en la instancia pública. Regenerar el paquete crea otros IDs.

## Mostrarlo en el host de producción

Se ejecuta **el mismo código de la web app** con un directorio de datos de demo separado y un puerto de loopback. No sustituir `shared/data` por este backup: contiene fixtures y su biblioteca sintética, que no pertenece a la Biblioteca pública de muebles reales.

En el host, desde un checkout/release compatible y con su entorno Python activado, copiar o descargar el ZIP y ejecutar:

```bash
python -m tools.backup restore \
  --archive /ruta/descargada/data/muebles_procesados_demo/demo-runtime.zip \
  --destination /home/kripta/apps/vexplorer/shared/demo-procesada-20261114

VEXPLORER_ENV=local VEXPLORER_AUTH_ENABLED=false VEXPLORER_ROOT_PATH= \
VEXPLORER_DATA_DIR=/home/kripta/apps/vexplorer/shared/demo-procesada-20261114 \
VEXPLORER_HISTORY_DB=/home/kripta/apps/vexplorer/shared/demo-procesada-20261114/history.sqlite3 \
OPENAI_API_KEY= \
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18863
```

Desde el ordenador del presentador:

```console
ssh -N -L 18863:127.0.0.1:18863 kripta
```

Abrir los enlaces anteriores. La aplicación y los datos corren en el host productivo, aislados del servicio público; el túnel es solo transporte. No hace falta cambiar Caddy, `current`, `production.env` ni reiniciar `vexplorer.service`. Parar Uvicorn y el túnel termina la demo. Si el puerto local está ocupado, elegir otro en la primera parte de `-L` y en los enlaces.

## Guion de demostración

1. Abrir Estantería 900. Mostrar plano, despiece y revisión 2 ya guardada; el estado original del run puede seguir siendo `needs_review`, mientras la revisión actual está completada.
2. Abrir 3D esquemático y las explicaciones de las piezas. La colocación es una interpretación revisada de ensayo, no una certificación de fabricación.
3. Mostrar la estimación guardada y descargar JSON/CSV. La tarifa del fixture es sintética, diferenciada del histórico académico publicado.
4. En Biblioteca, usar **Geometría** y buscar similares. Los descriptores ya están guardados; la comparación determinista local no llama a un modelo. Los resultados de referencia también se incluyen en `similitud_geometrica.json`.
5. Abrir el caso de espesor desconocido. Enseñar la abstención sin volver a analizar ni completar medidas.
6. En Histórico, mostrar los 19 registros publicados, sus fuentes y campos ausentes. No hay que volver a importarlos.

No pulsar «Agente en vivo», «Replay real» ni «Nueva ejecución»: no son necesarios para esta demo. No se incluyen respuestas LLM grabadas ni embeddings semánticos; no se presentan como resultados disponibles. La reconstrucción incluida es la **escena esquemática** del resultado, no una nueva reconstrucción generativa.

## Comprobaciones realizadas

Prueba automatizada de generación y restauración en otra carpeta: cuatro runs recuperables, tres entradas de biblioteca, 19 registros de histórico, planos/ledger/escenas/explicaciones accesibles y resultados/escenas idénticos a los exportados, con proveedor de IA desactivado. Se comprueba también que el generador no reutiliza una base externa configurada ni sobrescribe destinos.

No se ha cargado este paquete en `shared/data` ni modificado el despliegue productivo. Para regenerar solo los fixtures propios: `python -m tools.build_processed_demo --output .runtime/demo-nueva`.
