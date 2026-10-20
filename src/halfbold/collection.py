import re
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib.sfnt import readTTCHeader

COLLECTION_SUFFIX = ".ttc"
MEMBER = re.compile(r"(?P<file>.+\.ttc)#(?P<number>\d+)", re.IGNORECASE)


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
    if number is None:
        return TTFont(file, lazy=lazy)
    return TTFont(file, fontNumber=number, lazy=lazy)


def collection_members(path: Path) -> list[Path]:
    try:
        with path.open("rb") as file:
            count = readTTCHeader(file).numFonts
    except TTLibError, OSError:
        return []
    return [member_path(path, number) for number in range(count)]
