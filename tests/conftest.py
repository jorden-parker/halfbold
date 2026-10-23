from pathlib import Path

import pytest
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
LIGATURE_FEATURES = """
languagesystem DFLT dflt;
languagesystem latn dflt;
feature liga {
  sub f i by f_i;
} liga;
feature calt {
  script DFLT;
  sub hyphen greater by arrow;
} calt;
"""


def box_glyph(width: int):
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((width, 0))
    pen.lineTo((width, 500))
    pen.lineTo((0, 500))
    pen.closePath()
    return pen.glyph()


def make_font(
    path: Path,
    family: str,
    style: str,
    stem: int,
    features: str = "",
    weight: int = 400,
    glyph_prefix: str = "",
    letter_glyphs: dict[str, str] | None = None,
) -> Path:
    glyph_for = {c: glyph_prefix + c for c in LETTERS} | (letter_glyphs or {})
    names = [".notdef", "space", *(glyph_for[c] for c in LETTERS)]
    cmap = {ord(" "): "space", **{ord(c): glyph_for[c] for c in LETTERS}}
    if features:
        names += ["hyphen", "greater", "arrow", "f_i"]
        cmap |= {ord("-"): "hyphen", ord(">"): "greater"}
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf({n: box_glyph(stem if n != "space" else 0) for n in names})
    builder.setupHorizontalMetrics({n: (stem + 100, 0) for n in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": family,
            "styleName": style,
            "typographicSubfamily": style,
            "fullName": f"{family} {style}",
            "psName": f"{family}-{style}",
        }
    )
    builder.setupOS2(usWeightClass=weight)
    builder.setupPost()
    if features:
        addOpenTypeFeaturesFromString(builder.font, features, tables=["GSUB"])
    builder.save(path)
    return path


def make_collection(path: Path, faces: list[Path]) -> Path:
    collection = TTCollection()
    collection.fonts = [TTFont(face) for face in faces]
    collection.save(path)
    return path


@pytest.fixture
def font_pair(tmp_path: Path) -> tuple[Path, Path]:
    regular = make_font(tmp_path / "Test-Regular.ttf", "Test", "Regular", 100)
    bold = make_font(tmp_path / "Test-Bold.ttf", "Test", "Bold", 200)
    return regular, bold


@pytest.fixture
def ligature_font_pair(tmp_path: Path) -> tuple[Path, Path]:
    regular = make_font(
        tmp_path / "Liga-Regular.ttf", "Liga", "Regular", 100, LIGATURE_FEATURES
    )
    bold = make_font(tmp_path / "Liga-Bold.ttf", "Liga", "Bold", 200, LIGATURE_FEATURES)
    return regular, bold


def make_variable_font(path: Path, family: str) -> Path:
    names = [".notdef", "space", *LETTERS]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(" "): "space", **{ord(c): c for c in LETTERS}})
    builder.setupGlyf({n: box_glyph(100 if n != "space" else 0) for n in names})
    builder.setupHorizontalMetrics({n: (200, 0) for n in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": family, "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    builder.setupFvar([("wght", 400, 400, 700, "Weight")], [])
    wider = [(0, 0), (100, 0), (100, 0), (0, 0), None, None, None, None]
    builder.setupGvar(
        {n: [TupleVariation({"wght": (0, 1, 1)}, wider)] for n in names if n != "space"}
    )
    builder.save(path)
    return path


@pytest.fixture
def variable_font(tmp_path: Path) -> Path:
    return make_variable_font(tmp_path / "TestVar.ttf", "TestVar")


MULTI_WEIGHTS = {"Light": 300, "Regular": 400, "Medium": 500, "Bold": 700}


@pytest.fixture
def multi_weight_family(tmp_path: Path) -> Path:
    fonts = tmp_path / "multi"
    fonts.mkdir()
    for style, weight in MULTI_WEIGHTS.items():
        make_font(
            fonts / f"Multi-{style}.ttf", "Multi", style, weight // 2, weight=weight
        )
    make_font(fonts / "Multi-Italic.ttf", "Multi", "Italic", 200, weight=400)
    make_font(fonts / "Solo-Regular.ttf", "Solo", "Regular", 200)
    return fonts
