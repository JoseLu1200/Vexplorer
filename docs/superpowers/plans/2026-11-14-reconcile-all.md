# Reconciliación completa de ramas

> Ejecución nativa con superpowers:executing-plans y revisión final independiente.

**Objetivo:** integrar en main todos los desarrollos existentes, incluidos UX sin commit, conservando mejoras actuales y evidencia.
**Arquitectura:** fusiones por ascendencia y equivalencia de parches; snapshots con índice temporal para trabajo sin commit; resolución explícita de solapes.
**Spec:** autorización del usuario «adelante con todo ello» y registro de equipo de integración semántica.

## Restricciones y focos de revisión

No alterar índices ni archivos de los worktrees de origen; no importar secretos/datos ignorados. No reintroducir implementaciones antiguas ni perder el explorador al incorporar UX. Conservar distinción confirmado/hipótesis, referencias de evidencia, autenticación configurable y límites. Ramas activas requieren verificar cambios posteriores al snapshot. Main y remoto solo se actualizan con el resultado validado.

## Pasos

- [ ] Inventariar refs y trabajo sin commit; fijar snapshots y hashes.
- [ ] Incorporar transcript, reconstrucción y CAD; resolver contratos y endpoints conservando capacidades.
- [ ] Incorporar snapshot UX y conciliar frontend, acceso y empaquetado.
- [ ] Reconciliar ramas históricas mediante equivalencia y comprobación de sus cambios exclusivos; documentar decisiones.
- [ ] Ejecutar Python/JS, pruebas de navegador y revisión independiente; corregir regresiones.
- [ ] Revisar de nuevo orígenes, actualizar documentación, fusionar/publicar main y verificar CI.
