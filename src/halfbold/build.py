import math
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

BOLD_SUFFIX = ".half"
MAX_WORD_LENGTH = 20
STYLE_SUFFIX = "Half"


def build_halfbold_font(
    regular_path: Path,
    bold_path: Path,
    output_path: Path,
    max_word_length: int = MAX_WORD_LENGTH,
) -> list[str]:
    regular = TTFont(regular_path)
    bold = TTFont(bold_path)
    require_truetype_outlines(regular, regular_path)
    require_truetype_outlines(bold, bold_path)

    letters = word_letter_glyphs(regular, bold)
    if not letters:
        raise ValueError("no letter glyphs shared between the two fonts")

    copy_bold_glyphs(regular, bold, letters)
    fea = build_feature_code(letters, max_word_length)
    addOpenTypeFeaturesFromString(regular, fea, tables=["GSUB"])
    rename_font(regular)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    regular.save(output_path)
    return letters


def require_truetype_outlines(font: TTFont, path: Path) -> None:
    if "glyf" not in font:
        raise ValueError(f"{path} has no TrueType outlines (CFF/OTF is not supported)")


def word_letter_glyphs(regular: TTFont, bold: TTFont) -> list[str]:
    regular_cmap = regular.getBestCmap()
    bold_glyphs = set(bold.getGlyphOrder())
    names: list[str] = []
    seen: set[str] = set()
    for codepoint, name in sorted(regular_cmap.items()):
        if not chr(codepoint).isalpha():
            continue
        if name in bold_glyphs and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def copy_bold_glyphs(regular: TTFont, bold: TTFont, letters: list[str]) -> None:
    bold_glyph_set = bold.getGlyphSet()
    glyf = regular["glyf"]
    hmtx = regular["hmtx"]
    bold_hmtx = bold["hmtx"]
    new_order = regular.getGlyphOrder() + [name + BOLD_SUFFIX for name in letters]
    regular.setGlyphOrder(new_order)
    glyf.glyphOrder = new_order
    for name in letters:
        new_name = name + BOLD_SUFFIX
        pen = DecomposingRecordingPen(bold_glyph_set)
        bold_glyph_set[name].draw(pen)
        tt_pen = TTGlyphPen(None)
        pen.replay(tt_pen)
        glyf[new_name] = tt_pen.glyph()
        hmtx[new_name] = bold_hmtx[name]


def bold_prefix_length(word_length: int) -> int:
    return math.ceil(word_length / 2)


def build_feature_code(letters: list[str], max_word_length: int) -> str:
    plain = " ".join(letters)
    half = " ".join(name + BOLD_SUFFIX for name in letters)
    lines = [
        f"@plain = [{plain}];",
        f"@half = [{half}];",
        "lookup TO_HALF {",
        "  sub @plain by @half;",
        "} TO_HALF;",
        "feature calt {",
        "  ignore sub [@plain @half] @plain';",
    ]
    for length in range(max_word_length, 1, -1):
        prefix = bold_prefix_length(length)
        marked = " ".join("@plain' lookup TO_HALF" for _ in range(prefix))
        rest = " ".join("@plain" for _ in range(length - prefix))
        lines.append(f"  sub {marked} {rest};".replace("  ;", ";").rstrip())
    lines.append("} calt;")
    return "\n".join(lines) + "\n"


def rename_font(font: TTFont) -> None:
    name_table = font["name"]
    family = name_table.getBestFamilyName()
    new_family = f"{family} {STYLE_SUFFIX}"
    for record in name_table.names:
        if record.nameID in (1, 16):
            record.string = new_family
        elif record.nameID in (3, 4):
            record.string = record.toUnicode().replace(family, new_family)
        elif record.nameID == 6:
            record.string = record.toUnicode().replace(
                family.replace(" ", ""), new_family.replace(" ", "")
            )
