# Producto privado Vexplorer: diseño de cierre

Fecha: 2026-11-14. Base auditada: 10da225. Solicitud del usuario: completar el proyecto con un swarm GPT-6.1 Sol y revisión GPT-6 Astra; destino confirmado: servidor privado para el equipo.

## Objetivo
Vistas 2D de mesa con cotas parciales → propuesta generativa referenciada → revisión técnica → planos generales, por componente y despiece acotados → costes y precio provisional trazables. Mantener el perfil rectangular existente; no atribuir precisión industrial general a fixtures sintéticos.

## Decisiones de implementación
Mantener FastAPI, Pydantic, SQLite y frontend JS. Ampliar la aplicación actual en vez de reescribirla. Los datos observados permanecen inmutables; toda corrección humana crea una revisión y conserva fuente y motivo. Los importes reales requieren catálogo explícito con origen y fecha; no convertir tarifas demo en reales. Presupuestos incompletos no publican totales ni precios cerrados.

Servidor privado con autenticación individual, TLS en proxy, almacenamiento persistente y copias verificables. Configuración de producción falla al arrancar si faltan controles requeridos. Procesamiento limitado y trabajos consultables; nunca afirmar streaming si solo hay historial. No desplegar a un host no identificado ni inventar tarifas, planos reales, tiempos o aceptación de técnicos.

## Alternativas consideradas
Reescribir como SaaS multiempresa exigiría aislamiento/identidad y operación que no corresponde al destino confirmado. Mantener demo sin controles impide compartirla de forma fiable. Se elige reforzar el despliegue privado existente con límites y trazabilidad.

## Aceptación
Pruebas de regresión CAD y de revisión, concurrencia/idempotencia, identidad, catálogos reales/sintéticos, cálculo completo y parcial, interfaz integrada, empaquetado/arranque y backup/restore. Revisión independiente Astra sobre diff y evidencia. La validación industrial sobre corpus nuevo y la instalación remota se reportan por separado y no se simulan.

## Contrato operativo fijado durante implementación

- Perfil `local|production` mediante `VEXPLORER_ENV`; valores desconocidos no permiten arrancar. Producción requiere `VEXPLORER_DATA_DIR`, `VEXPLORER_USERS_FILE` y `VEXPLORER_ALLOWED_ORIGINS`. Catálogo económico por `VEXPLORER_COST_CATALOG`.
- HTTP Basic sobre TLS, con cuentas individuales y hashes scrypt en configuración de servidor. Todas las rutas y archivos del producto requieren autenticación salvo GET `/health` y `/api/v1/health`. Los usuarios autorizados comparten el espacio del equipo; no hay aislamiento multiempresa ni jerarquía de roles prometidos. La identidad del servidor prevalece sobre `reviewer_name` cliente. Las mutaciones desde navegador validan Origin contra la allowlist configurada, sin confiar en Host/Forwarded suministrados.
- Basic no crea una sesión cookie con logout propio; revocación/rotación se realiza actualizando la configuración de usuarios y reiniciando según guía operativa. El navegador puede cachear credenciales; no se presenta una acción visual como cierre fiable de esa autenticación.
- POST `/api/v1/jobs` persiste antes de ejecutar; GET `/api/v1/jobs/{id}` permite seguimiento explícito mediante polling. Estados: queued, running, succeeded, failed, interrupted. Un executor, un proceso Uvicorn soportado; máximo pendiente configurable (`VEXPLORER_JOB_MAX_PENDING`, 8 por defecto). Al reiniciar, activos anteriores se marcan interrupted y no se repiten llamadas pagadas automáticamente.
- Idempotency-Key está ligada a actor y hash del cuerpo: misma petición recupera el trabajo, mismo identificador con cuerpo distinto da 409. Revisión usa transacción SQLite BEGIN IMMEDIATE para CAS, revisión, evento e idempotencia. El generador de secuencias también se serializa en SQLite, no solo con un lock de proceso.
- El historial de eventos se etiqueta como historial consultable. No se promete streaming de tokens ni eventos durante una llamada remota indivisible.
- Moneda de este incremento: EUR. Precio provisional basado en margen bruto explícito, `coste / (1 - margen/100)`; no es markup ni valor de mercado. Impuestos y aprobación comercial quedan fuera del precio provisional y deben declararse. Catálogo validado/capturado, snapshot conservado en estimación; identidad de estimación incluye alcance y catálogo para no sobrescribir variantes de una misma revisión geométrica.
- Planos: general contiene ancho/profundidad/alto admitidos; componente contiene largo/ancho/espesor y cantidad; despiece identifica ocurrencias. Las cotas conservan dependencias y estado. Una hoja incompleta no se anuncia como lista para fabricación; no se entregan uniones, nesting ni mecanizado certificado.

## Despliegue autorizado
El usuario ha identificado `ssh kripta` y `http://gex-dashboard.hopto.org/` como destino; exige no romper ni alterar las aplicaciones actuales. Se inspeccionará la topología en solo lectura, se elegirá una ruta dedicada y se verificará TLS antes de usar autenticación. El contenedor, puerto loopback y volumen serán propios; cualquier cambio mínimo de proxy tendrá backup, prueba de sintaxis y rollback, sin reiniciar stacks existentes. Esta autorización cambia el pendiente de host desconocido; no autoriza publicar datasets externos.
