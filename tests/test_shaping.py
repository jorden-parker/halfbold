from pathlib import Path

import pytest
import uharfbuzz as hb
from fontTools.ttLib import TTFont

from halfbold.build import build_halfbold_font
from halfbold.cli import main
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


def test_short_subwords_stay_plain_at_a_higher_minimum(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(min_word_length=5))

    assert bolded(out, "toHaveBeenCalledExactlyOnceWith") == (
        "tohavebeenCALledEXACtlyoncewith"
    )
    assert bolded(out, "HTTPServer") == "httpSERver"


def test_high_bold_share_keeps_subword_boundaries(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(bold_share=0.8))

    assert bolded(out, "getXFoo") == "GETxFOO"
    assert bolded(out, "abcDef") == "ABCDEF"


def test_source_ligatures_survive_and_bold_letters_win(
    ligature_font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = ligature_font_pair
    out = tmp_path / "Liga-Half.ttf"
    build_halfbold_font(regular, bold, out)

    assert shape(out, "->") == "arrow"
    assert shape(out, "first") == "f.half i.half r.half s t"
    assert shape(out, "toffi") == "t.half o.half f.half f_i"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello", "HEllO"),
        ("word word", "WorD*WorD"),
        ("a be", "a*Be"),
        ("reading", "REadiNG"),
        ("the", "ThE"),
        ("toHaveBeen", "ToHavEBeeN"),
    ],
)
def test_bold_ends_two_bolds_the_start_and_end_of_each_word(
    font_pair: tuple[Path, Path], tmp_path: Path, text: str, expected: str
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(bold_ends=2))

    assert bolded(out, text) == expected


def test_bold_ends_two_keeps_long_words_start_only(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out, Settings(max_word_length=4, bold_ends=2))

    assert bolded(out, "abcd") == "AbcD"
    assert bolded(out, "abcdef") == "ABcdef"


def test_bold_ends_flag_reaches_the_built_font(font_pair: tuple[Path, Path]):
    regular, bold = font_pair
    arguments = ["--bold-share", "0.5", "--min-word-length", "2", "--bold-ends", "2"]
    assert main([str(regular), str(bold), *arguments]) == 0

    assert bolded(regular.with_name("Test-Regular-Half.ttf"), "hello") == "HEllO"
