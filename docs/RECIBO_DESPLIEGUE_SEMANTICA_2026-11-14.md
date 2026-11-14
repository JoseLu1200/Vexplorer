# Despliegue de semántica e integración en producción

Activado el 2026-11-14 a las 14:03:53 UTC por petición explícita del usuario de integrar, hacer commit/push en main y desplegar.

- Código publicado y desplegado: `fdb94dc8eac266136971aa80dea36a4e9ba05c83`.
- Release: `fdb94dc8eac2-tree906a13d6b72881fc`.
- SHA-256 payload: `906a13d6b72881fc492f992e9dd81c4f2c41c41d1683559357c30e7fa00b95c0`.
- SHA-256 archivo: `134ddc1cf36db0a0c9390dbef7d894400dec7486a97432a766ade754bfa46a4d`.
- Dos builds locales idénticos; manifiesto de 180 archivos verificado en el servidor.
- Release anterior conservado: `d0ea7a85e787-tree518ad7d881403b9b`.

## Verificación

[CI del commit desplegado](https://github.com/JoseLu1200/Vexplorer/actions/runs/43602603431): 1.387 pruebas Python y 253 pruebas frontend correctas; dependencias, compilación, paquete y construcción de imagen correctos.

Ensayo del candidato con datos restaurados en loopback: integridad SQLite, interfaz, API, biblioteca y lectura de tres ejecuciones históricas correctas. Tres trabajos privados conservan HTTP 404 en una sesión pública, igual que el release anterior.

Antes de activar se comprobó que no había trabajos pendientes ni ejecutándose. Se detuvo únicamente `vexplorer.service`, se creó backup quiescente y se restauró a una carpeta nueva; se cambió el enlace `current` y se arrancó el servicio. No se modificaron Caddy, secretos ni configuración de acceso.

- Backup: `/home/kripta/apps/vexplorer/shared/backups/semantic-predeploy-20261114T140353Z.zip`.
- Restauración: `/home/kripta/apps/vexplorer/shared/restores/semantic-predeploy-20261114T140353Z`.
- Recibo operativo: `/home/kripta/apps/vexplorer/shared/semantic-release-20261114T140353Z.json`.

[Producción](https://gex-dashboard.hopto.org/vexplorer/): raíz, health, config, biblioteca, sesión y JavaScript devuelven HTTP 200. Los bytes públicos de `app.js` y `core/scene.js` coinciden con el candidato. Una mutación desde origen ajeno devuelve HTTP 403. Servicio `active` y enlace `current` comprobados después de la activación.

El despliegue no acredita corrección industrial del despiece o montaje. Los límites y resultados del corpus se mantienen en [RESULTADOS_SEMANTICA_V2.md](RESULTADOS_SEMANTICA_V2.md); las referencias privadas y los datasets no forman parte del release.
