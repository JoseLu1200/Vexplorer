# Desplegar la landing, el portal y los ejemplos de Vexplorer

Guía de traspaso para otro agente u operador. Fecha: 15-11-2026. Código de referencia verificado: `e6d8cd7` en `main`. Todos los comandos parten de la raíz de un clon de Vexplorer salvo indicación expresa.

## 1. Qué se abrió realmente en esta sesión

Se compilaron las dos aplicaciones de diseño y se sirvieron sus carpetas `dist` por HTTP local:

| URL local | Directorio servido | Función |
|---|---|---|
| `http://127.0.0.1:18782/` | `diseno/landing/dist/` | Landing con recorrido animado, cajonera, QR y enlace al portal publicado. |
| `http://127.0.0.1:18781/#/` | `diseno/portal/dist/` | Portal nuevo, en modo de ejemplos, con casos procesados y reconstrucciones guardadas. |

Se usó `python -m http.server`, enlazado a `127.0.0.1`. No se desplegó una nueva versión en Vercel ni en el VPS durante esta apertura. Estos puertos son una elección local, no una dependencia del producto. La máquina original utilizó una worktree de integración; en otro PC basta un clon normal.

**La demo estática no ejecuta nuevas inferencias.** Consume los casos exportados del repositorio. Parte de esos casos sí fue generada previamente por nuestro harness con modelos; otra parte procede del motor geométrico sin LLM. No confundir reproducción de un resultado guardado con generación nueva.

Hay tres aplicaciones distintas:

- `diseno/landing/`: landing Vite/React.
- `diseno/portal/`: portal nuevo Vite/React/TypeScript. Por defecto usa ejemplos (`VITE_USE_MOCK=true`).
- `frontend/`: interfaz clásica servida por FastAPI y por el Dockerfile actual. Construir Docker **no compila ni publica automáticamente** las dos aplicaciones de `diseno/`.

## 2. Preparación en otro equipo

Requisitos para la demo estática: Git, Node/npm y un servidor HTTP. Python sirve como servidor sencillo. Las versiones comprobadas en CI son Node **24.11.0** y Python **3.14.2**. Usar los lockfiles con `npm ci`, sin actualizar dependencias durante el despliegue.

```bash
git clone https://github.com/JoseLu1200/Vexplorer.git
cd Vexplorer
git checkout main
git pull --ff-only
git rev-parse HEAD
npm ci --prefix diseno/landing
npm ci --prefix diseno/portal
```

El repositorio puede requerir autenticación de Git según los permisos de la cuenta. No copiar credenciales del equipo anterior. Los datos de demo versionados pueden hacer que la descarga sea considerable.

## 3. Arranque rápido: la misma demo que se mostró

Comprueba que no haya `.env.local` antiguos en `diseno/portal` configurando otro backend. Las variables `VITE_*` se incorporan **al compilar**: cambiarlas después de generar `dist` no cambia el comportamiento del bundle.

### Windows / PowerShell

```powershell
$env:VITE_USE_MOCK = "true"
$env:VITE_API_BASE = ""
npm run build --prefix diseno/landing
npm run build --prefix diseno/portal
```

En dos terminales, desde la raíz del repo:

```powershell
python -m http.server 18782 --bind 127.0.0.1 --directory diseno/landing/dist
```

```powershell
python -m http.server 18781 --bind 127.0.0.1 --directory diseno/portal/dist
```

Para dejarlos en segundo plano, esta sesión usó el equivalente a:

```powershell
$landingDist = (Resolve-Path diseno/landing/dist).Path
$portalDist = (Resolve-Path diseno/portal/dist).Path
$landingProcess = Start-Process python -ArgumentList @('-m','http.server','18782','--bind','127.0.0.1') -WorkingDirectory $landingDist -WindowStyle Hidden -PassThru
$portalProcess = Start-Process python -ArgumentList @('-m','http.server','18781','--bind','127.0.0.1') -WorkingDirectory $portalDist -WindowStyle Hidden -PassThru
Start-Process 'http://127.0.0.1:18782/'
Start-Process 'http://127.0.0.1:18781/#/'
```

Conserva los PID devueltos para detener únicamente tus servidores. Si un puerto está ocupado, usa otro; no mates procesos desconocidos.

### Linux / macOS

```bash
npm run build --prefix diseno/landing
VITE_USE_MOCK=true VITE_API_BASE='' npm run build --prefix diseno/portal
```

En terminales separadas:

```bash
python3 -m http.server 18782 --bind 127.0.0.1 --directory diseno/landing/dist
```

```bash
python3 -m http.server 18781 --bind 127.0.0.1 --directory diseno/portal/dist
```

Abre las dos URLs de la sección 1. No abrir `index.html` mediante `file://`: los chunks y las rutas de recursos requieren HTTP.

### Cómo llegar al ejemplo generado y evitar enlaces rotos

En el portal, pulsa la tarjeta superior **Estantería de tres huecos** y el botón **3D**. El proceso puede recorrer automáticamente las vistas; ciérralo o desactiva Automático si quieres mantener una vista fija. Ese caso es `recon_caso02`: siete componentes propuestos por GPT-6.1 Sol desde alzado, lateral y una cota de anchura; el harness construyó el montaje y el GLB. Conserva hipótesis y estado de revisión.

Los enlaces `#/planos/plan-<UUID>/esquema` usan IDs de **IndexedDB de ese navegador y origen**. No son enlaces portátiles: copiarlos a otro navegador, otro puerto o cambiar `localhost` por `127.0.0.1` puede mostrar «Este plano ya no está en el espacio de trabajo». Comparte `/#/` y el nombre de la tarjeta. No borres IndexedDB para arreglarlo: podría contener planos subidos por el usuario. El portal actual no ofrece una ruta pública estable por `casoId`.

## 4. Archivos de datos y procedencia

| Ruta desde la raíz | Contenido y uso |
|---|---|
| `diseno/portal/src/casos/datos/*.json` | Casos congelados que carga el portal. Contienen `sources`, `execution`, revisiones, propuestas y resultados. Reconstrucciones con medios incrustados cuando están disponibles. |
| `diseno/portal/src/casos/index.ts` | Catálogo, nombres, IDs de casos, runs guardados y hashes de entradas reconocidas. |
| `diseno/portal/src/api/fixtures/` | Respuestas de ejemplo del cliente mock: revisiones, errores, biblioteca y similitud. |
| `diseno/portal/src/assets/dxf/` | DXF empaquetados para los ejemplos de la interfaz. |
| `data/planos_demo/` | Planos sintéticos propios de mesas, estanterías y piezas separadas; manifiestos de fixtures. |
| `data/muebles_procesados_demo/` | DXF y resultados procesados sin LLM, con revisión y tarifas de ensayo. |
| `data/cad_completion_controls/public/` | Controles propios F01 mesa, F02 cajonera y F03 estantería. |
| `evaluation/results/cad_completion_live_2026-11-14/` | Propuestas/resultados de F01-F03 y evaluación estricta. Conserva también límites y fallos. |
| `data/plank_pipeline_demo/` | Resultados reales guardados de plank-030, plank-016 y mesas; documentos, runs, derivados, láminas y backup. |
| `data/semantic_pipeline_demo/` | Backup semántico, vectores, vecinos, snapshots, renders y `portable-inputs.zip`; permite presentar embeddings sin recalcularlos. |
| `data/full_app_demo/` | Paquete ampliado para restaurar backend: `demo-runtime.zip`, `catalog.json`, manifiesto, documentos, runs y reconstrucciones. Incluye los paquetes anteriores. |
| `data/full_app_demo/reconstruction/<job_id>/` | `status.json`, `source.png` y `artifacts/` con GLB, BOM, renders y planos disponibles. |
| `data/datasets/plankassembly/` | Metadatos de procedencia y ficha archivada; **no contiene el corpus completo original**. |
| `data/datasets/furniture_costs/`, `data/datasets/furniture_hours/` | Datos y documentación auxiliares de costes/horas; consultar sus README/manifiestos para alcance y procedencia. |
| `evaluation/reference/` | Referencias del evaluador. No servirlas como archivos públicos ni introducirlas como respuesta en el harness. |

El paquete completo documenta 20 ejecuciones, 10 trabajos de reconstrucción, 8 registros de biblioteca y 14 espacios vectoriales. Son conteos de la **demo restaurable**, no del servidor público ni de diseños distintos.

### Qué ejemplos son generativos

- `recon_caso01` a `recon_caso06`, `recon_mesa` y `recon_control`: trabajos de reconstrucción con `generated_design_hypothesis`, GPT-6.1 Sol y artefactos del harness. Los casos 01-03 parten de planos propios; 04-06, de controles ambiguos derivados de PlankAssembly. El control sin escala tiene una abstención inicial y una revisión con aclaraciones.
- `plank_030` y `plank_016`: planos adaptados del dataset; propuestas de Sol y revisión de Astra. No son el despiece de referencia copiado al resultado.
- F01-F03 y el PDF raster: propuestas guardadas de la vía con modelo.
- Mesas de catálogo, estanterías legacy y piezas separadas: cálculo geométrico y revisiones de ensayo sin LLM. Los costes de demo son sintéticos.

No presentar los estados `needs_review`, cotas estimadas o modelos esquemáticos como fabricación validada. La animación de la landing reproduce el caso F02; no es un backend generando mientras se hace scroll.

## 5. Recursos locales que no aparecen al clonar

`diseno/portal/public/local/` está ignorado por Git. Los casos 3D versionados incluyen medios incrustados que permiten la demo básica, pero el mapa, ciertas previews y rutas de descarga necesitan archivos adicionales. Vite copia `public/` a `dist/` **durante el build**: prepáralos antes de compilar.

### Recuperar previews y archivos 3D sin regenerar los JSON

Guarda el siguiente bloque como `.runtime/preparar_assets_portal.py` (crea antes `.runtime/`) y ejecútalo desde la raíz con `python .runtime/preparar_assets_portal.py`. Solo copia archivos de datos ya versionados; no llama a modelos:

```python
from pathlib import Path
import shutil

root = Path.cwd()
source = root / "data/full_app_demo"
dest = root / "diseno/portal/public/local"
for job in (source / "reconstruction").iterdir():
    if not job.is_dir():
        continue
    target = dest / "reconstruccion" / job.name
    target.mkdir(parents=True, exist_ok=True)
    if (job / "source.png").is_file():
        shutil.copy2(job / "source.png", target / "source.png")
    if (job / "artifacts").is_dir():
        shutil.copytree(job / "artifacts", target, dirs_exist_ok=True)
preview = source / "documents/doc-586b1d861e3345678b2f3ed36698262c/1-preview.png"
if not preview.is_file():
    raise FileNotFoundError(preview)
(dest / "documentos").mkdir(parents=True, exist_ok=True)
shutil.copy2(preview, dest / "documentos/pdf_raster.png")
```

El exportador oficial `diseno/portal/scripts/build_casos.py <ruta-absoluta-repo>` también prepara recursos, pero **reescribe los JSON versionados** y vuelve a extraer geometría con el código actual. No ejecutarlo solo para servir una demo ya congelada. Si se necesita reexportar, revisar el diff y las revisiones antes de publicarlo. Tampoco omitir su argumento de repositorio: su ruta por defecto pertenece a otro equipo.

### Mapa de embeddings preparado, sin modelos

Con Python y numpy instalados, desde la raíz:

```bash
python -I diseno/portal/scripts/mapa_embeddings.py --demo data/semantic_pipeline_demo --out diseno/portal/public/local/mapa
```

El script lee vectores/vecinos guardados, calcula la proyección y extrae renders; no llama a una API ni genera embeddings nuevos. Después compila el portal con `VITE_PUBLICO=1` para iniciar el mapa en EmbeddingGemma 2 y ocultar la opción geométrica del corpus completo:

```bash
VITE_USE_MOCK=true VITE_PUBLICO=1 npm run build --prefix diseno/portal
```

En PowerShell: `$env:VITE_PUBLICO = "1"` antes de `npm run build --prefix diseno/portal`. Esto es una decisión de presentación del mapa; no convierte ejemplos en muebles reales revisados ni constituye una medida de control de acceso.

Verificar `http://127.0.0.1:18781/local/mapa/espacios.json` y `/#mapa`. El arranque local original de esta sesión no reconstruyó este mapa: no atribuirle todos los recursos de la web publicada.

Las proyecciones adicionales UMAP/t-SNE se preparan con `diseno/portal/scripts/mapa_proyecciones.py` (consultar sus argumentos y dependencias antes de ejecutarlo). Sin esos archivos, el cargador conserva PCA 3D; generar únicamente `mapa_embeddings.py` no reproduce todas las proyecciones de un despliegue anterior.

### Corpus PlankAssembly completo, opcional

No es necesario para abrir los muebles congelados. En el equipo de preparación estaba en `../plankassembly_dataset/` respecto al checkout principal, **fuera de Git**: `data.zip`, `extracted/data/model/` y `extracted/data/splits/`. Esa ruta no se traslada automáticamente a otro PC o worktree.

La revisión fijada es `d1d4308f0ee0aac2f9f407b3533ff83ecee22d34`; SHA-256 de `data.zip`: `3a7f6d0bb66ace28a3a05e286c127b5385954e29bfa7ed2e932121b2429a460c`. Contiene programas JSON, no planos DXF originales. Hay 26.707 modelos en las particiones oficiales. Instrucciones de obtención e integridad: [PLANKASSEMBLY.md](PLANKASSEMBLY.md). La ficha archivada declara CC BY-NC-ND 4.0; preservar atribución y condiciones.

El mapa geométrico completo se prepara mediante `diseno/portal/scripts/mapa_generar.py --zip <data.zip> --raros <seleccion.json> --out diseno/portal/public/local/mapa`. Requiere el ZIP y la selección del estudio; no inventar la selección ni afirmar que está instalada por clonar el repo. Consultar `--help` y conservar el paquete `public/local/mapa` del despliegue si no se van a regenerar sus fuentes. No copiar referencias privadas de evaluación al directorio público.

## 6. Publicar landing y demo estática en VPS o hosting

Este es un procedimiento reproducible propuesto para otro servidor; no es un redespliegue del VPS realizado en esta sesión.

1. Preparar ejemplos/recursos opcionales y compilar como arriba.
2. Copiar **todo el contenido** de `diseno/landing/dist/` a la raíz de la web de landing y **todo** `diseno/portal/dist/` a la del portal. Conservar chunks y `local/`; no publicar solo `index.html` del portal normal.
3. Usar dos dominios/subdominios, por ejemplo `www.example.com` y `demo.example.com`, con HTTPS. No publicar la raíz del repositorio como document root.
4. Configurar un servidor estático. Ejemplo Caddy, en un VPS donde Caddy ya esté instalado y los DNS apunten al servidor:

```caddyfile
www.example.com {
    root * /srv/vexplorer/landing
    encode gzip zstd
    file_server
}

demo.example.com {
    root * /srv/vexplorer/portal
    encode gzip zstd
    file_server
}
```

Validar la configuración con `caddy validate --config <ruta-Caddyfile>` y recargar el servicio correspondiente. Ajustar permisos de lectura para su usuario, DNS y acceso a 80/443. Las rutas del portal son hash; no requieren convertir las peticiones de archivos inexistentes en `index.html`.

En un hosting con integración Git, crear **dos proyectos**: raíz `diseno/landing` o `diseno/portal`, instalación `npm ci`, build `npm run build`, salida `dist`. Si se necesita mapa/previews, el build debe preparar `public/local` desde el repo completo antes; un build limitado a la subcarpeta no tendrá esas fuentes. Alternativamente subir un `dist` completo precompilado. No se realizó un `vercel deploy` en esta sesión ni se presupone acceso a esa cuenta.

El QR y los enlaces de la landing apuntan actualmente a **https://vexplorer-portal.vercel.app/**. Conservarlo si ese sigue siendo el destino. Para cambiar de destino, localizar texto y SVG con `rg -n 'vexplorer-portal|qr-veta' diseno/landing/src diseno/landing/public`, actualizar también el contenido del QR y verificar su decodificación; cambiar solo el enlace HTML no cambia el QR.

`diseno/landing/build.html` es un **fragmento** generado por `strip.py` para incrustación. Para servir la landing standalone usar `dist/index.html`, que conserva charset y viewport. `npm run build:single --prefix diseno/portal` produce otra variante en `dist-single/`; no confundirla con `dist/` ni con el backend.

## 7. Backend con toda la demo restaurada, sin API de modelos

Para navegar las respuestas reales almacenadas, descargas, histórico y explorador desde un backend, usar el backup ampliado. No restaurarlo sobre datos de producción: contiene ejemplos y biblioteca de ensayo; la Biblioteca pública sigue reservada a muebles reales revisados.

Preparación Python desde la raíz (activar la venv según el sistema):

```bash
python -m venv .venv
# Linux: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-demo.txt
python -m pip install --constraint requirements-demo.txt ".[test]"
npm ci --prefix frontend
python -m tools.backup restore --archive data/full_app_demo/demo-runtime.zip --destination .runtime/demo-app-completa
```

El destino de restore debe ser nuevo. Para reabrir una restauración existente, arrancar directamente: no restaurar de nuevo encima.

PowerShell:

```powershell
$env:VEXPLORER_ENV = "local"
$env:VEXPLORER_AUTH_ENABLED = "false"
$env:VEXPLORER_ROOT_PATH = ""
$env:VEXPLORER_DATA_DIR = (Resolve-Path .runtime/demo-app-completa).Path
$env:VEXPLORER_HISTORY_DB = Join-Path $env:VEXPLORER_DATA_DIR 'history.sqlite3'
$env:VEXPLORER_COST_CATALOG = (Resolve-Path data/full_app_demo/catalog.json).Path
$env:VEXPLORER_EXPLORER_ENABLED = "1"
$env:OPENAI_API_KEY = ""
$env:VEXPLORER_JEV_API_KEY = ""
$env:VEXPLORER_JEV_DAILY_ATTEMPTS = "0"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18864
```

Linux, desde la raíz y la venv activa:

```bash
export VEXPLORER_ENV=local VEXPLORER_AUTH_ENABLED=false VEXPLORER_ROOT_PATH=''
export VEXPLORER_DATA_DIR="$PWD/.runtime/demo-app-completa"
export VEXPLORER_HISTORY_DB="$VEXPLORER_DATA_DIR/history.sqlite3"
export VEXPLORER_COST_CATALOG="$PWD/data/full_app_demo/catalog.json"
export VEXPLORER_EXPLORER_ENABLED=1 OPENAI_API_KEY='' VEXPLORER_JEV_API_KEY=''
export VEXPLORER_JEV_DAILY_ATTEMPTS=0
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18864
```

Usar una terminal limpia, sin `--env-file .env` productivo. Este arranque es **solo loopback** y sin autenticación para demostración local. No exponerlo directamente a Internet. Para demostrarlo desde otro PC a través de un VPS puede usarse un túnel SSH: `ssh -L 18864:127.0.0.1:18864 usuario@servidor`.

URLs estables de la interfaz clásica restaurada:

- Inicio: `http://127.0.0.1:18864/`.
- Salud: `http://127.0.0.1:18864/api/v1/health`.
- Explorador: `http://127.0.0.1:18864/explorer.html`.
- Estantería generada, caso 02: `http://127.0.0.1:18864/reconstruction.html?job=00ba57224b3b00a78fc9a2bbdb6f3405`.
- Mesa con coste: `http://127.0.0.1:18864/?run=run-161fc0b9bf7c46f499ddf84abe105d9b`.

Los `job`/`run` de estas URLs son persistidos en el backup, distintos de los UUID de IndexedDB del portal. Abrir trabajos guardados no llama a modelos. Pulsar Generar o enviar un refinamiento nuevo sí inicia otro flujo y requiere proveedor.

### Portal nuevo conectado al backend local

Con el backend anterior en 18864, crear `diseno/portal/.env.local` (ignorado por Git):

```dotenv
VITE_USE_MOCK=false
VITE_API_BASE=
VITE_API_PROXY=http://127.0.0.1:18864
```

Arrancar `npm run dev --prefix diseno/portal -- --host 127.0.0.1 --port 18783`. Vite reenvía `/api` al backend; abrir `http://127.0.0.1:18783/#/`. Retirar variables `VITE_USE_MOCK=true` de la terminal si quedaron del build anterior, porque pueden prevalecer sobre el archivo.

Para producción, el proxy de desarrollo de Vite **no existe** dentro de `dist`: servir el portal y `/api/*` bajo el mismo origen mediante reverse proxy. El portal puede recurrir a casos congelados si el backend no contiene un run; ver una tarjeta no prueba que provenga del servidor. Las acciones de recuperación del portal nuevo y el aviso global de construcción provisional tienen pendientes documentados en [registro de cierre](../team/agente_despiece_coordinacion.md).

## 8. Backend productivo, modelos y datos persistentes

No confundir el despliegue estático con la configuración productiva. Referencias existentes:

- [compose.yaml](../compose.yaml), [Dockerfile](../Dockerfile), [deploy/production.env.example](../deploy/production.env.example): alternativa Docker/Caddy. Requiere usuarios, catálogo, origen HTTPS, volumen persistente y snapshot local fijado de EmbeddingGemma 2. Sirve `frontend/` por defecto.
- [deploy/SYSTEMD_RELEASE.md](../deploy/SYSTEMD_RELEASE.md), [deploy/systemd-production.env.example](../deploy/systemd-production.env.example): procedimiento del VPS existente con `systemd --user`, releases y datos compartidos. No mezclar las variables de interpolación de Compose con las que lee el servicio.

Los pesos de EmbeddingGemma 2 no están incluidos en Git ni son necesarios para reproducir resultados guardados. La producción usa la revisión fijada en Compose; los nuevos embeddings necesitan su snapshot. Las nuevas inferencias de despiece requieren un proveedor configurado. El relay Codex de `tools/codex_test_bridge.py` es infraestructura de **evaluación local con agentes**, no un sustituto automático de la API en un VPS desatendido.

Antes de actualizar un servicio existente: identificar su runtime y unidad exactos, respaldar y verificar restauración en destino nuevo, conservar secretos/usuarios/catálogo y activar la release con el procedimiento del despliegue. No borrar volúmenes, importar la demo en Biblioteca pública ni sustituir los datos reales por fixtures.

## 9. Comprobaciones de entrega

1. `git rev-parse HEAD`: registrar el commit desplegado.
2. `npm run build --prefix diseno/landing` y `npm run build --prefix diseno/portal`: sin errores.
3. Abrir ambas webs desde una sesión nueva; comprobar escritorio y móvil.
4. En portal: tarjeta Estantería de tres huecos → 3D, piezas/BOM y fuente; mesa con revisión y coste → cotas y total. No marcar inferencias como medidas observadas.
5. Si se preparó mapa: `/#mapa`, `local/mapa/espacios.json`, vecinos y renders sin 404. Si no se preparó, declarar esa limitación.
6. Landing: QR al destino correcto; acentos correctos; no usar el fragmento sin wrapper UTF-8.
7. Backend opcional: health, run guardado, reconstrucción por `job=` y descargas; sin llamadas nuevas a modelos.
8. Comprobar consola/red del navegador y `git status --short`; no añadir `.env`, `dist`, venv, datos privados ni `public/local` a Git.

CI de la base `e6d8cd7`: 1.828 pruebas Python, pruebas de navegador, builds de landing/portal y paquete/Docker aprobados. Esta guía documenta procedimientos; un nuevo VPS requiere sus propias comprobaciones DNS, TLS, permisos y recursos. No acredita que se haya alcanzado el 90 % de precisión de despiece/cotas en un corpus independiente.
