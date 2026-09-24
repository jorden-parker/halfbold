from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont

from halfbold.build import (
    BOLD_SUFFIX,
    Letters,
    bold_prefix_length,
    build_feature_code,
    build_halfbold_font,
    copy_bold_glyphs,
    word_letter_glyphs,
)
from halfbold.cli import main


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
