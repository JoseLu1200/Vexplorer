# Cierre de producción CAD pública

Encargo explícito: acabar una versión operativa de producción conservando trabajo existente. El usuario confirmó acceso público sin login. Base: cad-completion 8e5f584, con origin/main 4504adb incorporado. Se integra además la UX ya desplegada desde una copia de su checkout, sin modificar ese checkout.

- [ ] Recuperación acotada en un solo job hasta P3; fallos deterministas no repiten llamadas al modelo.
- [ ] Reintento durable tras reinicio, idempotencia y límites persistentes del acceso público.
- [ ] Mantener pública la entrada CAD; aislar histórico empresarial y mutaciones globales del catálogo.
- [ ] Conservar UX desplegada, CAD por pieza, explicación y descarga de revisiones exactas.
- [ ] Verificar suite, empaquetado por commit exacto y CI.
- [ ] Ejecutar un DXF complejo desde upload hasta planos con modelos reales en un único job.
- [ ] Ensayar release aislado sobre backup restaurado y configuración pública equivalente.
- [ ] Activar únicamente Vexplorer con rollback disponible; comprobar dominio, reinicio, persistencia y restauración.
- [ ] Programar copias quiescentes verificadas y dejar evidencia, commits y main actualizados.

No se altera el proxy ni los servicios vecinos. No se cambian contraseñas ni se vuelve a exigir login. Límites iniciales de uso live: 10 intentos globales/día y 3 por cliente/día; la idempotencia no consume otro intento. Los resultados constructivos siguen distinguiendo observación, deducción y estimación; disponibilidad productiva no se presenta como precisión industrial universal.
