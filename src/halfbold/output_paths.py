import os
import re
from pathlib import Path

UNSAFE_NAME_CHARACTERS = re.compile(r"[/\\\x00]")
MAX_STEM_BYTES = 100


def file_stem(family: str) -> str:
    stem = UNSAFE_NAME_CHARACTERS.sub("_", family.replace(" ", ""))
    return stem.encode()[:MAX_STEM_BYTES].decode(errors="ignore")


def contained_file(folder: Path, name: str) -> Path:
    if name in ("", ".", "..") or Path(name).name != name:
        raise ValueError(f"refusing to write {name!r}: not a single file name")
    target = folder / name
    if os.path.realpath(target.parent) != os.path.realpath(folder):
        raise ValueError(f"refusing to write {name!r}: it leaves {folder}")
    if target.is_symlink():
        raise ValueError(f"refusing to write {name!r}: it is a symbolic link")
    return target
