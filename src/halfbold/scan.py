import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from fontTools.ttLib import TTFont, TTLibError

from halfbold.build import STYLE_SUFFIX, build_halfbold_font
from halfbold.settings import Settings

REGULAR_STYLES = {"regular", "book", "normal", "roman"}
BOLD_STYLES = {"bold"}

Kind = Literal["sans", "serif", "mono"]
KINDS: tuple[Kind, ...] = ("sans", "serif", "mono")
MONO_NAME = re.compile(r"mono|\bcode\b")


@dataclass(frozen=True)
class Candidate:
    family: str
    regular: Path
    bold: Path | None
    kind: Kind
    output_dir: Path | None = None

    @property
    def output(self) -> Path:
        stem = self.family.replace(" ", "")
        return (self.output_dir or self.regular.parent) / f"{stem}-{STYLE_SUFFIX}.ttf"

    @property
    def sources(self) -> list[Path]:
        return [p for p in (self.regular, self.bold) if p is not None]

    def is_stale(self) -> bool:
        if not self.output.exists():
            return True
        built = self.output.stat().st_mtime
        return any(p.stat().st_mtime > built for p in self.sources)


@dataclass(frozen=True)
class FontInfo:
    path: Path
    family: str
    style: str
    variable: bool
    kind: Kind


def font_kind(font: TTFont, family: str) -> Kind:
    lowered = family.lower()
    panose = font["OS/2"].panose if "OS/2" in font else None
    fixed_pitch = "post" in font and bool(font["post"].isFixedPitch)
    if fixed_pitch or (panose and panose.bProportion == 9) or MONO_NAME.search(lowered):
        return "mono"
    if panose and 2 <= panose.bSerifStyle <= 10:
        return "serif"
    if panose and 11 <= panose.bSerifStyle <= 15:
        return "sans"
    if "serif" in lowered and "sans" not in lowered:
        return "serif"
    return "sans"


def read_font_info(path: Path) -> FontInfo | None:
    try:
        font = TTFont(path, lazy=True)
    except TTLibError, OSError:
        return None
    try:
        if "glyf" not in font:
            return None
        name = font["name"]
        family = name.getDebugName(16) or name.getDebugName(1) or ""
        style = name.getDebugName(17) or name.getDebugName(2) or ""
        variable = "fvar" in font and any(
            a.axisTag == "wght" for a in font["fvar"].axes
        )
        kind = font_kind(font, family)
        return FontInfo(path, family, style, variable, kind)
    finally:
        font.close()


def is_half_output(info: FontInfo) -> bool:
    return info.family.endswith(f" {STYLE_SUFFIX}")


def is_italic(info: FontInfo) -> bool:
    return "italic" in info.style.lower() or "oblique" in info.style.lower()


def find_installed_half_families(fonts_dir: Path) -> set[str]:
    return {
        info.family
        for path in sorted(fonts_dir.glob("*.ttf"))
        if (info := read_font_info(path)) is not None and is_half_output(info)
    }


def find_candidates(fonts_dir: Path) -> list[Candidate]:
    return candidates_from_paths(sorted(fonts_dir.glob("*.ttf")))


def installed_font_dirs() -> list[Path]:
    if sys.platform != "darwin":
        return []
    return [
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path("/Network/Library/Fonts"),
    ]


def find_installed_candidates(fonts_dir: Path) -> list[Candidate]:
    roots = [fonts_dir]
    if fonts_dir == Path.home() / "Library/Fonts":
        roots.extend(installed_font_dirs())
    paths = dict.fromkeys(
        path
        for root in reversed(roots)
        for path in sorted(root.rglob("*"))
        if path.suffix.lower() in {".ttf", ".otf"}
        and not path.name.startswith("._")
        and path.is_file()
    )
    return sorted(
        (
            replace(candidate, output_dir=fonts_dir)
            for candidate in candidates_from_paths(list(paths))
        ),
        key=lambda candidate: candidate.family.casefold(),
    )


def candidates_from_paths(paths: list[Path]) -> list[Candidate]:
    infos = [
        info
        for path in paths
        if (info := read_font_info(path)) is not None
        and not is_half_output(info)
        and not is_italic(info)
    ]
    candidates: list[Candidate] = []
    families_done: set[str] = set()
    for info in infos:
        if info.variable and info.family not in families_done:
            base = " ".join(p for p in info.family.split() if p != "Variable")
            candidates.append(Candidate(base, info.path, None, info.kind))
            families_done.add(info.family)
    regulars = {
        i.family: i
        for i in infos
        if not i.variable and i.style.lower() in REGULAR_STYLES
    }
    bolds = {
        i.family: i for i in infos if not i.variable and i.style.lower() in BOLD_STYLES
    }
    for family, regular in regulars.items():
        if family in families_done or family not in bolds:
            continue
        candidates.append(
            Candidate(family, regular.path, bolds[family].path, regular.kind)
        )
        families_done.add(family)
    return candidates


def build_all(
    fonts_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> list[str]:
    report: list[str] = []
    for candidate in find_candidates(fonts_dir):
        if not force and not candidate.is_stale():
            report.append(f"up to date  {candidate.output.name}  ({candidate.kind})")
            continue
        if dry_run:
            report.append(
                f"would build {candidate.output.name}  "
                f"<- {candidate.family} ({candidate.kind})"
            )
            continue
        try:
            build_halfbold_font(
                candidate.regular, candidate.bold, candidate.output, settings
            )
            report.append(
                f"built       {candidate.output.name}  "
                f"<- {candidate.family} ({candidate.kind})"
            )
        except (ValueError, TTLibError) as err:
            report.append(f"skipped     {candidate.family} ({candidate.kind}): {err}")
    return report
