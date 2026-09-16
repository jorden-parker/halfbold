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
