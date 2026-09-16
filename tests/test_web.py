from pathlib import Path

import pytest
from test_scan import fill_fonts_dir

from halfbold.cli import main
from halfbold.scan import build_all
from halfbold.web import get_web_fonts, set_web_font

CSS = """:root {
  --halfbold-sans: "Inter Half";
  --halfbold-serif: "Source Serif 4 Half";
  --halfbold-mono: "JetBrainsMono Nerd Font Half";
}

* { font-family: var(--halfbold-sans), sans-serif !important; }
"""


def test_set_web_font_rewrites_only_its_line(tmp_path: Path):
    css_path = tmp_path / "halfbold.css"
    css_path.write_text(CSS)

    set_web_font(css_path, "serif", "Pair Half")

    lines = css_path.read_text().splitlines()
    assert lines[2] == '  --halfbold-serif: "Pair Half";'
    assert lines[1] == '  --halfbold-sans: "Inter Half";'
    assert lines[3] == '  --halfbold-mono: "JetBrainsMono Nerd Font Half";'
    expected_last = "* { font-family: var(--halfbold-sans), sans-serif !important; }"
    assert lines[-1] == expected_last


def test_set_web_font_missing_line_raises(tmp_path: Path):
    css_path = tmp_path / "halfbold.css"
    incomplete_css = (
        ':root {\n  --halfbold-sans: "Inter Half";\n'
        '  --halfbold-serif: "Source Serif 4 Half";\n}\n'
    )
    css_path.write_text(incomplete_css)
    before = css_path.read_text()

    with pytest.raises(ValueError, match="--halfbold-mono"):
        set_web_font(css_path, "mono", "Pair Half")

    assert css_path.read_text() == before


def test_cli_sets_active_fonts(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)

    result = main(
        [
            "--sans",
            "Pair",
            "--mono",
            "Var Half",
            "--fonts-dir",
            str(fonts),
            "--css",
            str(css),
        ]
    )

    assert result == 0
    text = css.read_text()
    assert '--halfbold-sans: "Pair Half";' in text
    assert '--halfbold-mono: "Var Half";' in text
    out = capsys.readouterr().out
    assert "sans   Pair Half" in out


def test_cli_rejects_unknown_family(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)
    before = css.read_text()

    result = main(["--serif", "Nope", "--fonts-dir", str(fonts), "--css", str(css)])

    assert result == 1
    out = capsys.readouterr().out
    assert "'Nope Half' is not installed" in out
    assert "Pair Half" in out
    assert css.read_text() == before


def test_cli_web_flags_exclusive_with_all():
    with pytest.raises(SystemExit):
        main(["--sans", "Pair", "--all"])


def test_get_web_fonts_reads_all_slots(tmp_path: Path):
    css_path = tmp_path / "halfbold.css"
    css_path.write_text(CSS)

    assert get_web_fonts(css_path) == {
        "sans": "Inter Half",
        "serif": "Source Serif 4 Half",
        "mono": "JetBrainsMono Nerd Font Half",
    }


def test_get_web_fonts_missing_line_raises(tmp_path: Path):
    css_path = tmp_path / "halfbold.css"
    incomplete_css = (
        ':root {\n  --halfbold-sans: "Inter Half";\n'
        '  --halfbold-serif: "Source Serif 4 Half";\n}\n'
    )
    css_path.write_text(incomplete_css)

    with pytest.raises(ValueError, match="--halfbold-mono"):
        get_web_fonts(css_path)
