# Acciones (reparar con confirmación)

Cuando el diagnóstico apunta a una causa, el modelo puede **proponer** una
reparación. JudgeMan-Mike nunca ejecuta comandos libres: solo acepta acciones de
un catálogo cerrado, y solo las ejecuta si tú las confirmas.

## Catálogo

| `id` | Título | Parámetros | Riesgo | Reversible |
|------|--------|------------|--------|------------|
| `kill_process` | Terminar proceso | `pid` | alto | no |
| `open_firewall_port` | Permitir puerto en el firewall | `port` (`protocol`, `name` opcionales) | medio | sí |
| `close_firewall_port` | Cerrar puerto en el firewall | `port` (`protocol`, `name` opcionales) | bajo | sí |
| `start_service` | Iniciar servicio | `name` | bajo | sí |
| `stop_service` | Detener servicio | `name` | medio | sí |
| `restart_service` | Reiniciar servicio | `name` | medio | sí |

## Cómo se propone una acción

El modelo responde con un bloque de código etiquetado `action` que contiene JSON:

````
```action
{"id": "open_firewall_port", "params": {"port": 3000}, "reason": "La app no recibe conexiones entrantes"}
```
````

`parse_actions()` lee cada bloque y lo valida:

- El `id` debe existir en `ACTION_CATALOG`.
- No deben faltar parámetros obligatorios.
- Los parámetros deben poder construir el comando (por ejemplo, un `port`
  numérico).

Cualquier bloque inválido se descarta y se muestra un error en lugar de
ejecutarse.

## Aplicar una acción

```
/apply 1     # ejecuta la acción n.º 1 de la última respuesta
/apply all   # ejecuta todas las propuestas
```

Al aplicar, la consola muestra el **comando exacto** y pide una confirmación
`y/N`. Solo un `y` explícito continúa.

## Seguridad de ejecución

- El comando se construye en código como una lista de argumentos y se ejecuta
  con `shell=False`. **No** se interpola texto del modelo en una línea de shell,
  así que no hay metacaracteres que puedan inyectar comandos.
- Cada acción trae su nivel de riesgo y si es reversible.
- Un error del sistema operativo se captura y se reporta; nunca tumba la sesión.

## Auditoría

Toda acción —propuesta, confirmada, rechazada o fallida— se registra en JSON, una
línea por evento, en el log de auditoría:

- Windows: `%APPDATA%\judgman\audit.log`
- macOS/Linux: `~/.config/judgman/audit.log`

Cada entrada incluye el *timestamp* UTC, el `id`, los parámetros, el comando, si
se confirmó, si se ejecutó y el resultado. Ejemplo:

```json
{"timestamp": "2026-01-01T12:00:00+00:00", "action": "open_firewall_port", "params": {"port": 3000}, "command": ["netsh", "advfirewall", "firewall", "add", "rule", "name=judgman-allow-3000", "dir=in", "action=allow", "protocol=TCP", "localport=3000"], "confirmed": true, "executed": true, "ok": true, "error": null}
```

## Nota sobre permisos

Algunas acciones (firewall, servicios) requieren privilegios elevados. Si el
sistema devuelve un error de permisos, aparece en el resultado y en la auditoría;
vuelve a intentarlo desde una terminal elevada.
