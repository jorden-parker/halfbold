from pathlib import Path

import pytest
from conftest import make_font, make_variable_font
from PIL import ImageFont

from halfbold.cli import main
from halfbold.preview import (
    CANVAS_WIDTH,
    FONT_SIZE,
    LINE_HEIGHT,
    MARGIN,
    SAMPLE_TEXT,
    kitty_chunks,
    load_faces,
    render_preview,
    supports_kitty_graphics,
    wrap_words,
)


def _non_white_pixels(image, box) -> int:
    band = image.crop(box)
    return sum(1 for pixel in band.getdata() if pixel != (255, 255, 255))


def _paragraph_bands(regular: Path, bold: Path | None):
    _, bold_face = load_faces(regular, bold)
    max_width = CANVAS_WIDTH - 2 * MARGIN
    lines = wrap_words(SAMPLE_TEXT.split(), bold_face, max_width)
    n = len(lines)
    half_bold_top = MARGIN + LINE_HEIGHT * 2
    half_bold_bottom = half_bold_top + LINE_HEIGHT * n
    plain_top = half_bold_bottom + LINE_HEIGHT
    plain_bottom = plain_top + LINE_HEIGHT * n
    return (half_bold_top, half_bold_bottom), (plain_top, plain_bottom)


def test_render_pair_bolds_word_starts(font_pair: tuple[Path, Path]):
    regular, bold = font_pair
    image = render_preview("Test", regular, bold)

    assert image.width == CANVAS_WIDTH
    assert image.height > 0

    half_bold_rows, plain_rows = _paragraph_bands(regular, bold)
    half_bold_band = _non_white_pixels(
        image, (0, half_bold_rows[0], image.width, half_bold_rows[1])
    )
    plain_band = _non_white_pixels(
        image, (0, plain_rows[0], image.width, plain_rows[1])
    )
    assert half_bold_band > plain_band


def test_render_variable_uses_two_weights(variable_font: Path):
    image = render_preview("TestVar", variable_font, None)

    assert image.width == CANVAS_WIDTH
    assert image.height > 0

    half_bold_rows, plain_rows = _paragraph_bands(variable_font, None)
    half_bold_band = _non_white_pixels(
        image, (0, half_bold_rows[0], image.width, half_bold_rows[1])
    )
    plain_band = _non_white_pixels(
        image, (0, plain_rows[0], image.width, plain_rows[1])
    )
    assert half_bold_band > plain_band

    regular_face, bold_face = load_faces(variable_font, None)
    assert bytes(regular_face.getmask("a")) != bytes(bold_face.getmask("a"))


def test_static_font_without_bold_is_rejected(font_pair: tuple[Path, Path]):
    regular, _ = font_pair
    with pytest.raises(ValueError, match="not a variable font"):
        load_faces(regular, None)


def test_wrap_words_never_exceeds_width(font_pair: tuple[Path, Path]):
    _, bold = font_pair
    bold_face = ImageFont.truetype(str(bold), FONT_SIZE)
    sentence = "The quick brown fox jumps over the lazy dog again and again and again"
    words = sentence.split()
    max_width = CANVAS_WIDTH - 2 * MARGIN

    lines = wrap_words(words, bold_face, max_width)

    for line in lines:
        assert bold_face.getlength(" ".join(line)) <= max_width
    assert sum(lines, []) == words


def test_kitty_chunks_split_and_flags():
    png = b"x" * 10_000
    commands = kitty_chunks(png, columns=80, tmux=False)

    assert len(commands) == 4
    assert commands[0].startswith(b"\x1b_Gf=100,a=T,q=2,c=80,m=1;")
    last_control = commands[-1].split(b";", 1)[0]
    assert last_control.endswith(b"m=0")
    for command in commands[1:-1]:
        control = command.split(b";", 1)[0]
        assert b"f=100" not in control


def test_kitty_chunks_tmux_wrapping():
    png = b"x" * 10_000
    commands = kitty_chunks(png, columns=80, tmux=True)

    for command in commands:
        assert command.startswith(b"\x1bPtmux;\x1b\x1b_G")
        assert command.endswith(b"\x1b\x1b\\\x1b\\")


def test_supports_kitty_graphics():
    assert supports_kitty_graphics({"GHOSTTY_RESOURCES_DIR": "/x"})
    assert supports_kitty_graphics({"KITTY_WINDOW_ID": "1"})
    assert supports_kitty_graphics({"TERM": "xterm-kitty"})
    assert not supports_kitty_graphics({"TERM": "tmux-256color"})


def test_cli_preview_png_writes_file(variable_font: Path, tmp_path: Path, capsys):
    out = tmp_path / "p.png"
    assert main(["--preview", str(variable_font), "--png", str(out)]) == 0
    assert out.exists()
    assert "wrote" in capsys.readouterr().out


def test_cli_preview_directory_previews_each_candidate(tmp_path: Path, capsys):
    subdir = tmp_path / "fonts"
    subdir.mkdir()
    make_font(subdir / "A-Regular.ttf", "A", "Regular", 100)
    make_font(subdir / "A-Bold.ttf", "A", "Bold", 200)
    make_variable_font(subdir / "BVar.ttf", "BVar")

    out = tmp_path / "out.png"
    assert main(["--preview", str(tmp_path), "--png", str(out)]) == 0
    assert out.exists()
    assert out.with_stem("out-2").exists()


def test_cli_preview_rejects_other_modes(capsys):
    with pytest.raises(SystemExit):
        main(["--preview", "--all"])
    with pytest.raises(SystemExit):
        main(["--png", "x.png"])
