from pathlib import Path

from fontTools.ttLib import TTFont

from halfbold.build import build_halfbold_font

HALF_LOOKUPS = 4


def langsys_features(gsub, script_tag: str) -> dict[str, list[int]]:
    records = gsub.FeatureList.FeatureRecord
    script = next(
        r.Script for r in gsub.ScriptList.ScriptRecord if r.ScriptTag == script_tag
    )
    return {
        records[i].FeatureTag: records[i].Feature.LookupListIndex
        for i in script.DefaultLangSys.FeatureIndex
    }


def test_half_lookups_come_first_and_old_ones_shift(
    ligature_font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = ligature_font_pair
    out = tmp_path / "Liga-Half.ttf"
    build_halfbold_font(regular, bold, out)

    source = TTFont(regular)["GSUB"].table
    merged = TTFont(out)["GSUB"].table
    assert len(merged.LookupList.Lookup) == len(source.LookupList.Lookup) + HALF_LOOKUPS
    old_liga = langsys_features(source, "latn")["liga"]
    assert langsys_features(merged, "latn")["liga"] == [
        i + HALF_LOOKUPS for i in old_liga
    ]
    tags = [r.FeatureTag for r in merged.FeatureList.FeatureRecord]
    assert tags == sorted(tags)


def test_calt_reaches_every_langsys(
    ligature_font_pair: tuple[Path, Path], tmp_path: Path
):
    regular, bold = ligature_font_pair
    out = tmp_path / "Liga-Half.ttf"
    build_halfbold_font(regular, bold, out)

    merged = TTFont(out)["GSUB"].table
    dflt = langsys_features(merged, "DFLT")["calt"]
    latn = langsys_features(merged, "latn")["calt"]
    assert latn == [2, 3]
    assert len(dflt) == 3
    assert dflt[0] >= HALF_LOOKUPS
    assert dflt[-2:] == [2, 3]
