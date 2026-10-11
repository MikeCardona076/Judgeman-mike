import judgman.theme as theme
from judgman.theme import (
    block_bar,
    gauge_color,
    gauge_segments,
    make_console,
    make_highlighter,
)


def test_block_bar_length_and_edges() -> None:
    assert len(block_bar(0, 10)) == 10
    assert block_bar(0, 10) == "\u2591" * 10
    assert block_bar(100, 10) == "\u2588" * 10
    assert block_bar(50, 10) == "\u2588" * 5 + "\u2591" * 5


def test_block_bar_clamps_out_of_range() -> None:
    assert block_bar(-20, 10) == "\u2591" * 10
    assert block_bar(180, 10) == "\u2588" * 10


def test_gauge_color_thresholds() -> None:
    assert gauge_color(10) == theme.CYAN
    assert gauge_color(75) == theme.AMBER
    assert gauge_color(95) == theme.RED


def test_gauge_segments_render_percent() -> None:
    segments = gauge_segments("CPU", 50.0, width=10)

    text = "".join(part for _, part in segments)
    assert "CPU" in text
    assert "50%" in text


def test_make_highlighter_marks_risk_terms() -> None:
    highlighter = make_highlighter()

    result = highlighter("esto es CRITICO y tambien ALTO")

    assert hasattr(result, "spans")
    assert result.spans


def test_make_console_respects_no_color_flag() -> None:
    console = make_console(no_color=True)

    assert console.no_color is True


def test_make_console_respects_env(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")

    console = make_console()

    assert console.no_color is True
