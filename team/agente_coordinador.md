# Agente coordinador — demo local

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
