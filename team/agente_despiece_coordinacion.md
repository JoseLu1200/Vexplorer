# Coordinación de mejora del despiece

Identidad: agente IA `/root`, coordinación del swarm autorizado por el usuario. Encargo vigente: corregir generación, cotas y recuperación con objetivos de 90 % verificados en evaluación independiente.

Propiedad: documentación de diseño/plan, integración, verificación y despliegue. No editar bajo registros personales ajenos. Propiedad de runtime disjunta según `docs/superpowers/plans/2026-11-14-despiece-cobertura-90.md`.

Base de trabajo exclusiva: `.worktrees/similarity-public`, conservando cambios V4 ya publicados. No se toca el checkout raíz concurrente ni sus datos. Biblioteca pública sigue reservada a muebles reales revisados.

Estado: diagnóstico y definición de métricas en curso; motor/API/UI/evaluación delegados a agentes Sol existentes y revisión a Astra. Sin nuevos despliegues ni nuevas llamadas live de evaluación por ahora.

Continuación: root asume evaluación y regresión de concurrencia tras agotarse la cuota de agentes. Se cierran cantidades desconocidas, autoridad de cantidad en herrajes, fase obligatoria y terminal interrupted antes del nuevo ensayo.

## Continuación 2026-11-15: preservar portal y landing

El usuario ordena continuar sin romper el trabajo incorporado en 8022ac6 y a467280. La integración pasa a la worktree aislada `.worktrees/cutlist-design-integration`, rama `fix/cutlist-preserve-design-20261115`, desde origin/main a467280. Esto reemplaza la base exclusiva antigua para integración; similarity-public permanece conservada con sus cambios y backup `.runtime/preserve-r13-before-main-20261115`. No se sobrescribe el checkout raíz ni se modifica trabajo personal ajeno. Portal, landing, logos, QR, aristas marrones, siluetas y arranque quedan protegidos mediante manifiesto de hashes y revisión de cambios. Se conserva también EmbeddingGemma 2 y la recuperación durable de main. Evaluaciones sin API mediante Codex; R13 anterior interrumpida, no acreditada como cohorte completa.

Integración por lotes: se trasladaron 21 archivos de bajo solape verificando que el blob base f32021d coincida con a467280; receipt `.runtime/low-overlap-transfer.json`. El generador PlankAssembly actual de main ya corrige vistas superpuestas mediante normalización de origen y se conserva, sin copiar la variante antigua. Se añaden jsonschema/referencing solo a extras test/dev y exclusiones de dependencias/buildinfo locales de diseño en .gitignore. Focal root56passed29.90s; geometría63passed17.12s. La ejecución baseline general se interrumpió y no se acredita como baseline limpio; no se detuvieron procesos de pruebas ajenos.

## Cierre solicitado por el usuario

El usuario solicita terminar aunque no se alcancen todos los requisitos, integrar mejoras compatibles en main, publicar y dejar CI verde. Se aplaza R14: no se acredita el objetivo global de 90 % ni una nueva evaluación de modelos. R12 obtuvo 14/14 piezas y 42/42 cotas en un caso, pero falló la puerta de entrega conjunta; R13 quedó interrumpida y no es combinable. El holdout permanece sin abrir. No se usó la API agotada para estas pruebas.

Preservación visual comprobada en escritorio y móvil: QR decodificado al portal publicado, aristas marrones, siluetas del mapa y arranque. De 197 archivos protegidos, 194 son idénticos; excepciones justificadas: vite.config.ts usa directorio relativo equivalente para loadEnv, build.html se regenera mediante strip.py y general.gen.ts se regenera desde Pydantic para el soporte de proyecciones compartidas. Portal typecheck/build/build:single y landing build pasan; frontend legacy 283 pruebas y 6 de navegador pasan. Astra aprueba extracción, frontend legacy y servicio; revisión final del despiece en curso.

Pendientes explícitos del portal nuevo: conectar acciones retry/resume ya presentes en el cliente; conservar fase, revisión y checkpoint en el diagnóstico; no atribuir todos los estados sin propuesta a falta de modelo; propagar el aviso global provisional_not_manufacturing a MesaGeneral. No se rediseñó el portal para resolverlos durante el cierre. El mapa publicado observado aún permite el corpus geométrico PlankAssembly; no se redesplegó ni se importaron muebles sintéticos a Biblioteca. build.html es un fragmento que necesita un contenedor UTF-8; dist/index.html es la salida standalone.

Cierre de revisión: Astra SHIP en extracción, contratos/despiece, servicio y frontend. Se integró origin/main 9656dd5 mediante merge limpio, incluyendo PR7 y su CI verde; no se restauran ramas antiguas. Auditoría de ramas: PR3/PR5 ya integradas y endurecidas; PR4 sustituida por la evaluación actual; transcript-completion ya incorporada y evolucionada. No hay PR abiertas ni mejoras adicionales pendientes de merge identificadas. Suite global anterior detenida para verificar la combinación final, sin acreditarla como PASS.
