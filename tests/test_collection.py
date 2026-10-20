from pathlib import Path

from conftest import make_collection, make_font

from halfbold.collection import (
    collection_members,
    open_font,
    source_file,
    split_member,
)


def build_collection(tmp_path: Path) -> tuple[Path, Path]:
    parts = tmp_path / "parts"
    parts.mkdir()
    regular = make_font(parts / "Coll-Regular.ttf", "Coll", "Regular", 100)
    bold = make_font(parts / "Coll-Bold.ttf", "Coll", "Bold", 200, weight=700)
    ttc = make_collection(tmp_path / "Coll.ttc", [regular, bold])
    return ttc, regular


def test_collection_members_lists_every_face(tmp_path: Path) -> None:
    ttc, _ = build_collection(tmp_path)

    assert collection_members(ttc) == [Path(f"{ttc}#0"), Path(f"{ttc}#1")]


def test_collection_members_is_empty_for_plain_or_missing_files(tmp_path: Path) -> None:
    _, plain = build_collection(tmp_path)

    assert collection_members(plain) == []
    assert collection_members(tmp_path / "missing.ttc") == []


def test_split_member_separates_index_from_file(tmp_path: Path) -> None:
    ttc, plain = build_collection(tmp_path)

    assert split_member(Path(f"{ttc}#1")) == (ttc, 1)
    assert split_member(plain) == (plain, None)


def test_source_file_returns_the_collection_for_a_member(tmp_path: Path) -> None:
    ttc, _ = build_collection(tmp_path)

    assert source_file(Path(f"{ttc}#1")) == ttc


def test_open_font_opens_the_addressed_face(tmp_path: Path) -> None:
    ttc, plain = build_collection(tmp_path)

    assert open_font(Path(f"{ttc}#1"))["name"].getDebugName(2) == "Bold"
    assert open_font(plain)["name"].getDebugName(2) == "Regular"
