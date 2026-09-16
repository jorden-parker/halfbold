from pathlib import Path

from fontTools.ttLib import TTFont

from halfbold.build import (
    BOLD_SUFFIX,
    bold_prefix_length,
    build_feature_code,
    build_halfbold_font,
)
from halfbold.cli import main


def test_bold_prefix_is_half_rounded_up():
    assert [bold_prefix_length(n) for n in (2, 3, 4, 5, 6)] == [1, 2, 2, 3, 3]


def test_feature_code_lists_longest_words_first():
    fea = build_feature_code(["a", "b"], 4)
    rules = [
        line for line in fea.splitlines() if line.strip().startswith("sub @plain'")
    ]
    assert len(rules) == 3
    assert rules[0].count("lookup TO_HALF") == 2
    assert rules[-1].count("lookup TO_HALF") == 1


def test_build_adds_bold_glyphs_and_calt(font_pair: tuple[Path, Path], tmp_path: Path):
    regular, bold = font_pair
    out = tmp_path / "Test-Half.ttf"
    letters = build_halfbold_font(regular, bold, out)

    font = TTFont(out)
    assert len(letters) == 26
    assert "a" + BOLD_SUFFIX in font.getGlyphOrder()
    assert font["hmtx"]["a" + BOLD_SUFFIX][0] == 300
    features = {f.FeatureTag for f in font["GSUB"].table.FeatureList.FeatureRecord}
    assert "calt" in features
    assert font["name"].getBestFamilyName() == "Test Half"


def test_cli_defaults_output_next_to_regular(font_pair: tuple[Path, Path], capsys):
    regular, bold = font_pair
    assert main([str(regular), str(bold)]) == 0
    assert regular.with_name("Test-Regular-Half.ttf").exists()
    assert "26 letter glyphs" in capsys.readouterr().out


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
