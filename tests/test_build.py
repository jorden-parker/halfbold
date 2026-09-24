from pathlib import Path

from fontTools.ttLib import TTFont

from halfbold.build import (
    BOLD_SUFFIX,
    Letters,
    bold_prefix_length,
    build_feature_code,
    build_halfbold_font,
)
from halfbold.cli import main


def test_bold_prefix_is_half_rounded_up():
    assert [bold_prefix_length(n) for n in (2, 3, 4, 5, 6)] == [1, 2, 2, 3, 3]
    assert [bold_prefix_length(n, 0.25) for n in (2, 4, 8)] == [1, 1, 2]
    assert [bold_prefix_length(n, 1.0) for n in (2, 5)] == [2, 5]


def lowercase_rules(fea: str) -> list[str]:
    return [
        line
        for line in fea.splitlines()
        if line.startswith("  sub @lower'") and "@upper" not in line
    ]


def test_feature_code_honours_share_and_min_word_length():
    fea = build_feature_code(Letters(["a", "b"], ["A"]), 6, 0.25, 4)
    rules = lowercase_rules(fea)
    assert len(rules) == 3
    assert rules[-1].count("lookup TO_HALF") == 1
    assert rules[0].count("lookup TO_HALF") == 2


def test_feature_code_lists_longest_words_first():
    fea = build_feature_code(Letters(["a", "b"], ["A"]), 4)
    rules = lowercase_rules(fea)
    assert len(rules) == 3
    assert rules[0].count("lookup TO_HALF") == 2
    assert rules[-1].count("lookup TO_HALF") == 1


def test_feature_code_orders_camel_case_rules():
    fea = build_feature_code(Letters(["a"], ["A"]), 3, 0.5, 1)
    body = fea.split("feature calt {\n", 1)[1]
    lines = [line.strip() for line in body.splitlines() if line.startswith("  ")]
    assert lines[0] == "ignore sub @letter @lower';"
    assert lines[1] == "ignore sub [@upper @upper_half] @upper' @upper;"
    acronym_end = lines.index("ignore sub [@upper @upper_half] @upper';")
    assert any(line.endswith("@upper @lower;") for line in lines[:acronym_end])
    assert lines[acronym_end + 1] == (
        "sub @upper' lookup TO_HALF @upper' lookup TO_HALF @upper;"
    )
    assert "sub @upper' lookup TO_HALF;" not in lines[:acronym_end]
    assert lines[acronym_end + 3] == "sub @upper' lookup TO_HALF;"


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
