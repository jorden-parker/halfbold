import struct
from pathlib import Path

import pytest
from conftest import make_collection, make_font
from fontTools.ttLib import TTLibError
from fontTools.ttLib.sfnt import TTC_V1

from halfbold.collection import (
    MAX_COLLECTION_FACES,
    collection_members,
    open_font,
    source_file,
    split_member,
)

TTC_VERSION_ONE = 0x00010000
UNRECOGNISED_TTC_VERSION = 0x00030000


def craft_collection_header(
    path: Path, declared_faces: int, offsets: int, version: int = TTC_V1
) -> Path:
    header = struct.pack(">4sLL", b"ttcf", version, declared_faces)
    path.write_bytes(header + bytes(4 * offsets))
    return path


def build_collection(tmp_path: Path) -> tuple[Path, Path]:
    parts = tmp_path / "parts"
    parts.mkdir()
    regular = make_font(parts / "Coll-Regular.ttf", "Coll", "Regular", 100)
    bold = make_font(parts / "Coll-Bold.ttf", "Coll", "Bold", 200, weight=700)
    ttc = make_collection(tmp_path / "Coll.ttc", [regular, bold])
    return ttc, regular


def write_collection_header(
    path: Path, version: int, count: int, tables: bytes
) -> Path:
    path.write_bytes(b"ttcf" + struct.pack(">II", version, count) + tables)
    return path


def test_collection_members_lists_every_face(tmp_path: Path) -> None:
    ttc, _ = build_collection(tmp_path)

    assert collection_members(ttc) == [Path(f"{ttc}#0"), Path(f"{ttc}#1")]


def test_face_cap_refuses_a_huge_count_the_file_cannot_hold(
    tmp_path: Path,
) -> None:
    huge = craft_collection_header(tmp_path / "Huge.ttc", 2**26, offsets=0)

    assert collection_members(huge) == []


def test_collection_members_refuses_a_count_above_the_cap(tmp_path: Path) -> None:
    over = MAX_COLLECTION_FACES + 1
    crafted = craft_collection_header(tmp_path / "Over.ttc", over, offsets=over)

    assert collection_members(crafted) == []


def test_collection_members_refuses_an_over_cap_count_in_any_version(
    tmp_path: Path,
) -> None:
    over = MAX_COLLECTION_FACES + 1
    crafted = craft_collection_header(
        tmp_path / "Future.ttc", over, offsets=over, version=UNRECOGNISED_TTC_VERSION
    )

    assert collection_members(crafted) == []


def test_collection_members_lists_a_count_at_the_cap(tmp_path: Path) -> None:
    crafted = craft_collection_header(
        tmp_path / "Full.ttc", MAX_COLLECTION_FACES, offsets=MAX_COLLECTION_FACES
    )

    assert len(collection_members(crafted)) == MAX_COLLECTION_FACES


def test_collection_members_is_empty_for_plain_or_missing_files(tmp_path: Path) -> None:
    _, plain = build_collection(tmp_path)

    assert collection_members(plain) == []
    assert collection_members(tmp_path / "missing.ttc") == []


def test_collection_members_is_empty_for_truncated_offset_table(tmp_path: Path) -> None:
    truncated = write_collection_header(
        tmp_path / "Truncated.ttc", TTC_VERSION_ONE, 2, b"\x00\x00\x00\x1c"
    )

    assert collection_members(truncated) == []


def test_collection_members_is_empty_for_unrecognised_version(tmp_path: Path) -> None:
    unknown = write_collection_header(
        tmp_path / "Unknown.ttc", UNRECOGNISED_TTC_VERSION, 1, b"\x00\x00\x00\x1c"
    )

    assert collection_members(unknown) == []


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


def test_open_font_refuses_an_over_cap_header_named_as_a_font(
    tmp_path: Path,
) -> None:
    crafted = craft_collection_header(tmp_path / "Huge.ttf", 2**26, offsets=0)

    with pytest.raises(TTLibError):
        open_font(crafted)
