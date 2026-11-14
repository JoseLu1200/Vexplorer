# Agente coordinador — demo local

## Entrada corregida por el usuario: piezas separadas (2026-11-14)

El usuario exige partir únicamente de vistas del despiece y confirma DXF 2D con piezas separadas. La auditoría baseline queda conservada en `59623ef`; producto auditado `dab7ce5`. Nuevo trabajo en `feat/parts-integration` y worktrees `feat/parts-{geometry,backend,frontend,evaluation}`. Diseño y plan en `docs/superpowers/{specs,plans}/2026-11-14-piezas-separadas*`.

A/B han acordado por mensajes el contrato aditivo 0.4 antes de implementar, B lo registra y es escritor único. C/D reciben shape para trabajar en paralelo. A posee ingesta/extracción/parts/reconstrucción; B contratos/API/harness/repositorio/revisión/descriptor; C frontend; D fixtures/referencia privada/aceptación; root documentación/integración/navegador; Astra revisión final. Hallazgos baseline no se borran: cada corrección tendrá verificación posterior identificada.

Estado: contrato `86fe0c1` + `6a82a8e`, regresiones OCS/Z/DIMLFAC `854d003` y fixtures `4ae1cee`/`7d3376c`/`1c399af` integrados. Auditoría baseline aceptada por Astra tras reforzar evidencia en `20540ff` + `0a8161a`. A/B revisan asignación por ejemplares: un tipo observado puede servir a varios roles, con cantidades disjuntas y sin duplicación. No se ha verificado aún el nuevo flujo completo.

## Auditoría de uso solicitada el 2026-11-14

Base congelada: main `dab7ce5`. El usuario pide probar API y navegador y documentar capacidades, fallos y pendientes. Rama de documentación `audit/app-20261114`; no se modifica código de producto durante la auditoría.

- Coordinador: instancia aislada, navegador, informe `docs/AUDITORIA_APP_2026-11-14.md`, evidencia resumida y enlaces README.
- D: pruebas HTTP de aceptación y negativos, script reproducible `tools/audit_api.py`, evidencia `docs/auditoria/2026-11-14/api.json` y su registro; rama propia desde baseline.
- A: revisión de implementación y contraejemplos geométricos, solo lectura/scratch ignorado, sin referencias reservadas en runtime.
- C: revisión de comportamiento de interfaz/contratos y comprobaciones pendientes, solo lectura/scratch; no alterar la sesión del navegador del coordinador.
- Astra: contraste final entre informe y evidencia, solo lectura.

Los casos de prueba usarán almacenamiento separado `.runtime/audit-20261114/`; no se alterarán revisiones o biblioteca de la demo existente. El informe distinguirá PASS, FAIL, limitación prevista, no implementado y no verificado. Hallazgos nuevos permanecen documentados para reproducirlos; no se incorporan correcciones silenciosas.

## Ampliación autorizada: plano, reconstrucción y similitud (2026-11-13)

Solicitud posterior del usuario: centrar el trabajo en el visualizador de planos y vistas, cotas, piezas, explicación del harness, reconstrucción y embeddings coherentes para agrupar muebles. Rama de integración `demo/drawing-workbench`, base integrada `40e5e40`. Se conserva la revisión humana y la estimación existentes.

Propiedad para esta fase:
- A: ingesta, geometria, `servicios/decomposition.py`, nuevo `servicios/reconstruction.py`, pruebas geométricas y de reconstrucción; su registro. No escribe contratos.
- B: contratos (único escritor), API/main, harness, repositorio y similitud/embeddings; pruebas backend salvo las reservadas a A; su registro.
- C: frontend completo, dependencias JS declaradas y pruebas; su registro.
- D: fixtures propios, generador, referencias reservadas y `tests/test_demo*`; su registro.
- Coordinador: documentación de entrega, índice de equipo, integración, comprobación navegador y restricciones reproducibles. GPT-6 Astra revisa en lectura el resultado integrado.

Secuencia: A/B acuerdan y registran primero contratos aditivos de dibujo enriquecido, escena y descriptor/similitud, avisan C/D; paralelizar implementación y pruebas en ramas aisladas; integrar; recorrer plano/revisión/3D/agrupación en navegador y comprobar proveedor real si está configurado; corregir hallazgos Astra; documentar límites.

Criterios: cotas con anclajes y unidades; navegación/pan/zoom; selección bidireccional pieza/evidencia; explicaciones verificables con fuentes y premisas; sólidos únicamente con dimensiones suficientes y colocación justificada, sin completar incógnitas; descriptor semántico versionado, embeddings reales identificados con modelo y caché, similitud geométrica separada; grupos reproducibles sobre entradas propias. No publicar PlankAssembly ni atribuir precisión industrial a la reconstrucción.

Estado: en curso; capacidades de esta ampliación todavía no verificadas.

Transferencia adicional por petición de reutilización open source: coordinador asume exclusivamente `backend/app/salida/drawing_preview.py` y `backend/tests/test_drawing_preview.py`, nuevos archivos de representación SVG con ezdxf. B mantiene la ruta API, C integra la imagen y A mantiene el ledger geométrico. Avisados A/B/C antes de código. El SVG no constituye evidencia métrica ni aporta identidades de piezas; no se alinea con el ledger sin transformación demostrada.

Bloque de render: SVGBackend integrado con presupuesto de entidades/recursión, tiempo cooperativo y tamaño; sin adjuntos externos ni contenido activo. Pruebas propias primero rojas por módulo ausente, luego tres verdes sobre curvas/bloques/texto/cotas, ciclo recursivo y DXF inválido. Pillow 12.3.0 declarada por B e instalada desde pyproject; versión registrada en requirements-demo. Endpoint/UI aún pendientes de integración. Investigación open source documentada en docs/OPEN_SOURCE.md.

Push autorizado por solicitud posterior del usuario: `git push -u origin demo/drawing-workbench`, observado correcto hasta `8eb85ab`. La ampliación posterior continúa en desarrollo y se subirá tras verificación; sin despliegue.

## Cierre de ampliación (2026-11-14)

- Integrados A/B/C/D en `demo/drawing-workbench`: cotas/textos anclados, CAD original SVG, preview sin despiece, reconstrucción por ocurrencias, explicaciones, biblioteca local, embeddings reales y grupos geométricos/semánticos. Three.js local con licencia y dependencias fijadas.
- Navegador real: carga propia, selección de evidencia, revisión 2, largos 864 mm, CAD original, seis tableros WebGL, restauración, consultas y agrupación de biblioteca. Corregidos asset faltante, mínimo/centro de cajas, bucle de resize, respuestas y errores async obsoletos.
- Proveedor embeddings real: tres llamadas de generación `text-embedding-3-small` a 256 dimensiones; control trasladado y repetición reutilizan caché. Los cuatro ejemplos cercanos forman un grupo; no se afirma calidad empresarial de clustering.
- Verificación integrada: 119 pruebas Python y 46 JavaScript, compileall correcto y pip check sin incompatibilidades. Aviso conocido TestClient/httpx. Pruebas focalizadas adicionales cubren `explicar_pieza`, argumentos malformados, IDs visibles al modelo y agrupación semántica compatible.
- Astra detectó y se corrigieron agrupación semántica inicialmente ausente, carreras de respuestas antiguas, herramienta explicativa sin handler y referencias de propuestas ausentes del contexto. Dictamen final: SHIP sobre código 2f6bb9e y documentación actual, con 119 pruebas Python y 46 JavaScript verificadas independientemente; sin hallazgos críticos/importantes abiertos.
- El usuario solicitó explícitamente varias veces merge y push de todo a main. Se realizará merge sin force-push, conservando commits de agentes. No se despliega ni se publican datasets externos; `.env`, runtime, SQLite, caches y worktrees permanecen ignorados.

Identidad: agente coordinador de IA; no representa a una persona. Autorización: solicitud explícita del usuario del 2026-11-13.

## Alcance y propiedad
- Coordinador: integración, README.md, .gitignore, docs/DEMO_IMPLEMENTACION.md, docs/VERIFICACION_DEMO.md y este archivo.
- A: backend/app/ingesta/, backend/app/geometria/, backend/tests/test_geometry.py, team/agente_geometria.md.
- B: backend/app/contratos/, api/, agente/, herramientas/, validador/, salida/, servicios/, backend/app/main.py y __init__.py; pyproject.toml, .env.example; backend/tests/test_backend*.py; team/agente_backend.md. Único escritor de contratos.
- C: frontend/ y team/agente_frontend.md.
- D: data/planos_demo/, evaluation/, tools/build_demo_fixture.py, tests/test_demo*.py, team/agente_evaluacion.md.
- No hay reservas personales previas; cada agente crea y mantiene su propio registro.

## Plan autorizado
1. Partir de main actualizado; baseline: 13 tests pasan, commit c09a6f9.
2. A/B acuerdan contrato 0.2 de demo y comunican a C antes de código contractual.
3. D crea fixture propio de estantería montada y variante incompleta; referencia reservada separada.
4. A implementa geometría determinista sin leer referencia; B implementa API, revisiones, herramientas, live configurable, comparables y estimación sintética.
5. C integra plano, evidencia, propuestas, revisión, histórico, estimación, exportación y traza.
6. Coordinador integra commits, ejecuta suite y recorrido navegador; GPT-6 Astra revisa diff final; corregir y repetir checks afectados.

## Decisiones
- Familia: estantería rectangular de tableros. UX español, servidor local FastAPI sirve JS/HTML para arranque único.
- geometry_only siempre disponible; live requiere proveedor real configurado. recorded_replay no se habilita sin grabación real.
- PlankAssembly permanece fuera del runtime y sin publicar; adaptación futura acotada se documentará.
- Se siguen la especificación del usuario y PLAN.md; decisiones rutinarias autónomas según autorización expresa.

## Estado
Completado: demo local integrada y verificada; aceptación final GPT-6 Astra SHIP. El historial de bloques siguiente conserva el estado que tenía cada entrega en su momento.

## Integración parcial
- Contratos 3346537, fixture c3c5e85 y geometría 7b46a2a/7ce5112/1cd65bc integrados.
- Entorno virtual nuevo instalado con .venv/Scripts/python.exe -m pip install -e '.[test]'. Suite integrada: 30 passed antes del último filtro de cotas; pendiente nueva ejecución con regresiones.
- Coordinador mantiene además requirements-demo.txt como restricciones del entorno comprobado (Python 3.14 Windows), sin rutas locales ni secretos.


## Aceptación en curso
- Backend df184a9/a7ce394/d9d6c7e y frontend hasta e360efd integrados. Suite actual52Python/28JS, navegador real8765 probado; smoke live real con gpt-6.1-sol.
- Ampliación A autorizada: tools/prepare_evaluation.py y tests/test_prepare_evaluation.py para hallazgos del usuario; fix8501ded integrado, sin solapes.
- Astra revisa código integrado; cierre pendiente de dictamen y regresiones finales.



## Transferencias durante revisión
- Coordinador mantiene team/README.md como índice común actualizado; los registros propios permanecen bajo autoría de cada agente.
- A asume temporalmente backend/app/servicios/decomposition.py y backend/tests/test_decomposition_geometry.py para el gate rectangular encontrado por Astra; B avisado para evitar solape.
- B corrige exclusividad de escenarios en revisión y cálculo parcial; C restaura sesiones/trazas y limpia estimaciones caducadas.


## Cierre final
- Implementación integrada desde main c09a6f9 en demo/first-executable, con commits propios de A/B/C/D y coordinación. Sin push, VPS ni publicación de datos externos.
- Acuerdo A/B0.2 y aviso C registrados; cada worktree conserva su alcance.
- Verificación final: 55 pruebas Python, 35 JavaScript; compileall correcto, pip check sin incompatibilidades. Advertencia TestClient/httpx y whitespace generado documentados.
- Navegador real: geometry_only, live GPT-6.1 Sol con herramientas reales, selección de evidencia, revisiones2/3, invalidación y recálculo, comparables, ficha JSON, traza y variante incompleta. Decisiones de ensayo atribuidas al agente, no a un técnico humano.
- Revisor final GPT-6 Astra: SHIP tras correcciones0dcd5fe/5c340a7. No quedan fallos importantes o críticos; quedan los límites declarados en README.
- Servicio local activo en http://127.0.0.1:8765. Comandos reproducibles y guion en README; evidencia detallada en docs/VERIFICACION_DEMO.md.

## Hito de piezas separadas — 14/11/2026

- Agente coordinador: integración en `feat/parts-integration` desde `dab7ce5`. A/B/C/D trabajan en ramas/worktrees propios; B conserva propiedad única de contratos Pydantic. Se acuerda contrato 0.4 antes de implementar y se comunica a frontend/evaluación.
- Entrada autorizada: DXF 2D de piezas separadas. Fixture propio, nueve vistas de tres observaciones y seis ejemplares; referencia reservada al evaluador, fuera del runtime. Sin datos ni derivados de PlankAssembly publicados.
- Integrados extracción, revisión versionada, recálculo por piezas efectivas, escena, descriptor v2, herramientas live nativas y UI de vistas/cotas/confirmaciones. Se mantienen observaciones e historial inmutables.
- Auditoría baseline conservada; nuevas pruebas HTTP y navegador documentan lo implementado y las correcciones, sin presentar simulaciones como proveedor real. Una modificación de cantidad humana 2→3 produce revisión4, siete objetos y 140,80 EUR sintéticos.
- Evidencia y límites: `docs/VERIFICACION_PIEZAS_SEPARADAS.md` y `docs/auditoria/2026-11-14/parts-*`. Astra realiza revisión final del diff y reproduce los defectos corregidos.
- La autorización de merge/push a main sigue vigente. No se solicita otra confirmación; el cierre requiere pruebas y revisión correctas. No se despliega al VPS.
- Siguiente solicitud activa del usuario: acabar este hito y ampliar a planta/alzado/perfil del conjunto, caso mesa rectangular, propuesta generativa acotada, planos derivados y por pieza acotados y costes explicados. No se atribuye esa ampliación al hito 0.4.
- Cierre: agente GPT-6 Astra emite SHIP sobre `cbc549a`; suites 188 Python/66 JS, auditoría HTTP 58/58 y proveedor real correctos. Merge fast-forward y push a main completados en `06cf51e`; `main...origin/main` devuelve `0 0`.

## Mesa y adaptación CAD/harness — integración en curso

- Rama `feat/mounted-table-drawings` desde main `164356b`. Contrato A/B 0.5 y diseño/plan registrados antes del código. Se conserva la demo publicada en un checkout y servidor separado.
- Integrados programa generativo acotado, revisión, ledger, planos generales/por pieza/despiece, SVG/DXF, escena, costes por componentes, CSV genérico y descriptor v3. Los agentes no leen la referencia privada durante la inferencia.
- Carga, revisión, dibujos, 3D y coste parcial recorridos en navegador real. Corregidos solape del botón Abrir, solicitud de incógnitas no bloqueantes y ausencia de zoom en planos derivados; la legibilidad se sigue revisando.
- Primera llamada real falló por un JSON Schema estricto incompatible con Responses. B corrigió el esquema generado desde Pydantic; segunda llamada `gpt-6.1-sol` entregó bindings y componentes propios y llegó a revisión 2 completada. Embedding real generado y reutilizado desde caché. Evidencia temporal `.runtime/table-live-schema-fixed.json`; auditoría reproducible `tools/audit_table_live.py`, propiedad del coordinador.
- Usuario amplió la integración a dos bloques de Pablo en `mejoras/cad-harness`. Revisión aislada confirmó 140/46 y 166/46 pruebas respectivamente, pero reprodujo defectos de espesores duplicados, cantos duplicados, límites de bloques, planos Z, Sistema 32 y contexto truncado. Se adaptan funciones compatibles, sin reemplazar los contratos 0.5 ni portar esos defectos.
- A mantiene ingesta/geometría y validación del programa; B mantiene contratos/API/harness. Apoyos delegados: exportador de corte y costes bajo B, renderer de planos bajo A, plausibilidad de taller bajo B. Cada archivo tiene un único escritor; root integra commits y conserva la atribución de origen en documentación.
- Revisión Astra sustantiva en curso: corrigiendo restricciones geométricas, evidencia derivada, IDs de revisión disjuntos, referencias de planos, explicación de valores humanos y tarifa fija de catálogo. La aceptación de contrato y el SHIP 0.4 no equivalen a SHIP de esta ampliación.
- La autorización de merge/push main persiste; se ejecutará después de la verificación integrada. No hay despliegue al VPS ni publicación de datos externos.

### Cierre técnico de mesa/CAD

- Primer merge/push incremental a main confirmado en `23b8e01`, con 287 Python/81 JS y SHIP incremental.
- Código final `5241a86`: 313 Python/82 JS, 26 comprobaciones HTTP del flujo, 20 peticiones HTTP live correctas, compileall/pip check/diff-check correctos. GPT-6 Astra emite SHIP final sin hallazgos críticos o importantes reproducibles.
- Visión nativa real verificada: el modelo solicitó FRONT, recibió PNG con cinco marcas y su hash; después propuso y la revisión 2 quedó completed. OFF por defecto; ON exige al menos una inspección y permite tres intentos. Acuerdo A/B explícito registrado por B.
- Navegador final abrió el run live, mostró cotas y componentes y amplió el SVG con nitidez; consola sin errores/avisos en esa sesión. C verificó además zoom/pan/Escape, subida/revisión/coste/3D y responsive. Evidencia en `docs/VERIFICACION_MESA_CAD_2026-11-14.md` y `docs/auditoria/2026-11-14/table-*`.
- Adaptación selectiva de ambos bloques de Pablo integrada. Quedan fuera HATCH, bulges, paperspace y ARC OCS negativo; costes sintéticos, reconstrucción esquemática y perfil acotado se mantienen explícitos. No se afirma automatización general ni precisión empresarial.
- Merge fast-forward y push final confirmados: `23b8e01..443e9f1` en main. El checkout de demostración sirve esa versión en `http://127.0.0.1:8765`, con visión desactivada por defecto y el run live revisado restaurado. Se verificaron health/config/resultado y apertura en navegador. Los servidores temporales de ensayo se cerraron; no se borraron sus datos.
