"""Tema "futuro dark punk" para el chat de terminal.

Centraliza la paleta, los estilos de ``rich`` y el estilo del prompt para que la
estetica sea consistente en toda la CLI.
"""

from rich.console import Console
from rich.theme import Theme

CYAN = "#00f0ff"
MAGENTA = "#ff2fd6"
VIOLET = "#b967ff"
GREEN = "#7dffb3"
AMBER = "#ffd23f"
RED = "#ff3860"
TEXT = "#e6e6ff"
DIM = "#8a86a8"
BACKGROUND = "#0a0a0f"

THEME = Theme(
    {
        "jmike.title": f"bold {MAGENTA}",
        "jmike.accent": f"bold {CYAN}",
        "jmike.violet": f"bold {VIOLET}",
        "jmike.ok": f"bold {GREEN}",
        "jmike.warn": f"bold {AMBER}",
        "jmike.err": f"bold {RED}",
        "jmike.dim": DIM,
        "jmike.text": TEXT,
        "jmike.prompt": f"bold {CYAN}",
        "jmike.user": f"bold {VIOLET}",
        "jmike.assistant": TEXT,
    }
)

_BANNER_TEXT = "J U D G M A N   .   M I K E   >>   dark punk"
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


def make_console(**kwargs: object) -> Console:
    """Crea un ``Console`` con el tema aplicado por defecto."""
    options = {**CONSOLE_KWARGS, **kwargs}
    return Console(**options)


def prompt_style():
    """Estilo de ``prompt_toolkit`` a juego con el tema."""
    from prompt_toolkit.styles import Style

    return Style.from_dict(
        {
            "prompt": f"fg:{CYAN} bold",
            "completion-menu.completion": f"bg:{BACKGROUND} fg:{DIM}",
            "completion-menu.completion.current": f"bg:{MAGENTA} fg:{BACKGROUND}",
            "scrollbar.background": f"bg:{BACKGROUND}",
            "scrollbar.button": f"bg:{VIOLET}",
        }
    )
