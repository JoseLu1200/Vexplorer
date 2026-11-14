# PR2: revisión, correcciones e integración

**Objetivo:** integrar la PR2 de embeddings y precedentes conservando el sistema vigente y corrigiendo fallos reproducidos por el swarm GPT-6.1 Sol solicitado por el usuario.

**Arquitectura:** se mantienen contratos Pydantic, geometría determinista, sugerencias como hipótesis, comparación de espacios compatibles y abstención explícita. La integración local incorpora la unión aditiva de contratos previamente acordada por A/B y comunicada a C. Se trabaja desde la PR en un worktree aislado; el checkout raíz conserva cambios locales de otras sesiones.

**Especificación:** alcance existente de PR2 y `docs/BRAINSTORMING_EMBEDDINGS.md`; correcciones de integración, sin ampliar a proveedores de imagen ni nuevos roles de autorización.

## Tareas y responsables

- [x] Confirmar base, cabecera, CI y ausencia de conflictos textuales con `main`.
- [x] Revisar con cuatro agentes independientes: similitud, precedentes, seguridad e interfaz.
- [x] Similitud: exportar calibración en formato utilizable por `thresholds.py`, reutilizar coseno estable y validar matrices; probar round-trip y extremos numéricos.
- [x] Validador: evitar inferir apoyos de piezas sin relación y tratar catálogo no confirmado como provisional; verificar conexión con un resultado real antes de afirmar integración.
- [x] Precedentes: conservar cantidades desconocidas fuera de totales de corte, recuperar suficientes comparables válidos y rechazar/normalizar pesos cuyo total desborda; pruebas de regresión independientes.
- [x] Seguridad: invalidar caché de biblioteca antes de publicar una rotación de espacio y compartir exclusión de mantenimiento con regeneración; probar deriva con mismo modelo, orden ante fallo y regeneración posterior.
- [x] Interfaz: corregir regresiones comprobadas en flujo de duplicados/explicaciones, preservando el recorrido vigente.
- [ ] Coordinación: revisar diffs, ejecutar suite Python, frontend y comprobaciones de empaquetado; registrar límites reales, actualizar PR y esperar CI antes del merge autorizado.

## Decisiones de revisión

Se conserva el fallback geométrico documentado del híbrido, exponiendo pesos efectivos. MAD cero sigue como abstención estadística; no se inventa dispersión. Los lotes siguen siendo estimaciones por superficie, no nesting. Imagen, recomendaciones de pesos y herrajes no se presentan como capacidades validadas con datos reales. La rotación afecta a la biblioteca, no al histórico económico separado. Los bloqueos de mantenimiento siguen limitados al proceso.

## Propiedad

Cada agente mantiene únicamente su registro `team/agente_pr2_*.md`. Similitud posee calibrador, matemáticas y plausibilidad; precedentes posee piezas, lotes, analogía e híbrido; seguridad posee API de mantenimiento, espacio, protocolo de regeneración y el método de invalidación del repositorio; interfaz posee frontend. Coordinación posee cambios compartidos de `main.py` y documentación de entrega. Commits y merge centralizados.
