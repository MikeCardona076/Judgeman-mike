# Arquitectura

JudgeMan-Mike es una aplicación local. No hay servidor intermedio: tu equipo, tu
proveedor LLM y tus datos. Esta página describe cómo está organizado el código y
por dónde pasa cada flujo.

## Vista general

```
                    +---------------------------+
                    |          CLI / TUI        |   judgman/cli.py, tui.py
                    |  (jmike chat, comandos /) |
                    +-------------+-------------+
                                  |
                    +-------------v-------------+
                    |        ChatSession        |   judgman/core/chat.py
                    | modes: diagnose/security/ |
                    |          file             |
                    +------+-------------+------+
                           |             |
              +------------v--+      +---v-----------------+
              |   Analyzer    |      |  diagnostico        |  core/diagnostics.py
              | (LiteLLM)     |      |  (solo lectura)     |
              +-------+-------+      +-----------+---------+
                      |                          |
              +-------v--------+      +----------v---------+
              | proveedor LLM  |      | psutil + comandos  |
              | (remoto)       |      | de solo lectura    |
              +----------------+      +--------------------+

              +----------------+      +--------------------+
              |  ActionRunner  |----->|  auditoria         |  %APPDATA%\judgman\
              | (confirmacion) |      |  audit.log         |
              +----------------+      +--------------------+

              +----------------+      +--------------------+
              |  API FastAPI   |      |  monitor web       |  judgman/api, ui/
              |  + watchdog    |      |  (127.0.0.1)       |
              +----------------+      +--------------------+
```

## Capas

- **Interfaces**: `judgman/cli.py` (consola simple y comandos), `judgman/tui.py`
  (consola Tron a pantalla completa) y `judgman/api/server.py` + `judgman/ui/`
  (monitor web).
- **Dominio**: `judgman/core/`.
  - `chat.py`: sesión de conversación, modos y construcción del contexto.
  - `analyzer.py`: cliente del proveedor LLM (vía LiteLLM) y *prompts* de cada
    modo. Es la única pieza que habla con la red.
  - `diagnostics.py`: recolección de evidencia del equipo en modo solo lectura.
  - `actions.py`: catálogo cerrado de reparaciones, validación, confirmación y
    auditoría.
  - `scanner.py` y `metrics.py`: monitor pasivo de archivos y gauges del HUD.
- **Configuración y presentación**: `judgman/config.py` (ajustes y rutas),
  `judgman/theme.py` (paleta, estilos y textos de ayuda), `judgman/onboarding.py`
  (asistente inicial) y `judgman/main.py` (arranque del monitor y bandeja).

## Flujo de una consulta

1. Escribes una pregunta o usas un comando (`/diagnose`, `/ports`, ...).
2. `ChatSession` decide si necesita evidencia del sistema. Si es así, llama a
   `collect_diagnostics()`, que reúne puertos, procesos, conexiones, arranque,
   servicios, firewall y `hosts` con una caché de pocos segundos.
3. El resultado se convierte en texto con `render_bundle()`, se **redacta**
   (carpeta personal y nombre de usuario) y se acota a un tamaño máximo.
4. `Analyzer` envía el modo, el contexto y tu mensaje al proveedor LLM
   configurado y transmite la respuesta token a token.
5. Si la respuesta propone acciones, `parse_actions()` valida cada bloque
   ```action``` contra `ACTION_CATALOG`. Cuando pides `/apply <n>`, `ActionRunner`
   muestra el comando, pide confirmación y registra el resultado en la auditoría.

## Puntos de diseño

- **El modelo no ejecuta nada.** Solo puede proponer acciones de un catálogo
  cerrado; el `argv` se construye en código, nunca desde texto libre, y se
  ejecuta sin *shell*.
- **La red solo sale por un sitio.** `analyzer.py` es el único módulo que habla
  con un servicio externo.
- **La evidencia es de solo lectura.** `diagnostics.py` no modifica el sistema;
  usa APIs de `psutil`, lecturas de archivos y comandos de consulta.
- **Todo lo que cambia el sistema pasa por la auditoría.** Ver
  [Acciones](acciones.md) y [Seguridad y privacidad](seguridad-y-privacidad.md).
