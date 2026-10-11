# Diagnóstico (solo lectura)

`judgman/core/diagnostics.py` reúne la evidencia del equipo sin modificar nada.
Es la base de los modos `diagnose` y `security`, y de los comandos que muestran
datos crudos.

## Qué se recoge

| Sección | Fuente | Comando del chat |
|---------|--------|------------------|
| Puertos a la escucha | `psutil.net_connections` | `/ports`, `/port <n>` |
| Procesos con más carga | `psutil.process_iter` | `/procs` |
| Conexiones salientes | `psutil.net_connections` | `/connections` |
| Arranque automático | Registro de Windows / `*.desktop` | `/startup` |
| Servicios | `psutil.win_service_iter` / `systemctl` | `/services` |
| Firewall | `netsh advfirewall` / `ufw` / `firewall-cmd` | `/firewall` |
| `hosts`, DNS y proxy | Archivo `hosts` + variables de proxy | `/hosts` |
| Todo el bundle | Lo anterior combinado y redactado | `/diagnostics` |

Los datos también alimentan las respuestas del modelo: `render_bundle()` los
convierte en texto legible, **redacta** la carpeta personal y el nombre de usuario
y recorta el resultado (por defecto 4000 caracteres) antes de enviarlo.

## Solo lectura, sin shell

- Los comandos del sistema se ejecutan con `subprocess.run(..., shell=False)`, con
  una lista de argumentos (nunca una cadena interpretada) y un *timeout* corto.
- Las lecturas directas son de archivos y del registro; nunca se escribe.
- Los datos de `psutil` pueden requerir permisos elevados: si un PID no se puede
  resolver, se indica con una nota en lugar de fallar.

## `check_port`: la parte determinista

`check_port(port)` es el único diagnóstico que no depende del modelo:

- **`listening`**: algo ya está escuchando en ese puerto; se listan el PID y el
  proceso.
- **`not_listening`**: nada escucha. El mensaje recuerda que un firewall no puede
  *bloquear* un puerto donde nada escucha: el servicio no corre o usa otro puerto.

```powershell
/port 8080
```

También se usa para el modo de diagnóstico honesto que describe el README: separar
"nada escucha" de "algo escucha pero no llega tráfico" (probable firewall), sin
afirmar causas que no se puedan sustentar con evidencia.

## Caché

`collect_diagnostics()` guarda el resultado unos **15 segundos** (clave según el
workspace). Esto evita recolectar de nuevo cuando encadenas comandos seguidos,
sin servir datos peligrosamente viejos.

## Redacción de datos sensibles

Antes de salir del equipo, `redact_text()` sustituye:

- La carpeta personal por `~`.
- El nombre de usuario por `<usuario>`.
- Las credenciales de un proxy en una URL por `<credenciales>`.

Usa `/diagnostics` para ver exactamente el texto que se enviaría. Ver
[Seguridad y privacidad](seguridad-y-privacidad.md).
