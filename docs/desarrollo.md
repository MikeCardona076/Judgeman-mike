# Desarrollo

Guía para trabajar en el código de JudgeMan-Mike.

## Entorno

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

El extra `dev` añade `pytest`, `httpx` y `build`. Si quieres probar los gauges y
los colectores de `psutil`, instala también el extra `monitor`:

```powershell
python -m pip install -e ".[dev,monitor]"
```

## Pruebas

```powershell
python -m pytest
```

Las pruebas cubren el confinamiento de rutas y enlaces simbólicos, el scanner de
solo lectura, la recolección de diagnóstico (puertos, servicios, firewall), el
catálogo de acciones y su ejecución con confirmación y auditoría, los endpoints de
la API, la sesión de chat, la CLI, el tema y la consola Tron, y el muestreo de
métricas con y sin `psutil`.

## Empaquetado

```powershell
python -m build
python -m twine check dist/*
```

## Estructura del proyecto

```
judgman/
  __init__.py         # version y docstring del paquete
  cli.py              # comandos, chat en linea, /apply, /pro
  tui.py              # consola Tron (prompt_toolkit)
  theme.py            # paleta, estilos, ayuda de comandos y banner
  config.py           # ajustes y rutas de configuracion
  onboarding.py        # asistente inicial
  main.py             # arranque del monitor y bandeja del sistema
  core/
    chat.py           # sesion y modos
    analyzer.py       # cliente LLM (LiteLLM) y prompts
    diagnostics.py    # recoleccion solo lectura
    actions.py        # catalogo, confirmacion y auditoria
    scanner.py        # monitor pasivo de archivos
    metrics.py        # gauges CPU/RAM/disco
  api/
    server.py         # API FastAPI y montaje de la UI
  ui/                 # index.html, css, js, logo
tests/                # pytest
docs/                 # esta documentacion
```

## Convenciones

- Python 3.11+; tipado en las firmas públicas.
- Los comandos del sistema se ejecutan **sin shell** y con `timeout`.
- La evidencia del sistema es de solo lectura; lo que cambia el sistema vive en
  `actions.py` y siempre pasa por confirmación y auditoría.
- Los textos de la interfaz van en español.

## Añadir una acción al catálogo

1. Define un `build(params) -> list[str]` que devuelva el `argv` (sin shell) y
   valide los parámetros con `_require`.
2. Añade un `ActionSpec` a `ACTION_CATALOG` con `title`, `description`, `risk` y
   `reversible`.
3. Añade un test en `tests/test_actions.py` que cubra la construcción del comando,
   la validación de parámetros y que no haya metacaracteres de shell.

## Añadir un comando del chat

1. Registra el texto de ayuda en `COMMAND_HELP` (`judgman/theme.py`).
2. Maneja el comando en `execute_command` (`judgman/cli.py`).
3. Añade un test en `tests/test_cli.py` que verifique la salida en un `Console`
   con `io.StringIO`.

## Publicación

El proyecto se instala desde GitHub (no se publica en PyPI). Al etiquetar una
versión, actualiza `judgman/__init__.py` y `CHANGELOG.md`.
