from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from halfbold.build import (
    BOLD_STYLE,
    BOLD_SUFFIX,
    Letters,
    bold_face_path,
    bold_prefix_length,
    build_bold_face,
    build_feature_code,
    build_halfbold_font,
    copy_bold_glyphs,
    rename_font,
    word_letter_glyphs,
)
from halfbold.cli import main
from halfbold.settings import Settings


def test_bold_prefix_is_half_rounded_up():
    assert [bold_prefix_length(n) for n in (2, 3, 4, 5, 6)] == [1, 2, 2, 3, 3]
    assert [bold_prefix_length(n, 0.25) for n in (2, 4, 8)] == [1, 1, 2]
    assert [bold_prefix_length(n, 1.0) for n in (2, 5)] == [2, 5]


def block(fea: str, name: str) -> list[str]:
    body = fea.split(f"lookup {name} {{\n", 1)[1].split(f"}} {name};", 1)[0]
    return [line.strip() for line in body.splitlines()]


def test_feature_code_honours_share_and_min_word_length():
    count = block(build_feature_code(Letters(["a"], ["A"]), 6, 0.25, 4), "COUNT")
    assert [line.count("lookup TO_HALF") for line in count] == [1, 1, 0, 0, 0, 0]
    unbolded = [line.startswith("sub @half' lookup TO_PLAIN") for line in count]
    assert unbolded == [False, False, False, True, True, True]


def test_feature_code_lists_longest_words_first():
    count = block(build_feature_code(Letters(["a"], ["A"]), 4), "COUNT")
    assert count == [
        "sub @half' @plain' lookup TO_HALF @plain' @plain';",
        "sub @half' @plain' lookup TO_HALF @plain';",
        "ignore sub @half' @plain;",
        "sub @half' lookup TO_PLAIN;",
    ]


def test_feature_code_marks_subword_starts_in_order():
    fea = build_feature_code(Letters(["a"], ["A"]), 3)
    assert block(fea, "MARK_STARTS") == [
        "ignore sub [@lower @lower_half] @lower';",
        "ignore sub [@upper @upper_half] @lower';",
        "ignore sub [@upper @upper_half] @upper' @upper;",
        "sub @lower' lookup TO_HALF;",
        "sub @upper' lookup TO_HALF @lower;",
        "ignore sub [@upper @upper_half] @upper';",
        "sub @upper' lookup TO_HALF;",
    ]
    assert fea.index("lookup MARK_STARTS;") < fea.index("lookup COUNT;")


def test_feature_code_compiles_for_fonts_with_one_case(font_pair: tuple[Path, Path]):
    for pick in (
        lambda found: Letters(found.lower, []),
        lambda found: Letters([], found.upper),
    ):
        regular, bold = TTFont(font_pair[0]), TTFont(font_pair[1])
        letters = pick(word_letter_glyphs(regular, bold))
        copy_bold_glyphs(regular, bold, letters.names)
        addOpenTypeFeaturesFromString(
            regular, build_feature_code(letters), tables=["GSUB"]
        )
        assert "calt" in {
            f.FeatureTag for f in regular["GSUB"].table.FeatureList.FeatureRecord
        }


def test_build_adds_bold_glyphs_and_calt(font_pair: tuple[Path, Path], tmp_path: Path):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    letters = build_halfbold_font(regular, bold, out)

    font = TTFont(out)
    assert len(letters) == 52
    glyph_order = font.getGlyphOrder()
    assert "a" + BOLD_SUFFIX in glyph_order
    assert "A" + BOLD_SUFFIX in glyph_order
    assert font["hmtx"]["a" + BOLD_SUFFIX][0] == 300
    features = {f.FeatureTag for f in font["GSUB"].table.FeatureList.FeatureRecord}
    assert "calt" in features
    assert font["name"].getBestFamilyName() == "Test Half"


def test_build_drops_apple_shaping_tables_that_hide_calt(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    aat_regular = tmp_path / "Aat-Regular.ttf"
    font = TTFont(regular)
    for tag in ("morx", "feat"):
        font[tag] = DefaultTable(tag)
        font[tag].data = b"\0" * 8
    font.save(aat_regular)

    out = tmp_path / "Aat-Half.ttf"
    build_halfbold_font(aat_regular, bold, out)

    tables = TTFont(out).keys()
    assert "morx" not in tables
    assert "feat" not in tables


def test_rename_gives_half_font_its_own_postscript_and_full_names(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    for path in (regular, bold):
        font = TTFont(path)
        name = font["name"]
        style = name.getDebugName(2)
        name.setName("Test NF", 1, 3, 1, 0x409)
        name.setName(f"Test NF {style}", 4, 3, 1, 0x409)
        name.setName(f"TestNF-{style}", 6, 3, 1, 0x409)
        name.setName(f"Test NF {style} 1.0", 3, 3, 1, 0x409)
        name.setName("Test Nerd Font", 16, 3, 1, 0x409)
        font.save(path)
    out = tmp_path / "Test-Half.ttf"
    build_halfbold_font(regular, bold, out)

    name = TTFont(out)["name"]
    assert name.getDebugName(16) == "Test Nerd Font Half"
    assert name.getDebugName(1) == "Test Nerd Font Half"
    assert name.getDebugName(6) == "TestNerdFontHalf-Regular"
    assert name.getDebugName(4) == "Test Nerd Font Half Regular"
    assert name.getDebugName(3) != "Test NF Regular 1.0"
    assert "TestNF-Regular" not in {r.toUnicode() for r in name.names}


def test_cli_defaults_output_next_to_regular(font_pair: tuple[Path, Path], capsys):
    regular, bold = font_pair
    assert main([str(regular), str(bold)]) == 0
    assert regular.with_name("Test-Regular-Half.ttf").exists()
    assert regular.with_name("Test-Regular-HalfBold.ttf").exists()
    assert "52 letter glyphs" in capsys.readouterr().out


def test_rejects_cff_like_font(font_pair: tuple[Path, Path], tmp_path: Path):
    regular, bold = font_pair
    font = TTFont(regular)
    del font["glyf"]
    broken = tmp_path / "broken.ttf"
    font.save(broken)
    try:
        build_halfbold_font(broken, bold, tmp_path / "x.ttf")
    except ValueError as err:
        assert "TrueType" in str(err)
    else:
        raise AssertionError("expected ValueError")


def test_half_font_is_regular_whichever_face_built_it(multi_weight_family: Path):
    plain = multi_weight_family / "Multi-Bold.ttf"
    font = TTFont(plain)
    font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0x40) | 0x20
    font["head"].macStyle |= 0x01
    font.save(plain)
    out = multi_weight_family / "Multi-Half.ttf"

    build_halfbold_font(plain, multi_weight_family / "Multi-Medium.ttf", out)

    half = TTFont(out)
    name = half["name"]
    assert name.getDebugName(1) == "Multi Half"
    assert name.getDebugName(16) == "Multi Half"
    assert name.getDebugName(2) == "Regular"
    assert name.getDebugName(17) == "Regular"
    assert name.getDebugName(4) == "Multi Half Regular"
    assert name.getDebugName(6) == "MultiHalf-Regular"
    assert half["OS/2"].usWeightClass == 400
    assert half["OS/2"].fsSelection & 0x40
    assert not half["OS/2"].fsSelection & 0x21
    assert not half["head"].macStyle & 0x03


def test_untouched_glyphs_keep_their_source_bounds(font_pair, tmp_path: Path):
    regular, bold = font_pair
    source = TTFont(regular)
    widened = source["glyf"]["a"].xMax + 7
    source["glyf"]["a"].xMax = widened
    source.recalcBBoxes = False
    nudged = tmp_path / "Nudged.ttf"
    source.save(nudged)
    assert TTFont(nudged)["glyf"]["a"].xMax == widened
    out = tmp_path / "Out-Half.ttf"

    build_halfbold_font(nudged, bold, out)

    assert TTFont(out)["glyf"]["a"].xMax == widened


def test_copied_glyphs_get_bounds_that_hold_their_outline(font_pair, tmp_path: Path):
    regular, bold = font_pair
    out = tmp_path / "Out-Half.ttf"

    build_halfbold_font(regular, bold, out)

    font = TTFont(out)
    glyf = font["glyf"]
    glyph_set = font.getGlyphSet()
    copied = [n for n in font.getGlyphOrder() if n.endswith(BOLD_SUFFIX)]
    assert copied
    for name in copied:
        pen = BoundsPen(glyph_set)
        glyph_set[name].draw(pen)
        assert pen.bounds is not None
        glyph = glyf[name]
        assert glyph.xMin <= pen.bounds[0]
        assert glyph.yMin <= pen.bounds[1]
        assert glyph.xMax >= pen.bounds[2]
        assert glyph.yMax >= pen.bounds[3]


def test_rename_as_bold_makes_the_half_bold_face(font_pair: tuple[Path, Path]):
    font = TTFont(font_pair[1])
    rename_font(font, BOLD_STYLE)
    name = font["name"]
    assert name.getDebugName(1) == "Test Half"
    assert name.getDebugName(2) == "Bold"
    assert name.getDebugName(4) == "Test Half Bold"
    assert name.getDebugName(6) == "TestHalf-Bold"
    assert name.getDebugName(16) == "Test Half"
    assert name.getDebugName(17) == "Bold"
    assert font["OS/2"].usWeightClass == 700
    assert font["OS/2"].fsSelection & 0x20
    assert not font["OS/2"].fsSelection & 0x40
    assert font["head"].macStyle & 0x01


def test_bold_face_is_the_bold_source_without_half_glyphs(
    font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = font_pair
    out = tmp_path / "Test-HalfBold.ttf"
    build_bold_face(regular, bold, out)

    font = TTFont(out)
    assert font["name"].getBestFamilyName() == "Test Half"
    assert font["name"].getDebugName(2) == "Bold"
    assert not any(g.endswith(BOLD_SUFFIX) for g in font.getGlyphOrder())
    assert font["hmtx"]["a"][0] == 300


def test_bold_face_from_variable_font_is_static_bold(
    variable_font: Path, tmp_path: Path
):
    out = tmp_path / "TestVar-HalfBold.ttf"
    build_bold_face(variable_font, None, out, Settings(bold_weight=700))

    font = TTFont(out)
    assert "fvar" not in font
    assert font["name"].getDebugName(2) == "Bold"
    assert font["OS/2"].usWeightClass == 700


def test_bold_face_from_variable_font_is_drawn_at_bold_weight(
    variable_font: Path, tmp_path: Path
):
    out = tmp_path / "TestVar-HalfBold.ttf"
    build_bold_face(variable_font, None, out, Settings(bold_weight=700))

    font = TTFont(out)
    glyph = font["glyf"]["a"]
    glyph.recalcBounds(font["glyf"])
    assert glyph.xMax == 200


def test_bold_face_keeps_the_source_ligatures(
    ligature_font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = ligature_font_pair
    out = tmp_path / "Liga-HalfBold.ttf"
    build_bold_face(regular, bold, out)

    gsub = TTFont(out)["GSUB"].table
    tags = {record.FeatureTag for record in gsub.FeatureList.FeatureRecord}
    assert "liga" in tags


def test_bold_face_path_sits_next_to_the_half_font(tmp_path: Path):
    assert (
        bold_face_path(tmp_path / "Inter-Half.ttf") == tmp_path / "Inter-HalfBold.ttf"
    )
