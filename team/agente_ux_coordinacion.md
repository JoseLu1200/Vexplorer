# Coordinación de revisión UX — 2026-11-14

## Identidad y autorización

Agente raíz de esta sesión. El usuario ha pedido explícitamente un swarm de agentes para probar toda la aplicación, corregir errores funcionales, scroll y diseño, instalar skills relevantes y levantar/desplegar servidor y web con comprobación visual Playwright. Esta identidad es de agente, no una identidad humana inferida.

## Alcance y reservas

- Coordinación: este registro, plan e informe de verificación UX, artefactos QA en `.runtime/ui-review-maisa/`.
- `layout_scroll`: `frontend/styles.css`, `frontend/index.html`.
- `functional_ui`: `frontend/app.js`, helpers y tests funcionales necesarios.
- `scene_viewer`: `frontend/components/SceneViewer.js` y sus pruebas.
- `browser_qa`: pruebas independientes del navegador, sin cambios de producto.
- `docs_audit`: lectura de todos los Markdown propios y auditoría documental.
- `design_skills`: investigación e instalación selectiva de skills externas.
- `deploy_prepare`: inspección del despliegue y ejecución posterior a verificación integrada.
- Se preservan cambios locales previos, incluidos los de `team/agente_integracion_integral.md`. No se modifican contratos ni se atribuyen a esta sesión cambios anteriores.

## Evidencia inicial

- `npm test --prefix frontend`: 147 aprobadas antes de las correcciones.
- El puerto 8765 sirve una versión anterior. Instancia de esta revisión: `http://127.0.0.1:8771`, almacenamiento aislado `.runtime/ui-review-maisa/`.
- Carga real de `mesa_demo_001.dxf` por navegador en modo geometría: revisión 1, dos tipos de componentes propuestos.
- 390×844: piezas sobrepasa su contenedor y se solapa 23 px con inspector; 980×800: aproximadamente 14 px.
- Inspección de código: visor 3D escucha resize de ventana, no cambios de ancho por contraer raíl.
- Colores/radios iniciales proceden de trace-pay; tipografía distinta y exceso de pastillas/texto pendiente de corrección.

## Estado

### Ampliación explícita del usuario: acceso sin contraseña

El usuario solicita desactivar usuario/contraseña en VPS y localhost y dejar el servidor local disponible. Coordinación asume `backend/app/main.py`, pruebas de autenticación, configuración/documentación de despliegue y etiqueta de sesión. Se conserva el modo production, guard de origen y límites; la desactivación será explícita mediante configuración. No se cambian contratos ni datos de trabajo.

Producto corregido y publicado; limpieza de accesos y procesos temporales completada. Revisor independiente: SHIP. Evidencia final en `docs/VERIFICACION_UX_2026-11-14.md`.

## Verificación y despliegue final

- Coordinación ejecutó 596 pruebas Python y, sobre frontend final, 162 pruebas JavaScript; todas aprobadas. Backend runtime sin cambios durante reparación UX.
- Navegador local: carga/revisión de dos mesas, coste parcial, biblioteca, similitud, tema, 3D y responsive; QA independiente amplió a piezas incompletas/ambiguas, PDF, histórico, descargas y teclado.
- Lighthouse local final: 100 accesibilidad, 41 comprobaciones aprobadas y cero fallos; no equivale a certificación de accesibilidad completa.
- Archivo desplegado: `a61f97a89a86-treec58bbe42140dd03c`, SHA-256 `ed367c28920af79111350f68ae72580bbf975c7b09b09045b621cc6f988b05b6`.
- Playwright propio contra candidato y URL pública: restauración R2, fuentes, hashes, paneles a 1440/1100/390, modal y persistencia de tema. Cero errores JS/HTTP en ambos recorridos.
- Carga de DXF remoto sobre restore aislado: documentos201/job202, propuesta R1 completa con geometría solamente. El intento inicial por túnel HTTP recibió403 correctamente; el ensayo final usa TLS efímero y origen HTTPS específico sin modificar protección productiva.
- Publicado en `https://gex-dashboard.hopto.org/vexplorer/`; root verificó symlink, servicio active y health200. Backup y release previo conservados. Cambios de esta sesión siguen en árbol local sin commit; artefacto runtime los incluye por hash.
- No se repitieron evaluación industrial, inferencia live, embeddings o conversión DWG como parte de esta reparación visual/funcional.
- QA temporal eliminado, credencial revocada401 y users original preservado por igualdad de hash. Túnel/candidato cerrados y secretos temporales retirados. Servicio productivo active, health200 y acceso anónimo401 después de la limpieza.

### Cierre: acceso público y localhost

- Configuración explícita `VEXPLORER_AUTH_ENABLED=false`; production mantiene guard de origen, límites y jobs. Valores inválidos fallan al arrancar; autenticación sigue activa por defecto para otros despliegues.
- VPS activo: `/home/kripta/apps/vexplorer/releases/public-access-20261114-071821`; servicio active/enabled. Config anterior y release anterior conservados. Archivo de usuarios fuera de la configuración activa; no se han borrado datos ni backups.
- Local reiniciado en `http://localhost:8771/`, loopback `127.0.0.1:8771`, datos existentes de `.runtime/ui-review-maisa`. Arranque reproducible: `.runtime/public-access/start-local.ps1`.
- HTTP anónimo 200 para raíz, sesión y config en local y VPS, sin cabecera WWW-Authenticate. Playwright con contextos sin credenciales: ambas interfaces visibles, sesión anónima y cero errores JS.
- Pruebas: 11 de autenticación pasan; 162 frontend pasan. Suite Python: 605 aprobadas y `test_general_autonomous_semantic_repair_preserves_p1_and_reviews_p2` falló con MemoryError al leer evidencia visual. Repetición aislada: 1 aprobada en 2,21 s. No se declara suite completa verde. `git diff --check` correcto.
