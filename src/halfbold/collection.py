import re
import struct
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib.sfnt import readTTCHeader

COLLECTION_SUFFIX = ".ttc"
MEMBER = re.compile(r"(?P<file>.+\.ttc)#(?P<number>\d+)", re.IGNORECASE)
MAX_COLLECTION_FACES = 256
TTC_HEADER = struct.Struct(">4sLL")
TTC_TAG = b"ttcf"


def member_path(collection: Path, number: int) -> Path:
    return Path(f"{collection}#{number}")


def split_member(path: Path) -> tuple[Path, int | None]:
    match = MEMBER.fullmatch(str(path))
    if match is None:
        return path, None
    return Path(match["file"]), int(match["number"])


def source_file(path: Path) -> Path:
    return split_member(path)[0]


def open_font(path: Path, lazy: bool | None = None) -> TTFont:
    file, number = split_member(path)
    refuse_too_many_faces(file)
    if number is None:
        return TTFont(file, lazy=lazy)
    return TTFont(file, fontNumber=number, lazy=lazy)


def header_claims_too_many_faces(header: bytes) -> bool:
    if len(header) != TTC_HEADER.size:
        return False
    tag, _version, count = TTC_HEADER.unpack(header)
    return tag == TTC_TAG and count > MAX_COLLECTION_FACES


def refuse_too_many_faces(path: Path) -> None:
    with path.open("rb") as file:
        header = file.read(TTC_HEADER.size)
    if header_claims_too_many_faces(header):
        raise TTLibError(
            f"Not a Font Collection (more than {MAX_COLLECTION_FACES} faces)"
        )


def collection_members(path: Path) -> list[Path]:
    try:
        refuse_too_many_faces(path)
        with path.open("rb") as file:
            count = readTTCHeader(file).numFonts
    except TTLibError, OSError, struct.error, AssertionError:
        return []
    return [member_path(path, number) for number in range(count)]
