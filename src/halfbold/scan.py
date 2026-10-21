import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from fontTools.ttLib import TTFont, TTLibError

from halfbold.build import (
    STYLE_SUFFIX,
    bold_face_path,
    build_bold_face,
    build_halfbold_font,
)
from halfbold.collection import (
    COLLECTION_SUFFIX,
    collection_members,
    open_font,
    source_file,
)
from halfbold.settings import Settings

STYLE_WEIGHTS = {
    "thin": 100,
    "hairline": 100,
    "extralight": 200,
    "ultralight": 200,
    "light": 300,
    "regular": 400,
    "book": 400,
    "normal": 400,
    "roman": 400,
    "medium": 500,
    "semibold": 600,
    "demibold": 600,
    "bold": 700,
    "extrabold": 800,
    "ultrabold": 800,
    "black": 900,
    "heavy": 900,
}
FALLBACK_WEIGHT = 400

Kind = Literal["sans", "serif", "mono"]
KINDS: tuple[Kind, ...] = ("sans", "serif", "mono")
MONO_NAME = re.compile(r"mono|\bcode\b")
NON_LETTERS = re.compile(r"[^a-z]")


@dataclass(frozen=True)
class Face:
    path: Path
    style: str
    weight: int

    @property
    def label(self) -> str:
        return f"{self.style or 'Regular'} {self.weight}"


@dataclass(frozen=True)
class Candidate:
    family: str
    regular: Path
    bold: Path | None
    kind: Kind
    output_dir: Path | None = None
    faces: tuple[Face, ...] = ()
    plain_face: Face | None = None
    bold_face: Face | None = None
    plain_weight: float | None = None
    bold_weight: float | None = None

    @property
    def output(self) -> Path:
        stem = self.family.replace(" ", "")
        return (self.output_dir or self.regular.parent) / f"{stem}-{STYLE_SUFFIX}.ttf"

    @property
    def bold_face_output(self) -> Path:
        return bold_face_path(self.output)

    @property
    def sources(self) -> list[Path]:
        return [source_file(p) for p in (self.regular, self.bold) if p is not None]

    @property
    def faces_label(self) -> str | None:
        if self.plain_face is not None and self.bold_face is not None:
            return f"plain {self.plain_face.label}, bold {self.bold_face.label}"
        if self.plain_weight is not None and self.bold_weight is not None:
            return f"plain wght {self.plain_weight:g}, bold wght {self.bold_weight:g}"
        return None

    def is_stale(self) -> bool:
        outputs = (self.output, self.bold_face_output)
        if not all(path.exists() for path in outputs):
            return True
        built = min(path.stat().st_mtime for path in outputs)
        return any(p.stat().st_mtime > built for p in self.sources)


@dataclass(frozen=True)
class FontInfo:
    path: Path
    family: str
    style: str
    weight: int
    variable: bool
    kind: Kind
    weight_range: tuple[float, float] | None = None


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


def face_weight(font: TTFont, style: str) -> int:
    named = STYLE_WEIGHTS.get(NON_LETTERS.sub("", style.lower()))
    if named is not None:
        return named
    if "OS/2" in font:
        return int(font["OS/2"].usWeightClass)
    return FALLBACK_WEIGHT


FONT_INFO_CACHE: dict[tuple[Path, int, int], FontInfo | None] = {}


def read_font_info(path: Path) -> FontInfo | None:
    try:
        stat = source_file(path).stat()
    except OSError:
        return None
    key = (path, stat.st_mtime_ns, stat.st_size)
    if key in FONT_INFO_CACHE:
        return FONT_INFO_CACHE[key]
    info = load_font_info(path)
    FONT_INFO_CACHE[key] = info
    return info


def load_font_info(path: Path) -> FontInfo | None:
    try:
        font = open_font(path, lazy=True)
    except TTLibError, OSError:
        return None
    try:
        if "glyf" not in font:
            return None
        name = font["name"]
        family = name.getDebugName(16) or name.getDebugName(1) or ""
        style = name.getDebugName(17) or name.getDebugName(2) or ""
        axes = font["fvar"].axes if "fvar" in font else []
        axis = next((a for a in axes if a.axisTag == "wght"), None)
        kind = font_kind(font, family)
        weight_range = None if axis is None else (axis.minValue, axis.maxValue)
        return FontInfo(
            path,
            family,
            style,
            face_weight(font, style),
            axis is not None,
            kind,
            weight_range,
        )
    finally:
        font.close()


def is_half_output(info: FontInfo) -> bool:
    return info.family.endswith(f" {STYLE_SUFFIX}")


def is_italic(info: FontInfo) -> bool:
    return "italic" in info.style.lower() or "oblique" in info.style.lower()


def is_hidden(info: FontInfo) -> bool:
    return info.family.startswith(".")


def find_installed_half_fonts(fonts_dir: Path) -> dict[Path, str]:
    return {
        path: info.family
        for path in sorted(fonts_dir.glob("*.ttf"))
        if (info := read_font_info(path)) is not None and is_half_output(info)
    }


def find_installed_half_families(fonts_dir: Path) -> set[str]:
    return set(find_installed_half_fonts(fonts_dir).values())


def find_candidates(
    fonts_dir: Path, settings: Settings | None = None
) -> list[Candidate]:
    return candidates_from_paths(sorted(fonts_dir.glob("*.ttf")), settings)


def installed_font_dirs() -> list[Path]:
    if sys.platform != "darwin":
        return []
    return [
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path("/Network/Library/Fonts"),
    ]


FONT_SUFFIXES = {".ttf", ".otf", COLLECTION_SUFFIX}


def face_paths(path: Path) -> list[Path]:
    if path.suffix.lower() == COLLECTION_SUFFIX:
        return collection_members(path)
    return [path]


def find_installed_candidates(
    fonts_dir: Path, settings: Settings | None = None
) -> list[Candidate]:
    roots = [fonts_dir]
    if fonts_dir == Path.home() / "Library/Fonts":
        roots.extend(installed_font_dirs())
    paths = dict.fromkeys(
        face
        for root in reversed(roots)
        for path in sorted(root.rglob("*"))
        if path.suffix.lower() in FONT_SUFFIXES
        and not path.name.startswith("._")
        and path.is_file()
        for face in face_paths(path)
    )
    return sorted(
        (
            replace(candidate, output_dir=fonts_dir)
            for candidate in candidates_from_paths(list(paths), settings)
        ),
        key=lambda candidate: candidate.family.casefold(),
    )


def clamped(weight: float, span: tuple[float, float] | None) -> float:
    if span is None:
        return weight
    low, high = span
    return min(high, max(low, weight))


def family_faces(members: Sequence[FontInfo]) -> tuple[Face, ...]:
    by_weight: dict[int, Face] = {}
    for info in members:
        by_weight[info.weight] = Face(info.path, info.style, info.weight)
    return tuple(sorted(by_weight.values(), key=lambda face: face.weight))


def nearest_face(faces: Sequence[Face], weight: float, heavier_on_tie: bool) -> Face:
    def rank(face: Face) -> tuple[float, float, str]:
        tie = -face.weight if heavier_on_tie else face.weight
        return (abs(face.weight - weight), tie, str(face.path))

    return min(faces, key=rank)


def resolve_pair(
    faces: Sequence[Face], regular_weight: float, bold_weight: float
) -> tuple[Face, Face]:
    ordered = sorted(faces, key=lambda face: face.weight)
    plain = nearest_face(ordered, regular_weight, heavier_on_tie=False)
    bold = nearest_face(ordered, bold_weight, heavier_on_tie=True)
    if plain.weight != bold.weight:
        return plain, bold
    index = ordered.index(plain)
    lighter = ordered[index - 1] if index > 0 else None
    heavier = ordered[index + 1] if index + 1 < len(ordered) else None
    if bold_weight >= regular_weight:
        return (plain, heavier) if heavier is not None else (lighter, plain)
    return (plain, lighter) if lighter is not None else (heavier, plain)


def candidates_from_paths(
    paths: list[Path], settings: Settings | None = None
) -> list[Candidate]:
    settings = settings or Settings()
    infos = [
        info
        for path in paths
        if (info := read_font_info(path)) is not None
        and not is_half_output(info)
        and not is_italic(info)
        and not is_hidden(info)
    ]
    candidates: list[Candidate] = []
    families_done: set[str] = set()
    for info in infos:
        if info.variable and info.family not in families_done:
            base = " ".join(p for p in info.family.split() if p != "Variable")
            candidates.append(
                Candidate(
                    base,
                    info.path,
                    None,
                    info.kind,
                    plain_weight=clamped(settings.regular_weight, info.weight_range),
                    bold_weight=clamped(settings.bold_weight, info.weight_range),
                )
            )
            families_done.add(info.family)
    statics: dict[str, list[FontInfo]] = {}
    for info in infos:
        if not info.variable and info.family not in families_done:
            statics.setdefault(info.family, []).append(info)
    for family, members in statics.items():
        faces = family_faces(members)
        if len(faces) < 2:
            continue
        plain, bold = resolve_pair(faces, settings.regular_weight, settings.bold_weight)
        kind = next(i.kind for i in members if i.path == plain.path)
        candidates.append(
            Candidate(
                family,
                plain.path,
                bold.path,
                kind,
                faces=faces,
                plain_face=plain,
                bold_face=bold,
                plain_weight=plain.weight,
                bold_weight=bold.weight,
            )
        )
    return candidates


def build_all(
    fonts_dir: Path,
    force: bool = False,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or Settings()
    report: list[str] = []
    for candidate in find_candidates(fonts_dir, settings):
        label = candidate.faces_label
        detail = f"  {label}" if label else ""
        if not force and not candidate.is_stale():
            report.append(f"up to date  {candidate.output.name}  ({candidate.kind})")
            continue
        if dry_run:
            report.append(
                f"would build {candidate.output.name}  "
                f"<- {candidate.family}{detail} ({candidate.kind})"
            )
            continue
        try:
            build_halfbold_font(
                candidate.regular, candidate.bold, candidate.output, settings
            )
            build_bold_face(
                candidate.regular, candidate.bold, candidate.bold_face_output, settings
            )
            report.append(
                f"built       {candidate.output.name}  "
                f"<- {candidate.family}{detail} ({candidate.kind})"
            )
        except (ValueError, TTLibError) as err:
            report.append(f"skipped     {candidate.family} ({candidate.kind}): {err}")
    return report
