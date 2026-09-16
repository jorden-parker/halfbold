from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError

from halfbold.build import STYLE_SUFFIX, build_halfbold_font

REGULAR_STYLES = {"regular", "book", "normal", "roman"}
BOLD_STYLES = {"bold"}


@dataclass(frozen=True)
class Candidate:
    family: str
    regular: Path
    bold: Path | None

    @property
    def output(self) -> Path:
        stem = self.family.replace(" ", "")
        return self.regular.with_name(f"{stem}-{STYLE_SUFFIX}.ttf")

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


def read_font_info(path: Path) -> FontInfo | None:
    try:
        font = TTFont(path, lazy=True)
    except TTLibError:
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
        return FontInfo(path, family, style, variable)
    finally:
        font.close()


def is_half_output(info: FontInfo) -> bool:
    return info.family.endswith(f" {STYLE_SUFFIX}")


def is_italic(info: FontInfo) -> bool:
    return "italic" in info.style.lower() or "oblique" in info.style.lower()


def find_candidates(fonts_dir: Path) -> list[Candidate]:
    infos = [
        info
        for path in sorted(fonts_dir.glob("*.ttf"))
        if (info := read_font_info(path)) is not None
        and not is_half_output(info)
        and not is_italic(info)
    ]
    candidates: list[Candidate] = []
    families_done: set[str] = set()
    for info in infos:
        if info.variable and info.family not in families_done:
            base = " ".join(p for p in info.family.split() if p != "Variable")
            candidates.append(Candidate(base, info.path, None))
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
        candidates.append(Candidate(family, regular.path, bolds[family].path))
        families_done.add(family)
    return candidates


def build_all(fonts_dir: Path, force: bool = False, dry_run: bool = False) -> list[str]:
    report: list[str] = []
    for candidate in find_candidates(fonts_dir):
        if not force and not candidate.is_stale():
            report.append(f"up to date  {candidate.output.name}")
            continue
        if dry_run:
            report.append(f"would build {candidate.output.name}  <- {candidate.family}")
            continue
        try:
            build_halfbold_font(candidate.regular, candidate.bold, candidate.output)
            report.append(f"built       {candidate.output.name}  <- {candidate.family}")
        except (ValueError, TTLibError) as err:
            report.append(f"skipped     {candidate.family}: {err}")
    return report
