import os
import random
import shutil
import struct
from pathlib import Path

import pytest
from conftest import make_collection, make_font, make_variable_font
from fontTools.ttLib import TTFont
from fontTools.ttLib.sfnt import TTC_V1

from halfbold import scan
from halfbold.cli import main
from halfbold.collection import collection_members
from halfbold.scan import (
    Candidate,
    Face,
    build_all,
    candidates_from_paths,
    find_candidates,
    find_installed_half_families,
    font_kind,
    nearest_face,
    read_font_info,
    resolve_pair,
)
from halfbold.settings import Settings


def stamp_tables(path: Path, *, fixed_pitch: int = 0, serif_style: int = 0) -> None:
    font = TTFont(path)
    font["post"].isFixedPitch = fixed_pitch
    font["OS/2"].panose.bSerifStyle = serif_style
    font.save(path)


def fill_fonts_dir(fonts_dir: Path) -> None:
    fonts_dir.mkdir()
    make_font(fonts_dir / "Pair-Regular.ttf", "Pair", "Regular", 100)
    make_font(fonts_dir / "Pair-Bold.ttf", "Pair", "Bold", 200)
    make_font(fonts_dir / "Pair-Italic.ttf", "Pair", "Italic", 100)
    make_font(fonts_dir / "Lonely-Regular.ttf", "Lonely", "Regular", 100)
    make_variable_font(fonts_dir / "Var.ttf", "Var Variable")


def test_find_candidates_pairs_and_variables(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)

    found = {c.family: c for c in find_candidates(fonts)}

    assert set(found) == {"Pair", "Var"}
    assert found["Pair"].bold == fonts / "Pair-Bold.ttf"
    assert found["Var"].bold is None
    assert found["Var"].output == fonts / "Var-Half.ttf"


def test_build_all_skips_up_to_date_and_ignores_own_output(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)

    first = build_all(fonts)
    assert sorted(line.split()[0] for line in first) == ["built", "built"]
    assert (fonts / "Pair-Half.ttf").exists()
    assert (fonts / "Var-Half.ttf").exists()
    assert (fonts / "Pair-HalfBold.ttf").exists()
    assert (fonts / "Var-HalfBold.ttf").exists()

    second = build_all(fonts)
    assert all(line.startswith("up to date") for line in second)
    assert {c.family for c in find_candidates(fonts)} == {"Pair", "Var"}


def test_build_all_rebuilds_when_source_is_newer(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    output = fonts / "Var-Half.ttf"
    old = output.stat().st_mtime
    os.utime(fonts / "Var.ttf", (old + 10, old + 10))

    report = build_all(fonts)

    assert any(line.startswith("built") and "Var-Half" in line for line in report)
    assert any(line.startswith("up to date") and "Pair-Half" in line for line in report)


def test_build_all_rebuilds_when_half_bold_face_is_missing(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    (fonts / "Pair-HalfBold.ttf").unlink()

    report = build_all(fonts)

    assert any(line.startswith("built") and "Pair-Half" in line for line in report)
    assert (fonts / "Pair-HalfBold.ttf").exists()


def test_cli_all_dry_run(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)

    assert main(["--all", "--fonts-dir", str(fonts), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "would build Pair-Half.ttf" in out
    assert "would build Var-Half.ttf" in out
    assert not (fonts / "Pair-Half.ttf").exists()


def test_kind_from_tables(tmp_path: Path):
    path = make_font(tmp_path / "Plain-Regular.ttf", "Plain", "Regular", 100)

    stamp_tables(path, serif_style=4)
    assert font_kind(TTFont(path), "Plain") == "serif"

    stamp_tables(path, fixed_pitch=1)
    assert font_kind(TTFont(path), "Plain") == "mono"

    stamp_tables(path, serif_style=11)
    assert font_kind(TTFont(path), "Plain") == "sans"


def test_kind_from_name_when_tables_say_any(tmp_path: Path):
    path = make_font(tmp_path / "Plain-Regular.ttf", "Plain", "Regular", 100)
    font = TTFont(path)

    assert font_kind(font, "Fancy Serif") == "serif"
    assert font_kind(font, "Fancy Sans Serif") == "sans"
    assert font_kind(font, "JetBrainsMono Nerd Font") == "mono"
    assert font_kind(font, "Source Code Pro") == "mono"
    assert font_kind(font, "Pair") == "sans"


def test_candidates_carry_kind(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    stamp_tables(fonts / "Pair-Regular.ttf", fixed_pitch=1)

    found = {c.family: c for c in find_candidates(fonts)}

    assert found["Pair"].kind == "mono"
    assert found["Var"].kind == "sans"


def test_build_all_reports_kind(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    stamp_tables(fonts / "Pair-Regular.ttf", fixed_pitch=1)

    for line in build_all(fonts, dry_run=True):
        assert line.endswith("(sans)") or line.endswith("(mono)")
    assert any(
        line
        == (
            "would build Pair-Half.ttf  <- Pair  "
            "plain Regular 400, bold Bold 700 (mono)"
        )
        for line in build_all(fonts, dry_run=True)
    )


def test_installed_half_families(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)

    assert find_installed_half_families(fonts) == {"Pair Half", "Var Half"}


FACES = (
    Face(Path("Multi-Light.ttf"), "Light", 300),
    Face(Path("Multi-Regular.ttf"), "Regular", 400),
    Face(Path("Multi-Medium.ttf"), "Medium", 500),
    Face(Path("Multi-Bold.ttf"), "Bold", 700),
)


def test_nearest_face_picks_the_closest_weight():
    assert nearest_face(FACES, 500, heavier_on_tie=True).style == "Medium"
    assert nearest_face(FACES, 100, heavier_on_tie=True).style == "Light"
    assert nearest_face(FACES, 900, heavier_on_tie=False).style == "Bold"


def test_nearest_face_breaks_an_exact_tie_by_direction():
    assert nearest_face(FACES, 450, heavier_on_tie=True).style == "Medium"
    assert nearest_face(FACES, 450, heavier_on_tie=False).style == "Regular"


def test_resolve_pair_keeps_the_two_faces_distinct():
    plain, bold = resolve_pair(FACES, 500, 520)
    assert (plain.style, bold.style) == ("Medium", "Bold")

    plain, bold = resolve_pair(FACES, 700, 700)
    assert (plain.style, bold.style) == ("Medium", "Bold")

    plain, bold = resolve_pair(FACES, 300, 300)
    assert (plain.style, bold.style) == ("Light", "Regular")


def test_resolve_pair_honours_an_inverted_request():
    plain, bold = resolve_pair(FACES, 700, 300)
    assert (plain.style, bold.style) == ("Bold", "Light")


def test_style_name_decides_the_weight_over_a_wrong_weight_class(tmp_path: Path):
    path = make_font(tmp_path / "Odd-Bold.ttf", "Odd", "Bold", 200, weight=400)
    assert read_font_info(path).weight == 700

    path = make_font(tmp_path / "Odd-Cond.ttf", "Odd", "Condensed", 200, weight=600)
    assert read_font_info(path).weight == 600


def test_every_weight_of_a_family_becomes_a_face(multi_weight_family: Path):
    found = {c.family: c for c in find_candidates(multi_weight_family)}

    assert set(found) == {"Multi"}
    assert [f.style for f in found["Multi"].faces] == [
        "Light",
        "Regular",
        "Medium",
        "Bold",
    ]
    assert found["Multi"].regular.name == "Multi-Regular.ttf"
    assert found["Multi"].bold.name == "Multi-Bold.ttf"


def test_weight_settings_choose_the_faces(multi_weight_family: Path):
    settings = Settings(regular_weight=300, bold_weight=500)

    found = {c.family: c for c in find_candidates(multi_weight_family, settings)}

    assert found["Multi"].regular.name == "Multi-Light.ttf"
    assert found["Multi"].bold.name == "Multi-Medium.ttf"
    assert found["Multi"].faces_label == "plain Light 300, bold Medium 500"


def test_build_all_reports_the_resolved_faces(multi_weight_family: Path):
    settings = Settings(regular_weight=300, bold_weight=700)

    report = build_all(multi_weight_family, dry_run=True, settings=settings)

    assert any("plain Light 300, bold Bold 700" in line for line in report)


def test_build_all_copies_glyphs_from_the_chosen_faces(multi_weight_family: Path):
    build_all(
        multi_weight_family, settings=Settings(regular_weight=300, bold_weight=700)
    )
    font = TTFont(multi_weight_family / "Multi-Half.ttf")
    assert font["hmtx"]["a"][0] == 250
    assert font["hmtx"]["a.half"][0] == 450

    build_all(
        multi_weight_family,
        force=True,
        settings=Settings(regular_weight=400, bold_weight=500),
    )
    font = TTFont(multi_weight_family / "Multi-Half.ttf")
    assert font["hmtx"]["a"][0] == 300
    assert font["hmtx"]["a.half"][0] == 350


def test_variable_candidate_reports_its_clamped_weights(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    make_variable_font(fonts / "Var.ttf", "Var Variable")

    found = {c.family: c for c in find_candidates(fonts, Settings(bold_weight=900))}

    assert found["Var"].faces == ()
    assert found["Var"].faces_label == "plain wght 400, bold wght 700"


def make_coll_collection(tmp_path: Path) -> Path:
    parts = tmp_path / "parts"
    parts.mkdir()
    faces = [
        make_font(parts / "Coll-Regular.ttf", "Coll", "Regular", 100, weight=400),
        make_font(parts / "Coll-Bold.ttf", "Coll", "Bold", 200, weight=700),
        make_font(parts / "Coll-Italic.ttf", "Coll", "Italic", 100, weight=400),
    ]
    return make_collection(tmp_path / "Coll.ttc", faces)


def test_collection_faces_group_into_one_candidate(tmp_path: Path):
    ttc = make_coll_collection(tmp_path)

    [candidate] = candidates_from_paths(collection_members(ttc))

    assert candidate.family == "Coll"
    assert candidate.regular == Path(f"{ttc}#0")
    assert candidate.bold == Path(f"{ttc}#1")
    assert candidate.sources == [ttc, ttc]


def test_read_font_info_reads_a_collection_face(tmp_path: Path):
    ttc = make_coll_collection(tmp_path)

    info = read_font_info(Path(f"{ttc}#1"))

    assert info is not None
    assert info.style == "Bold"


def test_read_font_info_skips_an_over_cap_header_named_as_a_font(tmp_path: Path):
    crafted = tmp_path / "Huge.ttf"
    crafted.write_bytes(struct.pack(">4sLL", b"ttcf", TTC_V1, 2**26))

    assert read_font_info(crafted) is None


FUZZ_ROUNDS = 150


def shorten_table(path: Path, tag: bytes, length: int) -> None:
    data = bytearray(path.read_bytes())
    table_count = struct.unpack_from(">H", data, 4)[0]
    for index in range(table_count):
        record = 12 + 16 * index
        if bytes(data[record : record + 4]) == tag:
            struct.pack_into(">L", data, record + 12, length)
    path.write_bytes(bytes(data))


def test_read_font_info_skips_a_font_with_a_corrupt_table(tmp_path: Path):
    broken = tmp_path / "Broken-Regular.ttf"
    make_font(broken, "Broken", "Regular", 400)
    shorten_table(broken, b"post", 2)

    assert read_font_info(broken) is None


def test_build_all_skips_a_font_that_fails_to_build_and_keeps_going(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    make_font(fonts / "Good-Regular.ttf", "Good", "Regular", 100)
    make_font(fonts / "Good-Bold.ttf", "Good", "Bold", 200)
    make_font(fonts / "Bad-Regular.ttf", "Bad", "Regular", 100)
    bad_bold = make_font(fonts / "Bad-Bold.ttf", "Bad", "Bold", 200)
    shorten_table(bad_bold, b"glyf", 2)

    report = build_all(fonts)

    assert any(line.startswith("built") and "Good-Half.ttf" in line for line in report)
    assert any(line.startswith("skipped     Bad ") for line in report)


def flip_random_bytes(path: Path, rng: random.Random) -> None:
    data = bytearray(path.read_bytes())
    for _ in range(rng.randint(1, 12)):
        data[rng.randrange(len(data))] = rng.randrange(256)
    path.write_bytes(bytes(data))


def test_build_all_never_raises_on_byte_flipped_fonts(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    make_font(source / "Fuzz-Regular.ttf", "Fuzz", "Regular", 100)
    make_font(source / "Fuzz-Bold.ttf", "Fuzz", "Bold", 200)
    for seed in range(FUZZ_ROUNDS):
        rng = random.Random(seed)
        work = tmp_path / f"round{seed}"
        shutil.copytree(source, work)
        flip_random_bytes(work / rng.choice(["Fuzz-Regular.ttf", "Fuzz-Bold.ttf"]), rng)

        build_all(work)


def test_candidate_output_keeps_a_hostile_family_inside_the_folder(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    candidate = Candidate(
        "../../Escape", fonts / "a.ttf", fonts / "b.ttf", "sans", output_dir=fonts
    )

    assert candidate.output.parent == fonts
    assert candidate.bold_face_output.parent == fonts


def test_build_all_writes_a_hostile_family_only_inside_the_fonts_folder(
    tmp_path: Path,
):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    make_font(fonts / "Hostile-Regular.ttf", "Hostile/../../Escape", "Regular", 100)
    make_font(fonts / "Hostile-Bold.ttf", "Hostile/../../Escape", "Bold", 200)

    report = build_all(fonts)

    assert report[0].startswith("built")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fonts"]


def test_build_all_refuses_a_symlink_where_the_output_goes(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    outside = tmp_path / "outside.ttf"
    outside.write_bytes(b"keep")
    make_font(fonts / "Pair-Regular.ttf", "Pair", "Regular", 100)
    make_font(fonts / "Pair-Bold.ttf", "Pair", "Bold", 200)
    (fonts / "Pair-Half.ttf").symlink_to(outside)

    report = build_all(fonts)

    assert report == [
        "skipped     Pair (sans): refusing to write 'Pair-Half.ttf': "
        "it is a symbolic link"
    ]
    assert outside.read_bytes() == b"keep"


def test_build_all_builds_a_family_whose_name_is_longer_than_a_file_name(
    tmp_path: Path,
):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    family = "L" * 300
    make_font(fonts / "Long-Regular.ttf", family, "Regular", 100)
    make_font(fonts / "Long-Bold.ttf", family, "Bold", 200)

    report = build_all(fonts)

    assert report[0].startswith("built")


def test_build_all_reports_a_font_that_recurses_and_keeps_going(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    real_build = scan.build_halfbold_font

    def recurse_on_pair(regular, bold, output, settings):
        if regular.name.startswith("Pair"):
            raise RecursionError("maximum recursion depth exceeded")
        return real_build(regular, bold, output, settings)

    monkeypatch.setattr(scan, "build_halfbold_font", recurse_on_pair)

    report = build_all(fonts)

    assert any(line.startswith("skipped") and "Pair" in line for line in report)
    assert any(line.startswith("built") and "Var" in line for line in report)


def test_tuning_one_family_leaves_the_others_at_defaults(multi_weight_family: Path):
    tuned = Settings().with_font("Multi", {"regular_weight": 300, "bold_weight": 500})
    paths = sorted(multi_weight_family.glob("*.ttf"))
    multi = next(c for c in candidates_from_paths(paths, tuned) if c.family == "Multi")
    untuned = next(c for c in candidates_from_paths(paths) if c.family == "Multi")
    assert multi.plain_weight == 300
    assert untuned.plain_weight == 400
