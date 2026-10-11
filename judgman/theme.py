"""Tema "consola Tron" para el chat de terminal.

Centraliza la paleta, los estilos de ``rich``, las descripciones de comandos,
el resaltado de terminos de seguridad y los helpers del HUD (gauges) para que la
estetica sea consistente entre el flujo plano y la TUI a pantalla completa.
"""

import os

from rich.console import Console
from rich.theme import Theme

# Paleta Tron (inspirada en TRON: Legacy / eDEX-UI).
BACKGROUND = "#05070a"
CYAN = "#00e5ff"
BLUE = "#0a84ff"
MAGENTA = "#ff2fd6"
VIOLET = "#b967ff"
GREEN = "#7dffb3"
AMBER = "#ffd23f"
ORANGE = "#ff7a29"
RED = "#ff3860"
TEXT = "#dfe9ff"
DIM = "#6d7a99"
GRID = "#12283c"

THEME = Theme(
    {
        "jmike.title": f"bold {CYAN}",
        "jmike.accent": f"bold {CYAN}",
        "jmike.blue": f"bold {BLUE}",
        "jmike.violet": f"bold {VIOLET}",
        "jmike.ok": f"bold {GREEN}",
        "jmike.warn": f"bold {AMBER}",
        "jmike.err": f"bold {RED}",
        "jmike.dim": DIM,
        "jmike.text": TEXT,
        "jmike.prompt": f"bold {CYAN}",
        "jmike.user": f"bold {VIOLET}",
        "jmike.assistant": TEXT,
        "jmike.rule": f"{DIM} on {BACKGROUND}",
        "jmike.heading": f"bold {CYAN}",
        "jmike.key": f"bold {BLUE}",
        # Resaltado de terminos de seguridad.
        "jmike.critical": f"bold {RED} on #2a0008",
        "jmike.high": f"bold {AMBER}",
        "jmike.medium": f"bold {ORANGE}",
        "jmike.low": f"bold {GREEN}",
        "jmike.vuln": f"bold {MAGENTA}",
        "jmike.rec": f"bold {GREEN}",
    }
)

#: (uso, descripcion) compartido por la ayuda y el autocompletado.
COMMAND_HELP: tuple[tuple[str, str], ...] = (
    ("/help", "Muestra esta ayuda."),
    ("/status", "Muestra modelo, workspace y modo."),
    ("/diagnose <pregunta>", "Diagnostica un problema del equipo."),
    ("/security <texto>", "Busca amenazas en el texto o en el contexto."),
    ("/file <ruta>", "Analiza el contenido de un archivo del workspace."),
    ("/mode", "Cambia el modo (/mode diagnose|security|file)."),
    ("/model", "Muestra el modelo activo."),
    ("/diagnostics", "Muestra los datos de diagnostico que se enviarian."),
    ("/ports", "Lista los puertos a la escucha."),
    ("/port <n>", "Diagnostica un puerto concreto."),
    ("/procs", "Procesos con mas carga."),
    ("/connections", "Conexiones salientes establecidas."),
    ("/services", "Servicios detenidos o relevantes."),
    ("/startup", "Programas de arranque automatico."),
    ("/firewall", "Estado del firewall."),
    ("/hosts", "Archivo hosts, DNS y proxy."),
    ("/apply <n>", "Ejecuta una accion propuesta (pide confirmacion)."),
    ("/pro", "Funciones Pro (próximamente, no disponible en esta versión)."),
    ("/snapshot", "Datos basicos del sistema que se enviarian."),
    ("/serve", "Inicia el monitor web en segundo plano."),
    ("/settings", "Reconfigura la API key, el modelo o el workspace."),
    ("/retry", "Repite la ultima pregunta."),
    ("/clear, /new", "Limpia el historial y la pantalla."),
    ("/exit, /quit", "Sale del chat."),
)

_BANNER_TEXT = "J U D G E M A N   -   M I K E   >>   amenaza y diagnostico"
_BANNER_INNER = f"   {_BANNER_TEXT}   "
_BANNER_RULE = "+" + "=" * len(_BANNER_INNER) + "+"
BANNER = "\n".join(
    (
        _BANNER_RULE,
        "|" + _BANNER_INNER + "|",
        _BANNER_RULE,
    )
)

CONSOLE_KWARGS = {"theme": THEME, "highlight": False}


def make_highlighter():
    """Resalta terminos de seguridad (riesgos, recomendaciones) en las salidas."""
    from rich.highlighter import RegexHighlighter

    class SecurityHighlighter(RegexHighlighter):
        base_style = "jmike."
        highlights = [
            r"(?i)(?P<critical>\bCR[IÍ]TICO\b)",
            r"(?i)(?P<high>\bALTO\b)",
            r"(?i)(?P<medium>\bMEDIO\b)",
            r"(?i)(?P<low>\bBAJO\b)",
            r"(?i)(?P<vuln>\bVULNERABILIDAD(?:ES)?\b)",
            r"(?i)(?P<rec>\bRECOMENDACI[OÓ]N\b)",
        ]

    return SecurityHighlighter()


def make_console(no_color: bool | None = None, **kwargs: object) -> Console:
    """Crea un ``Console`` con el tema; respeta ``NO_COLOR``."""
    if no_color is None:
        no_color = bool(os.environ.get("NO_COLOR"))
    options = {
        **CONSOLE_KWARGS,
        "no_color": no_color,
        "highlighter": make_highlighter(),
        **kwargs,
    }
    return Console(**options)


def block_bar(percent: float, width: int = 12) -> str:
    """Barra de bloques para un porcentaje 0-100."""
    percent = max(0.0, min(100.0, float(percent)))
    filled = int(round(width * percent / 100))
    return "\u2588" * filled + "\u2591" * (width - filled)


def gauge_color(percent: float) -> str:
    if percent >= 90:
        return RED
    if percent >= 70:
        return AMBER
    return CYAN


def gauge_segments(
    label: str,
    percent: float,
    width: int = 12,
) -> list[tuple[str, str]]:
    """Segmentos ``(estilo, texto)`` listos para ``prompt_toolkit``."""
    percent = max(0.0, min(100.0, float(percent)))
    color = gauge_color(percent)
    return [
        (f"fg:{DIM}", f"{label:<4} "),
        (f"fg:{color}", block_bar(percent, width)),
        (f"fg:{TEXT}", f" {percent:3.0f}%"),
    ]


def prompt_style():
    """Estilo de ``prompt_toolkit`` a juego con el tema (flujo plano)."""
    from prompt_toolkit.styles import Style

    return Style.from_dict(
        {
            "prompt": f"fg:{CYAN} bold",
            "mode.diagnose": f"fg:{CYAN} bold",
            "mode.security": f"fg:{MAGENTA} bold",
            "mode.file": f"fg:{VIOLET} bold",
            "arg": f"fg:{DIM}",
            "completion-menu.completion": f"bg:{BACKGROUND} fg:{DIM}",
            "completion-menu.completion.current": f"bg:{MAGENTA} fg:{BACKGROUND}",
            "completion-menu.meta.completion": f"bg:{BACKGROUND} fg:{CYAN}",
            "completion-menu.meta.completion.current": f"bg:{VIOLET} fg:{BACKGROUND}",
            "scrollbar.background": f"bg:{BACKGROUND}",
            "scrollbar.button": f"bg:{VIOLET}",
        }
    )


def tui_style():
    """Estilo completo para la ``Application`` a pantalla completa."""
    from prompt_toolkit.styles import Style

    return Style.from_dict(
        {
            "header": f"bg:{BACKGROUND}",
            "header.title": f"fg:{CYAN} bold",
            "header.dim": f"fg:{DIM}",
            "header.clock": f"fg:{ORANGE} bold",
            "body": f"bg:{BACKGROUND} fg:{TEXT}",
            "input": f"bg:{BACKGROUND} fg:{TEXT}",
            "input.prompt": f"fg:{CYAN} bold",
            "footer": f"bg:{BACKGROUND} fg:{DIM}",
            "footer.accent": f"fg:{CYAN}",
            "footer.busy": f"fg:{ORANGE} bold",
            "mode.diagnose": f"fg:{CYAN} bold",
            "mode.security": f"fg:{MAGENTA} bold",
            "mode.file": f"fg:{VIOLET} bold",
            "completion-menu.completion": f"bg:{BACKGROUND} fg:{DIM}",
            "completion-menu.completion.current": f"bg:{CYAN} fg:{BACKGROUND}",
            "completion-menu.meta.completion": f"bg:{BACKGROUND} fg:{CYAN}",
            "completion-menu.meta.completion.current": f"bg:{BLUE} fg:{BACKGROUND}",
            "scrollbar.background": f"bg:{GRID}",
            "scrollbar.button": f"bg:{CYAN}",
        }
    )
