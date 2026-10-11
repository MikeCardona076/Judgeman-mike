# Roadmap

JudgeMan-Mike es **open-core**: el core es MIT y gratis; un Pro futuro añadirá
features avanzadas. Esta página es honesta sobre qué existe hoy y qué está por
llegar.

## Disponible hoy (core, MIT)

- Chat en terminal con tres modos: `diagnose`, `security`, `file`.
- Diagnóstico de solo lectura: puertos, procesos, conexiones, arranque, servicios,
  firewall y `hosts`/proxy.
- Reparación con **catálogo cerrado**, confirmación explícita y **auditoría**.
- Consola Tron a pantalla completa con HUD, gauges y *scroll* por teclado y ratón.
- Monitor web local (`127.0.0.1`) con observación pasiva de archivos.
- Redacción de datos sensibles antes de enviarlos al proveedor.

## Próximamente (Pro)

Estas funciones se marcarán como **"no disponible en esta versión"** hasta que
existan de verdad. No hay *gating* falso: lo que no está, se dice.

- **Monitor continuo con alertas**: vigilancia permanente y notificaciones ante
  cambios relevantes.
- **Historial y línea de tiempo**: ver la evolución de puertos, servicios y
  conexiones, con exportación.
- **Auditoría firmada**: entradas verificables criptográficamente.
- **Catálogo ampliado**: más acciones, con *rollback* y programación.
- **Multi-máquina y panel**: gestionar varios equipos desde un solo lugar.
- **Modelo hospedado**: usar JudgeMan-Mike sin configurar un proveedor propio.
- **Licencias y actualizaciones**: clave de licencia y auto-actualización.
- **SSO / RBAC**: control de acceso para equipos.

En esta versión, el comando `/pro` describe estas líneas y las marca como no
disponibles.

## Principios

- El free debe ser **útil por sí solo** y funcionar en local.
- El Pro se apoya en feature flags sobre el mismo core.
- Nada se anuncia como disponible hasta que lo esté.

## Cómo influir en el roadmap

Abre un *issue* con la plantilla de propuesta de funcionalidad
(`.github/ISSUE_TEMPLATE/feature_request.md`). Los casos de uso concretos pesan
más que las listas de deseos.
