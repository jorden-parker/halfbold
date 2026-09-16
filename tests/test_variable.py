from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from halfbold.build import BOLD_SUFFIX, build_halfbold_font
from halfbold.cli import main


def test_variable_font_is_instanced_at_two_weights(variable_font: Path, tmp_path: Path):
    out = tmp_path / "TestVar-Half.ttf"
    build_halfbold_font(variable_font, None, out)

    font = TTFont(out)
    assert "fvar" not in font
    glyf = font["glyf"]
    plain = glyf["a"].getCoordinates(glyf)[0]
    bold = glyf["a" + BOLD_SUFFIX].getCoordinates(glyf)[0]
    assert max(x for x, _ in plain) == 100
    assert max(x for x, _ in bold) == 200
    assert font["name"].getBestFamilyName() == "TestVar Half"


def test_static_font_without_bold_is_rejected(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, _ = font_pair
    with pytest.raises(ValueError, match="not a variable font"):
        build_halfbold_font(regular, None, tmp_path / "x.ttf")


def test_cli_accepts_single_variable_font(variable_font: Path, capsys):
    assert main([str(variable_font)]) == 0
    assert variable_font.with_name("TestVar-Half.ttf").exists()
    assert "26 letter glyphs" in capsys.readouterr().out
