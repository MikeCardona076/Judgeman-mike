# Consola Tron (pantalla completa)

Cuando ejecutas `jmike` en una terminal interactiva, se abre una consola a
pantalla completa inspirada en eDEX-UI / TRON. Está implementada con
`prompt_toolkit` en `judgman/tui.py`.

## Distribución de la pantalla

```
+--------------------------------------------------------------+
|  J U D G E M A N  -  M I K E   >>  amenaza y diagnostico      |
|  [reloj]        CPU ███████░░░  62%   RAM ████░░░░░░  38% ... |
+--------------------------------------------------------------+
|                                                              |
|                     conversacion (Markdown)                 |
|                     y salidas de comandos                    |
|                                                              |
+--------------------------------------------------------------+
|  jmike > _                                                   |
|  modo: diagnose · modelo: openai/gpt-4o-mini · workspace: ... |
|  PageUp historial · End vuelve abajo                         |
+--------------------------------------------------------------+
```

- **HUD fijo**: el banner de marca, el reloj y los *gauges* en vivo de
  **CPU / RAM / disco**.
- **Cuerpo**: la conversación con Markdown y resaltado de términos de riesgo
  (`CRÍTICO`, `ALTO`, `MEDIO`, `BAJO`, `VULNERABILIDAD`, `RECOMENDACIÓN`).
- **Entrada**: el prompt `jmike >` con autocompletado de comandos `/` y de rutas
  tras `/file`.
- **Barra de estado**: modo, modelo, workspace y ayuda de desplazamiento.

## Atajos

| Tecla | Acción |
|-------|--------|
| `Enter` | Envía el mensaje. |
| `Alt+Enter` | Inserta un salto de línea. |
| `Ctrl+L` | Limpia la pantalla. |
| `PageUp` / `PageDown` | Desplaza la conversación. |
| `Ctrl+Home` / `Ctrl+End` | Va al principio / final del historial. |
| `Home` / `End` | Igual, cuando el cuadro de entrada está vacío. |
| Rueda del ratón | Desplaza la conversación. |
| `Ctrl+C` | Cancela la línea actual o la respuesta en curso. |
| `Ctrl+D` | Sale. |

El *scroll* combina teclado y ratón: el controlador de ratón del cuerpo captura
los eventos `SCROLL_UP` / `SCROLL_DOWN`.

## Gauges en vivo

Los indicadores de CPU/RAM/disco usan `psutil`, del extra opcional `monitor`:

```powershell
pipx install "judgman-mike[monitor] @ git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

Sin `psutil`, el HUD degrada a valores aproximados de RAM/disco desde el snapshot
y lo indica en el encabezado. El color del gauge cambia según la carga:

| Carga | Color |
|-------|-------|
| < 70 % | cian |
| 70–90 % | ámbar |
| ≥ 90 % | rojo |

## Cuándo no se usa la TUI

- Si no hay terminal interactiva, o
- si pasas `--plain`,

se usa la **consola simple en línea**, que funciona igual (mismos comandos y
respuestas) sin ocupar toda la pantalla.
