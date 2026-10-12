"""Consola Tron a pantalla completa para ``jmike`` (estilo eDEX-UI / TRON).

Construye una :class:`prompt_toolkit.application.Application` fullscreen con:

* header HUD fijo (titulo, reloj y gauges de CPU/RAM/disco en vivo),
* cuerpo con la conversacion desplazable (Markdown renderizado a ANSI),
* entrada multilinea con autocompletado de comandos y de rutas del workspace,
* barra de estado inferior con modelo, workspace y atajos.

Las respuestas del proveedor se transmiten token a token desde un hilo, y las
metricas se refrescan en segundo plano. Si ``psutil`` no esta instalado, los
gauges degradan a RAM/disco del snapshot y lo indican en el header.
"""

from __future__ import annotations

import io
import threading
import time
from datetime import datetime
from pathlib import Path

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import Condition, has_focus
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.mouse_events import MouseEventType
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from judgman import updates
from judgman.cli import actions_table, execute_command, update_panel
from judgman.core.actions import ActionRunner, ProposedAction
from judgman.core.chat import ChatSession
from judgman.core.metrics import MetricsSampler
from judgman.paths import user_audit_path, user_history_path
from judgman.theme import (
    BANNER,
    COMMAND_HELP,
    THEME,
    gauge_segments,
    make_highlighter,
    tui_style,
)

HEADER_ROWS = 3
FOOTER_ROWS = 1
SEPARATOR_ROWS = 1
MAX_INPUT_ROWS = 6
MAX_BODY_LINES = 8000
SPINNER = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"


class ScrollableTextControl(FormattedTextControl):
    """Control de texto que responde a la rueda del raton (scroll)."""

    def __init__(self, *args, on_scroll=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._on_scroll = on_scroll

    def mouse_handler(self, mouse_event):  # noqa: ANN001 - API de prompt_toolkit
        if self._on_scroll is not None and mouse_event.event_type in (
            MouseEventType.SCROLL_UP,
            MouseEventType.SCROLL_DOWN,
        ):
            self._on_scroll(mouse_event)
            return None
        return super().mouse_handler(mouse_event)


class TuiCompleter(Completer):
    """Completa comandos ``/`` y rutas tras ``/file ``."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/file "):
            yield from self._complete_path(text[len("/file ") :])
            return
        if text.startswith("/") and " " not in text:
            for usage, description in COMMAND_HELP:
                command = usage.split()[0]
                if command.startswith(text):
                    yield Completion(
                        command,
                        start_position=-len(text),
                        display_meta=description,
                    )

    def _complete_path(self, argument: str):
        base = self.workspace
        target = base / argument
        if target.is_dir():
            directory = target
            prefix = ""
        else:
            directory = target.parent
            prefix = target.name
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for entry in entries:
            if not entry.name.startswith(prefix):
                continue
            try:
                relative = entry.relative_to(base).as_posix()
            except ValueError:
                continue
            if entry.is_dir():
                relative += "/"
            yield Completion(
                relative,
                start_position=-len(argument),
                display=entry.name + ("/" if entry.is_dir() else ""),
            )


class TronConsole:
    """Aplicacion fullscreen que da vida a la consola Tron."""

    def __init__(
        self,
        session: ChatSession,
        fallback_width: int = 80,
        fallback_height: int = 24,
        history_path: Path | None = None,
        notice: object | None = None,
    ) -> None:
        self.session = session
        self._history_path = history_path
        self._notice = notice
        self._highlighter = make_highlighter()
        self._sampler = MetricsSampler(workspace=session.workspace)
        self._metrics = self._sampler.sample(force=True)
        self._lines: list[str] = []
        self._stream_start = 0
        self._scroll = 0
        self._busy = False
        self._spinner = 0
        self._note_text = ""
        self._note_until = 0.0
        self._last_metrics_at = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._app: Application | None = None
        self._fallback_size = (fallback_width, fallback_height)
        self._pending_actions: list[ProposedAction] = []
        self._pending_update = False

        self.input_buffer = Buffer(
            multiline=True,
            completer=TuiCompleter(session.workspace),
            complete_while_typing=True,
            history=self._history(),
            accept_handler=self._on_accept,
        )
        self._layout = self._build_layout()

    # ------------------------------------------------------------------ layout
    def _history(self) -> FileHistory:
        path = self._history_path or user_history_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:  # pragma: no cover - permisos
            pass
        return FileHistory(str(path))

    def _build_layout(self) -> Layout:
        header = Window(
            FormattedTextControl(self._header),
            height=HEADER_ROWS,
            style="class:header",
        )
        body = Window(
            ScrollableTextControl(self._body, on_scroll=self._on_body_mouse),
            wrap_lines=True,
            style="class:body",
        )
        separator = Window(
            height=SEPARATOR_ROWS, char="\u2500", style="class:header.dim"
        )
        prompt = [("class:input.prompt", "\u00bb ")]
        entry = Window(
            BufferControl(
                buffer=self.input_buffer,
                input_processors=[BeforeInput(prompt)],
            ),
            height=Dimension(min=1, max=MAX_INPUT_ROWS),
            style="class:input",
        )
        footer = Window(
            FormattedTextControl(self._footer),
            height=FOOTER_ROWS,
            style="class:footer",
        )
        return Layout(
            HSplit([header, body, separator, entry, footer]),
            focused_element=self.input_buffer,
        )

    def _create_application(self) -> Application:
        return Application(
            layout=self._layout,
            key_bindings=self._key_bindings(),
            style=tui_style(),
            full_screen=True,
            mouse_support=True,
            refresh_interval=0.1,
        )


    def _key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        @bindings.add("enter", filter=has_focus(self.input_buffer))
        def _submit(event) -> None:
            self.input_buffer.validate_and_handle()

        @bindings.add("escape", "enter", filter=has_focus(self.input_buffer))
        def _newline(event) -> None:
            self.input_buffer.insert_text("\n")

        @bindings.add("c-l")
        def _clear(event) -> None:
            with self._lock:
                self._lines.clear()
                self._scroll = 0
            self._notify("pantalla limpia")

        @bindings.add("c-c")
        def _cancel(event) -> None:
            if self._busy:
                self._notify("cancelando...")
            else:
                self.input_buffer.reset()
                self._notify("linea cancelada")

        @bindings.add("c-d")
        def _exit(event) -> None:
            if not self.input_buffer.text:
                event.app.exit()

        @bindings.add("pageup")
        def _up(event) -> None:
            self._scroll_by(self._body_rows())

        @bindings.add("pagedown")
        def _down(event) -> None:
            self._scroll_by(-self._body_rows())

        @bindings.add("c-home")
        def _top(event) -> None:
            self._scroll_to_top()

        @bindings.add("c-end")
        def _bottom(event) -> None:
            self._scroll_to_bottom()

        empty_buffer = Condition(lambda: not self.input_buffer.text)

        @bindings.add("home", filter=has_focus(self.input_buffer) & empty_buffer)
        def _home(event) -> None:
            self._scroll_to_top()

        @bindings.add("end", filter=has_focus(self.input_buffer) & empty_buffer)
        def _end(event) -> None:
            self._scroll_to_bottom()

        return bindings

    # ------------------------------------------------------------------ render
    def _width(self) -> int:
        if self._app is None:
            return max(40, self._fallback_size[0])
        try:
            return max(40, self._app.output.get_size().columns)
        except Exception:
            return max(40, self._fallback_size[0])

    def _height(self) -> int:
        if self._app is None:
            return max(10, self._fallback_size[1])
        try:
            return max(10, self._app.output.get_size().rows)
        except Exception:
            return max(10, self._fallback_size[1])

    def _body_rows(self) -> int:
        input_lines = min(max(1, self.input_buffer.text.count("\n") + 1), MAX_INPUT_ROWS)
        reserved = HEADER_ROWS + FOOTER_ROWS + SEPARATOR_ROWS + input_lines
        return max(1, self._height() - reserved)

    def _render(self, *renderables: object) -> str:
        stream = io.StringIO()
        console = Console(
            file=stream,
            force_terminal=True,
            color_system="truecolor",
            width=self._width(),
            theme=THEME,
            highlighter=make_highlighter(),
            soft_wrap=False,
            legacy_windows=False,
        )
        for renderable in renderables:
            console.print(renderable)
        return stream.getvalue()

    def _header(self) -> FormattedText:
        width = self._width()
        fragments: list[tuple[str, str]] = [
            ("class:header.dim", "\u2500" * width),
            ("", "\n"),
        ]
        left = "\u259a JudgeMan-Mike  ::  CONSOLA TRON"
        right = f"[{self.session.mode.upper()}]  {datetime.now().strftime('%H:%M:%S')}"
        gap = width - len(left) - len(right)
        if gap < 1:
            left = left[: max(0, width - len(right) - 1)]
            gap = max(0, width - len(left) - len(right))
        fragments.append(("class:header.title", left))
        fragments.append(("class:header.dim", " " * gap))
        fragments.append(("class:header.clock", right))
        fragments.append(("", "\n"))
        fragments.extend(self._gauge_fragments(width))
        return FormattedText(fragments)

    def _gauge_fragments(self, width: int) -> list[tuple[str, str]]:
        metrics = self._metrics
        fragments: list[tuple[str, str]] = []
        used = 0

        def add(segments: list[tuple[str, str]]) -> None:
            nonlocal used
            for style, text in segments:
                fragments.append((style, text))
                used += len(text)

        def add_gauge(label: str, percent: float) -> bool:
            nonlocal used
            segments = gauge_segments(label, percent)
            extra = 3 if used else 0
            if used and used + extra + sum(len(t) for _, t in segments) > width:
                return False
            if used:
                fragments.append(("class:header.dim", "   "))
                used += 3
            add(segments)
            return True

        if metrics.available:
            add_gauge("CPU", metrics.cpu_percent)
            add_gauge("RAM", metrics.mem_percent)
            add_gauge("DISK", metrics.disk_percent)
        else:
            add_gauge("RAM", metrics.mem_percent)
            add_gauge("DISK", metrics.disk_percent)
            note = metrics.note or PSUTIL_HINT
            remaining = width - used - 3
            if remaining > 8:
                fragments.append(("class:header.dim", "   "))
                fragments.append(("class:header.dim", note[:remaining]))
        return fragments

    def _body(self) -> ANSI:
        with self._lock:
            lines = list(self._lines)
            scroll = self._scroll
        rows = self._body_rows()
        end = max(0, len(lines) - scroll)
        start = max(0, end - rows)
        chunk = lines[start:end]
        rendered = "\n".join(chunk)
        if len(chunk) < rows:
            rendered += "\n" * (rows - len(chunk))
        return ANSI(rendered)

    def _footer(self) -> FormattedText:
        width = self._width()
        if self._busy:
            frame = SPINNER[self._spinner % len(SPINNER)]
            return FormattedText(
                [("class:footer.busy", f" {frame} generando respuesta...   Ctrl+C cancela")]
            )
        if self._note_text and time.monotonic() < self._note_until:
            return FormattedText([("class:footer.accent", " " + self._note_text)])
        workspace = self.session.workspace.name or str(self.session.workspace)
        left = f"[{self.session.mode.upper()}] {self.session.analyzer.model}  \u00b7  {workspace}"
        if self._scroll > 0:
            right = "\u25b2 historial \u00b7 End vuelve abajo \u00b7 Ctrl+D salir"
        else:
            right = "Alt+Enter multilinea \u00b7 rueda/PageUp historial \u00b7 Ctrl+D salir"
        gap = width - len(left) - len(right)
        if gap < 1:
            return FormattedText([("class:footer", left[:width])])
        return FormattedText(
            [
                ("class:footer", left),
                ("class:footer", " " * gap),
                ("class:footer.accent", right),
            ]
        )

    # ------------------------------------------------------------------ output
    def _append(self, ansi: str) -> None:
        new_lines = ansi.splitlines() or [""]
        with self._lock:
            self._lines.extend(new_lines)
            removed = max(0, len(self._lines) - MAX_BODY_LINES)
            if removed:
                del self._lines[:removed]
                self._stream_start = max(0, self._stream_start - removed)

    def _replace_streaming(self, ansi: str) -> None:
        new_lines = ansi.splitlines() or [""]
        with self._lock:
            self._lines[self._stream_start :] = new_lines

    def _scroll_by(self, delta: int) -> None:
        with self._lock:
            total = len(self._lines)
            self._scroll = max(0, min(total, self._scroll + delta))

    def _scroll_to_top(self) -> None:
        with self._lock:
            self._scroll = max(0, len(self._lines) - self._body_rows())

    def _scroll_to_bottom(self) -> None:
        with self._lock:
            self._scroll = 0

    def _on_body_mouse(self, mouse_event) -> None:  # noqa: ANN001 - API de prompt_toolkit
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self._scroll_by(3)
        elif mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self._scroll_by(-3)

    def _notify(self, text: str, seconds: float = 2.5) -> None:
        self._note_text = text
        self._note_until = time.monotonic() + seconds

    def _touch(self) -> None:
        if self._app is not None:
            self._app.invalidate()

    # ------------------------------------------------------------------ input
    def _on_accept(self, buffer: Buffer) -> None:
        text = buffer.text.strip()
        buffer.reset()
        if self._pending_update:
            self._resolve_update(text)
            return
        if self._pending_actions:
            self._resolve_confirmation(text)
            return
        if not text:
            return
        if text.startswith("/"):
            self._handle_command(text)
            return
        self._start_reply(text)

    def _resolve_update(self, text: str) -> None:
        self._pending_update = False
        if text.casefold() not in ("y", "yes", "s", "si", "sí"):
            self._append(
                self._render(Text("Actualizacion cancelada.", style="jmike.dim"))
            )
            self._touch()
            return
        self._append(
            self._render(
                Text("Actualizando... esto puede tardar.", style="jmike.dim")
            )
        )
        self._notify("actualizando...")
        self._touch()

        def work() -> None:
            ok, message = updates.perform_update()
            if ok:
                note = Text(
                    "Actualizado. Reinicia jmike para usar la nueva version.",
                    style="jmike.ok",
                )
            else:
                note = Text(f"No se pudo actualizar: {message}", style="jmike.err")
            self._append(self._render(note))
            self._notify("actualizacion finalizada")
            self._touch()

        threading.Thread(
            target=work, name="judgman-tui-update", daemon=True
        ).start()

    def _resolve_confirmation(self, text: str) -> None:
        action = self._pending_actions.pop(0)
        approved = text.casefold() in ("y", "yes", "s", "si", "sí")
        runner = ActionRunner(
            confirm=lambda _action: approved,
            audit_path=user_audit_path(),
        )
        result = runner.apply(action)
        if result.ok:
            note = Text(f"Ejecutado: {action.action_id}", style="jmike.ok")
        elif not result.confirmed:
            note = Text(f"Cancelado: {action.action_id}", style="jmike.dim")
        else:
            note = Text(
                f"Fallo: {action.action_id} ({result.error or 'sin detalle'})",
                style="jmike.err",
            )
        self._append(self._render(note))
        self._prompt_next_action()
        self._touch()

    def _prompt_next_action(self) -> None:
        if not self._pending_actions:
            return
        action = self._pending_actions[0]
        self._append(self._render(actions_table([action])))
        self._append(
            self._render(
                Text(
                    f"Ejecutar '{action.action_id}'? [y/N]",
                    style="jmike.warn",
                )
            )
        )

    def _handle_command(self, line: str) -> None:
        if self._pending_actions:
            self._notify("termina de confirmar las acciones pendientes")
            return
        outcome = execute_command(self.session, line)
        for renderable in outcome.renderables:
            self._append(self._render(renderable))
        if outcome.clear_screen:
            with self._lock:
                self._lines.clear()
                self._scroll = 0
        if outcome.reply is not None:
            text, mode = outcome.reply
            self._start_reply(text, mode)
        elif outcome.apply_actions:
            self._pending_actions = list(outcome.apply_actions)
            self._prompt_next_action()
        elif outcome.update_run:
            info = updates.check_for_update(force=True)
            self._append(self._render(update_panel(info)))
            if info.available:
                self._pending_update = True
                self._append(
                    self._render(
                        Text("Actualizar ahora? [y/N]", style="jmike.warn")
                    )
                )
            else:
                self._notify("sin actualizaciones")
        elif not outcome.quit:
            with self._lock:
                self._scroll = 0
        if outcome.quit:
            if self._app is not None:
                self._app.exit()
        self._touch()

    # ------------------------------------------------------------------ streaming
    def _start_reply(self, text: str, mode: str | None = None) -> None:
        self._busy = True
        with self._lock:
            self._scroll = 0
        self._append(self._render(Text(f"\u00bb {text}", style="jmike.user")))
        with self._lock:
            self._stream_start = len(self._lines)
            self._lines.append("")
        threading.Thread(
            target=self._stream_worker,
            args=(text, mode),
            name="judgman-tui-stream",
            daemon=True,
        ).start()
        self._touch()

    def _stream_worker(self, text: str, mode: str | None) -> None:
        parts: list[str] = []
        try:
            for chunk in self.session.stream_reply(text, mode=mode):
                parts.append(chunk)
                self._replace_streaming(self._render(Text("".join(parts))))
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario
            panel = Panel(
                Text(str(exc), style="jmike.err"),
                title="Error del proveedor",
                border_style="jmike.err",
                subtitle="[jmike.dim]Revisa el modelo con /settings[/jmike.dim]",
            )
            self._replace_streaming(self._render(panel))
        else:
            answer = "".join(parts)
            rendered = self._render(Markdown(answer)) if answer.strip() else ""
            self._replace_streaming(rendered)
            self._append(self._render(self._metrics_line(answer)))
            for error in self.session.last_action_errors:
                self._append(self._render(Text(error, style="jmike.warn")))
            if self.session.last_actions:
                self._append(self._render(actions_table(self.session.last_actions)))
                self._append(
                    self._render(
                        Text(
                            "Usa /apply <n> para ejecutar una accion; se pedira "
                            "confirmacion.",
                            style="jmike.dim",
                        )
                    )
                )
            self._notify(f"listo \u00b7 {self.session.last_elapsed:.1f}s")
        finally:
            self._busy = False
            self._touch()

    def _metrics_line(self, answer: str) -> Text:
        chars = len(answer)
        tokens = round(chars / 4)
        return Text(
            f"  {self.session.last_elapsed:.1f}s \u00b7 {chars} caracteres "
            f"\u00b7 ~{tokens} tokens",
            style="jmike.dim",
        )

    # ------------------------------------------------------------------ ticker
    def _ticker(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.1)
            if self._busy:
                self._spinner += 1
            if (time.monotonic() - self._last_metrics_at) >= self._sampler.interval:
                self._metrics = self._sampler.sample()
                self._last_metrics_at = time.monotonic()

    # ------------------------------------------------------------------ run
    def run(self) -> None:
        if self._app is None:
            self._app = self._create_application()
        self._append(self._render(Text(BANNER, style="jmike.accent")))
        if self._notice:
            self._append(self._render(self._notice))
        self._last_metrics_at = 0.0
        self._metrics = self._sampler.sample(force=True)
        ticker = threading.Thread(
            target=self._ticker, name="judgman-tui-metrics", daemon=True
        )
        ticker.start()
        try:
            self._app.run()
        finally:
            self._stop.set()


def run_tui(
    session: ChatSession,
    console: Console | None = None,
    notice: object | None = None,
) -> None:
    """Arranca la consola Tron a pantalla completa."""
    TronConsole(session, notice=notice).run()
