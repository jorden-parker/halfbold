from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def box_glyph(width: int):
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((width, 0))
    pen.lineTo((width, 500))
    pen.lineTo((0, 500))
    pen.closePath()
    return pen.glyph()


def make_font(path: Path, family: str, style: str, stem: int) -> Path:
    names = [".notdef", "space", *LETTERS]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(" "): "space", **{ord(c): c for c in LETTERS}})
    builder.setupGlyf({n: box_glyph(stem if n != "space" else 0) for n in names})
    builder.setupHorizontalMetrics({n: (stem + 100, 0) for n in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": family, "styleName": style})
    builder.setupOS2()
    builder.setupPost()
    builder.save(path)
    return path


@pytest.fixture
def font_pair(tmp_path: Path) -> tuple[Path, Path]:
    regular = make_font(tmp_path / "Test-Regular.ttf", "Test", "Regular", 100)
    bold = make_font(tmp_path / "Test-Bold.ttf", "Test", "Bold", 200)
    return regular, bold
