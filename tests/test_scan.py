import os
from pathlib import Path

from conftest import make_font, make_variable_font
from fontTools.ttLib import TTFont

from halfbold.cli import main
from halfbold.scan import (
    build_all,
    find_candidates,
    find_installed_half_families,
    font_kind,
)


def stamp_tables(path: Path, *, fixed_pitch: int = 0, serif_style: int = 0) -> None:
    font = TTFont(path)
    font["post"].isFixedPitch = fixed_pitch
    font["OS/2"].panose.bSerifStyle = serif_style
    font.save(path)


def fill_fonts_dir(fonts_dir: Path) -> None:
    fonts_dir.mkdir()
    make_font(fonts_dir / "Pair-Regular.ttf", "Pair", "Regular", 100)
    make_font(fonts_dir / "Pair-Bold.ttf", "Pair", "Bold", 200)
    make_font(fonts_dir / "Pair-Italic.ttf", "Pair", "Italic", 100)
    make_font(fonts_dir / "Lonely-Regular.ttf", "Lonely", "Regular", 100)
    make_variable_font(fonts_dir / "Var.ttf", "Var Variable")


def test_find_candidates_pairs_and_variables(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)

    found = {c.family: c for c in find_candidates(fonts)}

    assert set(found) == {"Pair", "Var"}
    assert found["Pair"].bold == fonts / "Pair-Bold.ttf"
    assert found["Var"].bold is None
    assert found["Var"].output == fonts / "Var-Half.ttf"


def test_build_all_skips_up_to_date_and_ignores_own_output(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)

    first = build_all(fonts)
    assert sorted(line.split()[0] for line in first) == ["built", "built"]
    assert (fonts / "Pair-Half.ttf").exists()
    assert (fonts / "Var-Half.ttf").exists()

    second = build_all(fonts)
    assert all(line.startswith("up to date") for line in second)
    assert {c.family for c in find_candidates(fonts)} == {"Pair", "Var"}


def test_build_all_rebuilds_when_source_is_newer(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    output = fonts / "Var-Half.ttf"
    old = output.stat().st_mtime
    os.utime(fonts / "Var.ttf", (old + 10, old + 10))

    report = build_all(fonts)

    assert any(line.startswith("built") and "Var-Half" in line for line in report)
    assert any(line.startswith("up to date") and "Pair-Half" in line for line in report)


def test_cli_all_dry_run(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)

    assert main(["--all", "--fonts-dir", str(fonts), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "would build Pair-Half.ttf" in out
    assert "would build Var-Half.ttf" in out
    assert not (fonts / "Pair-Half.ttf").exists()


def test_kind_from_tables(tmp_path: Path):
    path = make_font(tmp_path / "Plain-Regular.ttf", "Plain", "Regular", 100)

    stamp_tables(path, serif_style=4)
    assert font_kind(TTFont(path), "Plain") == "serif"

    stamp_tables(path, fixed_pitch=1)
    assert font_kind(TTFont(path), "Plain") == "mono"

    stamp_tables(path, serif_style=11)
    assert font_kind(TTFont(path), "Plain") == "sans"


def test_kind_from_name_when_tables_say_any(tmp_path: Path):
    path = make_font(tmp_path / "Plain-Regular.ttf", "Plain", "Regular", 100)
    font = TTFont(path)

    assert font_kind(font, "Fancy Serif") == "serif"
    assert font_kind(font, "Fancy Sans Serif") == "sans"
    assert font_kind(font, "JetBrainsMono Nerd Font") == "mono"
    assert font_kind(font, "Source Code Pro") == "mono"
    assert font_kind(font, "Pair") == "sans"


def test_candidates_carry_kind(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    stamp_tables(fonts / "Pair-Regular.ttf", fixed_pitch=1)

    found = {c.family: c for c in find_candidates(fonts)}

    assert found["Pair"].kind == "mono"
    assert found["Var"].kind == "sans"


def test_build_all_reports_kind(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    stamp_tables(fonts / "Pair-Regular.ttf", fixed_pitch=1)

    for line in build_all(fonts, dry_run=True):
        assert line.endswith("(sans)") or line.endswith("(mono)")
    assert any(
        line == "would build Pair-Half.ttf  <- Pair (mono)"
        for line in build_all(fonts, dry_run=True)
    )


def test_installed_half_families(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)

    assert find_installed_half_families(fonts) == {"Pair Half", "Var Half"}
