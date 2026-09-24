from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont

from halfbold.build import build_halfbold_font
from halfbold.settings import Settings


def shape(path: Path, text: str) -> str:
    order = TTFont(path).getGlyphOrder()
    font = hb.Font(hb.Face(path.read_bytes()))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"calt": True})
    return " ".join(order[info.codepoint] for info in buf.glyph_infos)


def test_first_half_of_each_word_is_bold(font_pair: tuple[Path, Path], tmp_path: Path):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out)

    assert shape(out, "hello") == "h.half e.half l.half l o"
    assert shape(out, "a be") == "a space b.half e"
    assert shape(out, "word word") == "w.half o.half r d space w.half o.half r d"


def test_words_longer_than_max_use_the_longest_rule(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(max_word_length=4))

    glyphs = shape(out, "abcdef").split()
    assert glyphs == ["a.half", "b.half", "c", "d", "e", "f"]


def bolded(path: Path, text: str) -> str:
    out = ""
    for glyph in shape(path, text).split():
        if glyph == "space":
            out += "*"
        elif glyph.endswith(".half"):
            out += glyph[0].upper()
        else:
            out += glyph[0].lower()
    return out


def test_camel_case_subwords_are_bolded_separately(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out)

    assert bolded(out, "toHaveBeenCalledExactlyOnceWith") == (
        "ToHAveBEenCALledEXACtlyONceWIth"
    )
    assert bolded(out, "HTTPServer") == "HTtpSERver"
    assert bolded(out, "XMLParser") == "XMlPARser"
    assert bolded(out, "parseHTMLNow") == "PARseHTmlNOw"
    assert bolded(out, "iPhone") == "iPHOne"
    assert bolded(out, "getX") == "GEtx"


def test_prose_words_are_unchanged_by_case(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out)

    assert bolded(out, "Hello World") == "HELlo*WORld"
    assert bolded(out, "HELLO WORLD") == "HELlo*WORld"
    assert bolded(out, "ABC") == "ABc"


def test_lone_capital_after_acronym_is_not_rebolded(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(min_word_length=1))

    assert bolded(out, "ABC") == "ABc"
    assert bolded(out, "getX") == "GEtX"
    assert bolded(out, "a") == "A"
