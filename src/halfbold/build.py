import math
from dataclasses import dataclass
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from halfbold.settings import (
    BOLD_SHARE,
    MAX_WORD_LENGTH,
    MIN_WORD_LENGTH,
    Settings,
)

BOLD_SUFFIX = ".half"
STYLE_SUFFIX = "Half"


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
    )
    addOpenTypeFeaturesFromString(regular, fea, tables=["GSUB"])
    rename_font(regular)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    regular.save(output_path)
    return letters.names


def load_font_pair(
    regular_path: Path,
    bold_path: Path | None,
    regular_weight: float,
    bold_weight: float,
) -> tuple[TTFont, TTFont]:
    if bold_path is None:
        variable = TTFont(regular_path)
        require_truetype_outlines(variable, regular_path)
        if "fvar" not in variable:
            raise ValueError(
                f"{regular_path} is not a variable font; pass a Bold file as well"
            )
        regular = instance_at_weight(TTFont(regular_path), regular_weight)
        bold = instance_at_weight(TTFont(regular_path), bold_weight)
        return regular, bold
    regular = TTFont(regular_path)
    bold = TTFont(bold_path)
    require_truetype_outlines(regular, regular_path)
    require_truetype_outlines(bold, bold_path)
    return regular, bold


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
    regular_cmap = regular.getBestCmap()
    bold_glyphs = set(bold.getGlyphOrder())
    lower: list[str] = []
    upper: list[str] = []
    seen: set[str] = set()
    for codepoint, name in sorted(regular_cmap.items()):
        char = chr(codepoint)
        if not char.isalpha() or name not in bold_glyphs or name in seen:
            continue
        seen.add(name)
        (upper if char.isupper() else lower).append(name)
    return Letters(lower, upper)


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


def bold_prefix_length(word_length: int, bold_share: float = BOLD_SHARE) -> int:
    return min(word_length, max(1, math.ceil(word_length * bold_share)))


def build_feature_code(
    letters: Letters,
    max_word_length: int = MAX_WORD_LENGTH,
    bold_share: float = BOLD_SHARE,
    min_word_length: int = MIN_WORD_LENGTH,
) -> str:
    lengths = range(max_word_length, max(min_word_length, 1) - 1, -1)
    lines = [
        f"@lower = [{' '.join(letters.lower)}];",
        f"@upper = [{' '.join(letters.upper)}];",
        f"@lower_half = [{' '.join(half_name(n) for n in letters.lower)}];",
        f"@upper_half = [{' '.join(half_name(n) for n in letters.upper)}];",
        "@plain = [@lower @upper];",
        "@half = [@lower_half @upper_half];",
        "@letter = [@plain @half];",
        "lookup TO_HALF {",
        "  sub @plain by @half;",
        "} TO_HALF;",
        "feature calt {",
        "  ignore sub @letter @lower';",
        "  ignore sub [@upper @upper_half] @upper' @upper;",
    ]
    for length in lengths:
        lines.append(subword_rule(["@lower"] * length, bold_share))
    for length in lengths:
        if length > 1:
            cases = ["@upper"] + ["@lower"] * (length - 1)
            lines.append(subword_rule(cases, bold_share))
    for length in lengths:
        lines.append(subword_rule(["@upper"] * length, bold_share, "@upper @lower"))
    lines.append("  ignore sub [@upper @upper_half] @upper';")
    for length in lengths:
        lines.append(subword_rule(["@upper"] * length, bold_share))
    lines.append("} calt;")
    return "\n".join(lines) + "\n"


def half_name(name: str) -> str:
    return name + BOLD_SUFFIX


def subword_rule(cases: list[str], bold_share: float, lookahead: str = "") -> str:
    prefix = bold_prefix_length(len(cases), bold_share)
    marked = " ".join(f"{case}' lookup TO_HALF" for case in cases[:prefix])
    rest = " ".join([*cases[prefix:], *lookahead.split()])
    return f"  sub {marked} {rest};".replace(" ;", ";")


def rename_font(font: TTFont) -> None:
    name_table = font["name"]
    family = name_table.getBestFamilyName()
    base_family = " ".join(part for part in family.split() if part != "Variable")
    new_family = f"{base_family} {STYLE_SUFFIX}"
    style = name_table.getDebugName(17) or name_table.getDebugName(2) or "Regular"
    postscript = f"{new_family.replace(' ', '')}-{style.replace(' ', '')}"
    full_name = f"{new_family} {style}"
    for record in name_table.names:
        if record.nameID in (1, 16):
            record.string = new_family
        elif record.nameID == 4:
            record.string = full_name
        elif record.nameID == 6:
            record.string = postscript
        elif record.nameID == 3:
            record.string = f"{postscript};{STYLE_SUFFIX}"
