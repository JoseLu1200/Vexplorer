# Integración final en main

Agente IA de integración de esta sesión. Encargo explícito del usuario: guardar los cambios pendientes, integrar todas las ramas en main, resolver duplicados conservando la versión más completa y hacer push.

Alcance: reconciliación Git, resolución de conflictos, pruebas y publicación en origin/main. Se utiliza el worktree existente semantic-main; las fuentes se conservan mediante commits. No se despliegan servicios.

Inventario inicial: main local 0d9dee7, origin/main c66f93b, rama remota embeddings e95f6bd. Hay cambios pendientes en la raíz y similarity-public. Reconstrucción tiene cambios ya capturados por snapshots anteriores y algunos detalles adicionales. PoC aporta evaluación y semántica pendientes.

Solapes: CAD y protecciones públicas prevalecen sobre sus versiones antiguas; se combinan con montaje, similitud técnica, recuperación de trabajos y precedentes. Los contratos existentes se integran sin redefinir su arquitectura.

Estado: integración y comprobaciones en curso. Los resultados se registrarán después de ejecutarlos.

Cierre de integración: todas las ramas locales guardadas se han reconciliado; se conservan CAD, montaje por instancia, recuperación, similitud técnica y embeddings. Los merges concurrentes de montaje/PR2 contienen versiones ya incorporadas; prevalece el árbol integrado con sus correcciones posteriores.

Correcciones: límite de instancias provisionales de montaje; revisión geométrica sin exigir material/acabado desconocidos; hashes de fixtures LF/CRLF; corpus con serialización histórica explícita independiente del sistema; pruebas actualizadas a contratos compactos y contabilidad de evidencia.

Verificación observada antes del push: frontend 249/249; suite Python 1359 correctas y un fallo después corregido; 28 pruebas específicas y 63 de recuperación/evaluación correctas; pip check y compileall correctos; wheel construido. Segunda suite completa en curso, seguida de GitHub Actions para el SHA publicado. El arranque de UI local muestra Servicio disponible y cero errores de consola. Las ediciones concurrentes posteriores en otros worktrees no forman parte de esta instantánea hasta revisarlas.
