# Operación de la Biblioteca pública

## Estado observado el 2026-11-14

La Biblioteca pública vacía es coherente con la política vigente: **solo muebles reales revisados**. Configurar el proveedor de embeddings habilita la generación de vectores cuando se guarda una revisión; no crea ni publica registros por sí solo.

Inspección de solo lectura de `https://gex-dashboard.hopto.org/vexplorer/`:

- `semantic.available=true`, modelo `text-embedding-3-small`, 256 dimensiones;
- `GET /api/v1/library` devolvió cero elementos;
- `shared/data/vexplorer.sqlite3` pasó `integrity_check=ok` y contenía 3 runs, 4 resultados, 0 elementos de Biblioteca y 0 vectores en caché;
- los tres runs usaban el mismo documento de 51.234 bytes y SHA-256 `c8aa3006c1098f06df0bc56ac57dfa4e46f597aa5f7c721818e4608d7d367d82`, idéntico a `data/planos_demo/mesa_demo_001.dxf`;
- el único resultado `completed` tenía una revisión cuyo motivo lo identifica como «Ensayo automático de despliegue sobre datos propios sintéticos»; los otros dos resultados estaban `needs_review` y sin revisión.

Por tanto, ninguno es elegible. No se deben copiar las bibliotecas locales de pruebas ni los datos económicos a esta Biblioteca: pertenecen a otros dominios y sus fixtures no son muebles reales de producción.

## Selección explícita y dry-run

`tools/backfill_library.py` parte de un manifiesto creado por el operador. No descubre candidatos ni convierte una bandera CLI en prueba de procedencia. Cada entrada exige:

- `source_kind: real_furniture`;
- hash SHA-256 exacto del documento servido por la API;
- referencia de evidencia y de autorización para publicación;
- persona que certifica esos datos y aprobación explícita para Biblioteca pública;
- revisión exacta en estado `completed`, con revisor y motivo persistidos por el servidor;
- ledger no marcado como sintético y hash no incluido entre fixtures conocidos.

Ejemplo de manifiesto (los marcadores no son datos válidos):

```json
{
  "schema_version": "1.0",
  "backup_reference": null,
  "entries": [
    {
      "run_id": "run-00000000000000000000000000000000",
      "result_revision": 2,
      "label": "Armario de proyecto revisado",
      "embedding_mode": "openai",
      "provenance": {
        "source_kind": "real_furniture",
        "document_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "authorization_reference": "referencia-interna-de-aprobacion",
        "evidence_reference": "orden-o-expediente-revisado",
        "attested_by": "operador-responsable",
        "approved_for_public_library": true
      }
    }
  ]
}
```

El modo predeterminado solo inventaría y validaría el plan:

```powershell
.\.venv\Scripts\python.exe -m tools.backfill_library `
  --base-url https://gex-dashboard.hopto.org/vexplorer `
  --manifest .runtime/library-selection.json `
  --report .runtime/library-dry-run.json
```

El comando devuelve código 3 si alguna selección no es elegible y no escribe ninguna. `--apply` solo se usa tras revisar un dry-run íntegramente elegible y sustituir `backup_reference` por la referencia concreta de una copia v2 nueva y verificada del estado productivo. La escritura envía además el gate tipado `publication` con `source_kind`, `source_reference` y la aprobación; por ello un release anterior que no aplique la política productiva rechaza el campo extra en lugar de publicar silenciosamente. Si ya existe un embedding, una selección `offline` se rechaza para no degradarlo. Tras aplicar, el comando vuelve a leer la Biblioteca y comprueba cada `run_id` y revisión.

El contrato actualizado de `LibraryItem` conserva la referencia de fuente y la atestación derivada por el servidor: identidad autenticada o, en acceso anónimo, la identidad manual de la revisión; nunca acepta `attested_by` o `attested_at` aportados por el cliente. El informe operativo conserva además la referencia separada de autorización y del backup. Debe guardarse con acceso restringido junto con su evidencia; no se debe publicar si las referencias contienen datos internos.

## Activación y reversión del código revisado

No se despliega un snapshot mientras sus bytes sigan cambiando. El corte requiere `SHIP` del revisor Astra, suite integrada y QA independiente sobre el paquete exacto. El repositorio puede conservar cambios revisados sin commit: la autoridad del corte es el archivo inmutable, su manifiesto y sus hashes, no un requisito artificial de worktree limpio.

La inspección posterior detectó que producción avanzó a `cad-d0ea7a85e787`, commit `d0ea7a85e787f4358ab4dbb05ea0250395f2083b` de `feat/cad-completion`. Ese release contiene 35 rutas runtime que no existen en el HEAD `c94a888` del worktree principal, incluidas reconstrucción 3D, explorador semántico y planos de construcción. Por ello queda prohibido activar un paquete construido solo desde `c94a888`: los cambios de Biblioteca deben integrarse y revisarse sobre `feat/cad-completion` o una descendiente que conserve su manifiesto runtime. Inmediatamente antes de cualquier ensayo se vuelve a leer `current`; un cambio concurrente invalida el valor capturado y detiene el corte.

Esa base CAD también aplica una frontera de acceso público más restrictiva: `GET /api/v1/library` devuelve 403 y la configuración anuncia semántica no disponible. La reparación de Biblioteca debe reconciliar esa política, no sobrescribirla sin revisión. La lectura pública puede mostrar el estado vacío honesto; cualquier escritura debe seguir exigiendo mueble real revisado, atestación tipada y control de admisión. Generar embeddings mediante un proveedor con coste en acceso anónimo requiere una decisión y límite explícitos; configurar el proveedor no autoriza llamadas públicas ilimitadas.

1. Inmediatamente antes del corte, comprobar en solo lectura `readlink -f /home/kripta/apps/vexplorer/current`, estado de `vexplorer.service`, espacio e integridad de las tres SQLite.
2. Generar el paquete desde el commit congelado mediante el tooling de release vigente; verificar manifiesto y SHA-256 local/remoto. No incorporar `.runtime`, datasets, datos ni secretos.
3. Crear una copia v2 nueva de `shared/data` con `tools.backup` y verificarla antes de cambiar `current`. No reutilizar una copia histórica como evidencia del corte nuevo.
4. Ensayar el paquete contra una restauración aislada y comprobar health, lectura de runs, Biblioteca vacía honesta y dry-run del manifiesto aprobado.
5. Activar un release inmutable, actualizar únicamente el symlink `current` y reiniciar solo `vexplorer.service`. No modificar Caddy ni otros servicios si la ruta no cambia.
6. Verificar symlink exacto, health, configuración semántica, Biblioteca, assets y navegador público. Con datos reales autorizados, ejecutar primero dry-run y solo después `--apply`.
7. Si falla servicio, health o smoke, restaurar el symlink anterior y reiniciar únicamente Vexplorer. Una importación ya aplicada no se revierte cambiando código: recuperar la copia previa en un destino ensayado y coordinar el corte de datos por separado.

Tras recibir el commit exacto y el `SHIP`, el ensayo local reproducible es:

```powershell
.\.venv\Scripts\python.exe -m tools.rehearse_library_release `
  --repository . `
  --expected-head <commit-de-40-caracteres-aprobado> `
  --output .runtime\library-release-<identificador-unico>
```

El comando se niega a trabajar si el HEAD base no coincide o el destino ya existe. Admite cambios locales revisados porque `tools.build_release` los congela por allowlist. Construye dos archivos consecutivos, exige igualdad byte a byte y registra `candidate_id`, hash del árbol runtime y SHA-256 del archivo en `rehearsal.json`; si otro proceso altera bytes runtime entre ambas lecturas, la reproducibilidad falla. Es exclusivamente local (`remote_actions=false`): no transfiere, activa, reinicia ni toca datos.

Mientras no exista un run que cumpla todos los criterios, el resultado correcto es mostrar cero diseños y explicar que no hay muebles reales revisados publicados; no generar ejemplos ficticios para ocultar el estado vacío.
