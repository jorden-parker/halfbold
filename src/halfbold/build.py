import math
from dataclasses import dataclass
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.feaLib.lexer import Lexer
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from halfbold.collection import open_font
from halfbold.gsub import has_scripted_gsub, prepend_lookups
from halfbold.settings import (
    BOLD_ENDS,
    BOLD_SHARE,
    MAX_WORD_LENGTH,
    MIN_WORD_LENGTH,
    Settings,
)

BOLD_SUFFIX = ".half"
STYLE_SUFFIX = "Half"
PLAIN_STYLE = "Regular"
PLAIN_WEIGHT = 400
BOLD_STYLE = "Bold"
BOLD_WEIGHT_CLASS = 700
FS_ITALIC = 0x01
FS_BOLD = 0x20
FS_REGULAR = 0x40
MAC_BOLD = 0x01
MAC_ITALIC = 0x02
APPLE_SHAPING_TABLES = ("morx", "mort", "feat")


@dataclass(frozen=True)
class Letters:
    lower: list[str]
    upper: list[str]

    @property
    def names(self) -> list[str]:
        return self.lower + self.upper


def build_halfbold_font(
    regular_path: Path,
    bold_path: Path | None,
    output_path: Path,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or Settings()
    regular, bold = load_font_pair(
        regular_path, bold_path, settings.regular_weight, settings.bold_weight
    )

    letters = word_letter_glyphs(regular, bold)
    if not letters.names:
        raise ValueError("no letter glyphs shared between the two fonts")

    copy_bold_glyphs(regular, bold, letters.names)
    fea = build_feature_code(
        letters,
        settings.max_word_length,
        settings.bold_share,
        settings.min_word_length,
        settings.bold_ends,
    )
    add_calt_feature(regular, fea)
    drop_apple_shaping(regular)
    rename_font(regular)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    regular.recalcBBoxes = False
    regular.save(output_path)
    return letters.names


def build_bold_face(
    regular_path: Path,
    bold_path: Path | None,
    output_path: Path,
    settings: Settings | None = None,
) -> None:
    settings = settings or Settings()
    bold = load_bold_source(regular_path, bold_path, settings.bold_weight)
    rename_font(bold, BOLD_STYLE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bold.recalcBBoxes = False
    bold.save(output_path)


def bold_face_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}Bold{output_path.suffix}")


def add_calt_feature(font: TTFont, fea: str) -> None:
    original = font["GSUB"] if has_scripted_gsub(font) else None
    if original is not None:
        del font["GSUB"]
    addOpenTypeFeaturesFromString(font, fea, tables=["GSUB"])
    if original is not None:
        prepend_lookups(original.table, font["GSUB"].table, "calt")
        font["GSUB"] = original


def drop_apple_shaping(font: TTFont) -> None:
    for tag in APPLE_SHAPING_TABLES:
        if tag in font:
            del font[tag]


def load_font_pair(
    regular_path: Path,
    bold_path: Path | None,
    regular_weight: float,
    bold_weight: float,
) -> tuple[TTFont, TTFont]:
    regular = load_plain_source(regular_path, bold_path, regular_weight)
    bold = load_bold_source(regular_path, bold_path, bold_weight)
    return regular, bold


def load_plain_source(
    regular_path: Path, bold_path: Path | None, regular_weight: float
) -> TTFont:
    if bold_path is None:
        return load_variable_instance(regular_path, regular_weight)
    regular = open_font(regular_path)
    require_truetype_outlines(regular, regular_path)
    return regular


def load_bold_source(
    regular_path: Path, bold_path: Path | None, bold_weight: float
) -> TTFont:
    if bold_path is None:
        return load_variable_instance(regular_path, bold_weight)
    bold = open_font(bold_path)
    require_truetype_outlines(bold, bold_path)
    return bold


def load_variable_instance(path: Path, weight: float) -> TTFont:
    variable = open_font(path)
    require_truetype_outlines(variable, path)
    if "fvar" not in variable:
        raise ValueError(f"{path} is not a variable font; pass a Bold file as well")
    return instance_at_weight(variable, weight)


def instance_at_weight(font: TTFont, weight: float) -> TTFont:
    location = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes}
    if "wght" not in location:
        raise ValueError("variable font has no wght axis")
    location["wght"] = weight
    return instancer.instantiateVariableFont(font, location, inplace=True)


def require_truetype_outlines(font: TTFont, path: Path) -> None:
    if "glyf" not in font:
        raise ValueError(f"{path} has no TrueType outlines (CFF/OTF is not supported)")


def word_letter_glyphs(regular: TTFont, bold: TTFont) -> Letters:
    counterparts = bold_counterparts(regular, bold)
    lower: list[str] = []
    upper: list[str] = []
    seen: set[str] = set()
    for codepoint, name in sorted(regular.getBestCmap().items()):
        char = chr(codepoint)
        if not char.isalpha() or name not in counterparts or name in seen:
            continue
        seen.add(name)
        (upper if char.isupper() else lower).append(name)
    require_fea_glyph_names(lower + upper)
    return Letters(lower, upper)


def bold_counterparts(regular: TTFont, bold: TTFont) -> dict[str, str]:
    bold_cmap = bold.getBestCmap()
    counterparts: dict[str, str] = {}
    for codepoint, name in sorted(regular.getBestCmap().items()):
        if codepoint in bold_cmap:
            counterparts.setdefault(name, bold_cmap[codepoint])
    return counterparts


def copy_bold_glyphs(regular: TTFont, bold: TTFont, letters: list[str]) -> None:
    counterparts = bold_counterparts(regular, bold)
    bold_glyph_set = bold.getGlyphSet()
    glyf = regular["glyf"]
    hmtx = regular["hmtx"]
    bold_hmtx = bold["hmtx"]
    new_order = regular.getGlyphOrder() + [name + BOLD_SUFFIX for name in letters]
    regular.setGlyphOrder(new_order)
    glyf.glyphOrder = new_order
    for name in letters:
        bold_name = counterparts[name]
        new_name = name + BOLD_SUFFIX
        pen = DecomposingRecordingPen(bold_glyph_set)
        bold_glyph_set[bold_name].draw(pen)
        tt_pen = TTGlyphPen(None)
        pen.replay(tt_pen)
        glyph = tt_pen.glyph()
        glyph.recalcBounds(glyf)
        glyf[new_name] = glyph
        hmtx[new_name] = bold_hmtx[bold_name]


def bold_prefix_length(word_length: int, bold_share: float = BOLD_SHARE) -> int:
    return min(word_length, max(1, math.ceil(word_length * bold_share)))


def bold_split(
    word_length: int, bold_share: float = BOLD_SHARE, bold_ends: int = BOLD_ENDS
) -> tuple[int, int]:
    total = bold_prefix_length(word_length, bold_share)
    if bold_ends == 1:
        return total, 0
    start = math.ceil(total / 2)
    return start, total - start


def require_fea_glyph_names(names: list[str]) -> None:
    unusable = [name for name in names if not is_fea_glyph_name(name)]
    if unusable:
        listed = ", ".join(repr(name) for name in unusable)
        raise ValueError(f"letter glyph names cannot be used in feature code: {listed}")


def is_fea_glyph_name(name: str) -> bool:
    return (
        bool(name)
        and name[0] in Lexer.CHAR_NAME_START_
        and name[0] != "\\"
        and all(char in Lexer.CHAR_NAME_CONTINUATION_ for char in name[1:])
        and name != "include"
    )


def build_feature_code(
    letters: Letters,
    max_word_length: int = MAX_WORD_LENGTH,
    bold_share: float = BOLD_SHARE,
    min_word_length: int = MIN_WORD_LENGTH,
    bold_ends: int = BOLD_ENDS,
) -> str:
    require_fea_glyph_names(letters.names)
    lines = [
        f"@lower = [{' '.join(letters.lower)}];",
        f"@upper = [{' '.join(letters.upper)}];",
        f"@lower_half = [{' '.join(half_name(n) for n in letters.lower)}];",
        f"@upper_half = [{' '.join(half_name(n) for n in letters.upper)}];",
        "@plain = [@lower @upper];",
        "@half = [@lower_half @upper_half];",
        "lookup TO_HALF {",
        "  sub @plain by @half;",
        "} TO_HALF;",
        "lookup TO_PLAIN {",
        "  sub @half by @plain;",
        "} TO_PLAIN;",
        "lookup MARK_STARTS {",
        *start_rules(bool(letters.lower), bool(letters.upper)),
        "} MARK_STARTS;",
        "lookup COUNT {",
        *count_rules(max_word_length, bold_share, min_word_length, bold_ends),
        "} COUNT;",
        "feature calt {",
        "  lookup MARK_STARTS;",
        "  lookup COUNT;",
        "} calt;",
    ]
    return "\n".join(lines) + "\n"


def half_name(name: str) -> str:
    return name + BOLD_SUFFIX


def start_rules(has_lower: bool, has_upper: bool) -> list[str]:
    rules: list[str] = []
    if has_lower:
        rules.append("  ignore sub [@lower @lower_half] @lower';")
    if has_lower and has_upper:
        rules.append("  ignore sub [@upper @upper_half] @lower';")
    if has_upper:
        rules.append("  ignore sub [@upper @upper_half] @upper' @upper;")
    if has_lower:
        rules.append("  sub @lower' lookup TO_HALF;")
    if has_lower and has_upper:
        rules.append("  sub @upper' lookup TO_HALF @lower;")
    if has_upper:
        rules.append("  ignore sub [@upper @upper_half] @upper';")
        rules.append("  sub @upper' lookup TO_HALF;")
    return rules


def count_rules(
    max_word_length: int,
    bold_share: float,
    min_word_length: int,
    bold_ends: int = BOLD_ENDS,
) -> list[str]:
    rules: list[str] = []
    if bold_ends == 2:
        rules.append(long_word_rule(max_word_length, bold_share))
    for length in range(max_word_length, 0, -1):
        rule = length_rule(length, bold_share, min_word_length, bold_ends)
        if rule is not None:
            rules.append(rule)
    return rules


def length_rule(
    length: int, bold_share: float, min_word_length: int, bold_ends: int
) -> str | None:
    rest = " ".join(["@plain"] * (length - 1))
    if length < min_word_length:
        return f"  sub @half' lookup TO_PLAIN {rest};".replace(" ;", ";")
    start, end = bold_split(length, bold_share, bold_ends)
    if start == 1 and end == 0:
        return f"  ignore sub @half' {rest};" if length > 1 else None
    return sub_rule(bold_marks(length, start, end))


def long_word_rule(max_word_length: int, bold_share: float) -> str:
    start, _ = bold_split(max_word_length, bold_share, 1)
    if start == 1:
        return f"  ignore sub @half' {' '.join(['@plain'] * max_word_length)};"
    return sub_rule(bold_marks(max_word_length, start, 0) + ["@plain"])


def bold_marks(length: int, start: int, end: int) -> list[str]:
    return (
        ["@plain' lookup TO_HALF"] * (start - 1)
        + ["@plain'"] * (length - start - end)
        + ["@plain' lookup TO_HALF"] * end
    )


def sub_rule(marked: list[str]) -> str:
    return f"  sub @half' {' '.join(marked)};"


def rename_font(font: TTFont, style: str = PLAIN_STYLE) -> None:
    name_table = font["name"]
    family = name_table.getBestFamilyName()
    base_family = " ".join(part for part in family.split() if part != "Variable")
    new_family = f"{base_family} {STYLE_SUFFIX}"
    postscript = f"{new_family.replace(' ', '')}-{style}"
    names = {
        1: new_family,
        16: new_family,
        2: style,
        17: style,
        4: f"{new_family} {style}",
        6: postscript,
        3: f"{postscript};{STYLE_SUFFIX}",
    }
    for record in name_table.names:
        if record.nameID in names:
            record.string = names[record.nameID]
    for source, twin in ((1, 16), (2, 17)):
        for record in [r for r in name_table.names if r.nameID == source]:
            name_table.setName(
                names[twin], twin, record.platformID, record.platEncID, record.langID
            )
    for name_id, value in names.items():
        if not name_table.getDebugName(name_id):
            name_table.setName(value, name_id, 3, 1, 0x409)
    for name_id in (21, 22):
        name_table.removeNames(name_id)
    set_face_flags(font, style)


def set_face_flags(font: TTFont, style: str) -> None:
    os2 = font["OS/2"]
    head = font["head"]
    if style == BOLD_STYLE:
        os2.usWeightClass = BOLD_WEIGHT_CLASS
        os2.fsSelection = (os2.fsSelection & ~(FS_REGULAR | FS_ITALIC)) | FS_BOLD
        head.macStyle = (head.macStyle & ~MAC_ITALIC) | MAC_BOLD
    else:
        os2.usWeightClass = PLAIN_WEIGHT
        os2.fsSelection = (os2.fsSelection & ~(FS_BOLD | FS_ITALIC)) | FS_REGULAR
        head.macStyle &= ~(MAC_BOLD | MAC_ITALIC)
