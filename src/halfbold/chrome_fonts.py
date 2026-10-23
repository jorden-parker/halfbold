import hashlib
import hmac
import struct
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError

from halfbold.build import STYLE_SUFFIX, build_bold_face, build_halfbold_font
from halfbold.collection import open_font, source_file
from halfbold.scan import (
    Candidate,
    Face,
    FontInfo,
    candidates_from_paths,
    is_half_output,
    is_hidden,
    is_italic,
    read_font_info,
    resolve_pair,
)
from halfbold.settings import Settings

SERVED_FONT_VERSION = 1
SERVED_FONTS_QUOTA_BYTES = 512 * 1024 * 1024
MAX_FAMILY_NAME_LENGTH = 200
PRIVATE_USE_AREA = range(0xE000, 0xF900)
VARIABLE_SUFFIX = " Variable"


@dataclass(frozen=True)
class WebFace:
    weight: tuple[float, float]
    data: bytes
    style: str = "normal"
    unicode_range: str = ""

    @property
    def is_variable_between(self) -> bool:
        return self.weight[0] < self.weight[1]

    def covers(self, weight: float) -> bool:
        return self.weight[0] <= weight <= self.weight[1]


@dataclass(frozen=True)
class ServedFace:
    weight: str
    style: str = "normal"
    unicode_range: str = ""
    file: str | None = None
    local: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Conversion:
    faces: list[ServedFace] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "faces": [face.as_dict() for face in self.faces],
            "unchanged": self.unchanged,
        }


def served_key(sources: Sequence[bytes], settings: Settings, secret: bytes) -> str:
    digest = hmac.new(
        secret,
        f"{SERVED_FONT_VERSION}:{settings.cache_tag()}".encode(),
        hashlib.sha256,
    )
    for source in sources:
        digest.update(hashlib.sha256(source).digest())
    return digest.hexdigest()[:32]


def is_icon_font(font: TTFont) -> bool:
    cmap = font.getBestCmap() or {}
    private = sum(codepoint in PRIVATE_USE_AREA for codepoint in cmap)
    return private * 2 > len(cmap)


@dataclass(frozen=True)
class WebfontLimits:
    seconds: float = 30
    cpu_seconds: int = 30
    memory_bytes: int = 1 << 30


DEFAULT_WEBFONT_LIMITS = WebfontLimits()
MAX_EXPANDED_BYTES = 128 << 20
WOFF_SIGNATURES = (b"wOFF", b"wOF2")
TOTAL_SFNT_SIZE = struct.Struct(">L")
TOTAL_SFNT_SIZE_OFFSET = 16
RESIDENT_POLL_SECONDS = 0.05
KIBIBYTE = 1024


def declared_expanded_size(data: bytes) -> int | None:
    if data[:4] not in WOFF_SIGNATURES or len(data) < TOTAL_SFNT_SIZE_OFFSET + 4:
        return None
    return TOTAL_SFNT_SIZE.unpack_from(data, TOTAL_SFNT_SIZE_OFFSET)[0]


def write_webfont_truetype(
    data: bytes, path: Path, limits: WebfontLimits = DEFAULT_WEBFONT_LIMITS
) -> Path:
    expanded = declared_expanded_size(data)
    if expanded is not None and expanded > MAX_EXPANDED_BYTES:
        raise ValueError("web font declares too large an expansion")
    source = path.with_suffix(".webfont")
    source.write_bytes(data)
    convert_in_child(source, path, limits)
    with TTFont(path) as font:
        if is_icon_font(font):
            raise ValueError("icon font")
    return path


def convert_in_child(source: Path, target: Path, limits: WebfontLimits) -> None:
    command = [
        sys.executable,
        "-I",
        "-m",
        "halfbold.webfont_child",
        str(source),
        str(target),
        str(limits.cpu_seconds),
        str(limits.memory_bytes),
    ]
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as child:
        wait_for_child(child, limits)
    if child.returncode != 0:
        raise ValueError("web font could not be converted")


def wait_for_child(child: subprocess.Popen, limits: WebfontLimits) -> None:
    deadline = time.monotonic() + limits.seconds
    while child.poll() is None:
        if (
            time.monotonic() > deadline
            or resident_bytes(child.pid) > limits.memory_bytes
        ):
            child.kill()
            child.wait()
            raise ValueError("web font conversion exceeded its limits")
        time.sleep(RESIDENT_POLL_SECONDS)


def resident_bytes(pid: int) -> int:
    completed = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    )
    digits = completed.stdout.strip()
    return int(digits) * KIBIBYTE if digits.isdigit() else 0


def prune_served_fonts(fonts_dir: Path) -> None:
    fonts = sorted(
        (path for path in fonts_dir.glob("*.ttf")),
        key=lambda path: path.stat().st_mtime,
    )
    total = sum(path.stat().st_size for path in fonts)
    for path in fonts[:-1]:
        if total <= SERVED_FONTS_QUOTA_BYTES:
            break
        total -= path.stat().st_size
        path.unlink()


def served_half(
    key: str, fonts_dir: Path, plain: Path, bold: Path | None, settings: Settings
) -> str:
    name = f"{key}.ttf"
    output = fonts_dir / name
    if not output.exists():
        fonts_dir.mkdir(parents=True, exist_ok=True)
        partial = output.with_suffix(".part")
        build_halfbold_font(plain, bold, partial, settings)
        partial.replace(output)
        prune_served_fonts(fonts_dir)
    return name


def served_bold(
    key: str, fonts_dir: Path, plain: Path, bold: Path | None, settings: Settings
) -> str:
    name = f"{key}-bold.ttf"
    output = fonts_dir / name
    if not output.exists():
        fonts_dir.mkdir(parents=True, exist_ok=True)
        partial = output.with_suffix(".part")
        build_bold_face(plain, bold, partial, settings)
        partial.replace(output)
        prune_served_fonts(fonts_dir)
    return name


def webfont_pair(
    faces: Sequence[WebFace], settings: Settings
) -> tuple[WebFace, WebFace | None]:
    for face in faces:
        if face.covers(settings.regular_weight) and face.covers(settings.bold_weight):
            return face, None
    weighted = [
        Face(Path(str(index)), face.style, round(face.weight[0]))
        for index, face in enumerate(faces)
    ]
    if len({face.weight for face in weighted}) < 2:
        raise ValueError("needs a second weight")
    plain, bold = resolve_pair(weighted, settings.regular_weight, settings.bold_weight)
    return faces[int(str(plain.path))], faces[int(str(bold.path))]


def plain_weight_descriptor(face: WebFace, settings: Settings) -> str:
    if face.is_variable_between:
        return f"{round(settings.regular_weight)}"
    return f"{round(face.weight[0])}"


def convert_webfont_group(
    faces: Sequence[WebFace],
    fonts_dir: Path,
    settings: Settings,
    secret: bytes,
    limits: WebfontLimits,
) -> ServedFace:
    plain, bold = webfont_pair(faces, settings)
    sources = [plain.data] if bold is None else [plain.data, bold.data]
    key = served_key(sources, settings, secret)
    with tempfile.TemporaryDirectory() as scratch:
        plain_path = write_webfont_truetype(
            plain.data, Path(scratch) / "plain.ttf", limits
        )
        bold_path = None
        if bold is not None:
            bold_path = write_webfont_truetype(
                bold.data, Path(scratch) / "bold.ttf", limits
            )
        name = served_half(key, fonts_dir, plain_path, bold_path, settings)
    return ServedFace(
        plain_weight_descriptor(plain, settings),
        plain.style,
        plain.unicode_range,
        file=name,
    )


def webfont_groups(faces: Sequence[WebFace]) -> dict[tuple[str, str], list[WebFace]]:
    groups: dict[tuple[str, str], list[WebFace]] = {}
    for face in faces:
        groups.setdefault((face.style, face.unicode_range), []).append(face)
    return groups


def group_label(style: str, unicode_range: str) -> str:
    return f"{style} {unicode_range}".strip()


def convert_webfont_family(
    faces: Sequence[WebFace],
    fonts_dir: Path,
    settings: Settings,
    secret: bytes,
    limits: WebfontLimits = DEFAULT_WEBFONT_LIMITS,
) -> Conversion:
    conversion = Conversion()
    for (style, unicode_range), group in webfont_groups(faces).items():
        try:
            conversion.faces.append(
                convert_webfont_group(group, fonts_dir, settings, secret, limits)
            )
        except (ValueError, TTLibError) as error:
            conversion.unchanged.append(f"{group_label(style, unicode_range)}: {error}")
    return conversion


def family_key(family: str) -> str:
    return family.removesuffix(VARIABLE_SUFFIX).casefold()


def family_members(family: str, face_paths: Sequence[Path]) -> list[FontInfo]:
    wanted = family_key(family)
    return [
        info
        for path in face_paths
        if (info := read_font_info(path)) is not None
        and not is_half_output(info)
        and not is_hidden(info)
        and family_key(info.family) == wanted
    ]


def local_names(path: Path) -> tuple[str, ...]:
    font = open_font(path, lazy=True)
    try:
        names = (font["name"].getDebugName(4), font["name"].getDebugName(6))
    finally:
        font.close()
    return tuple(name for name in names if name)


def file_identity(path: Path) -> bytes:
    stat = source_file(path).stat()
    return f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode()


def local_face(info: FontInfo) -> ServedFace:
    weight = f"{info.weight}"
    if info.weight_range is not None:
        weight = f"{round(info.weight_range[0])} {round(info.weight_range[1])}"
    style = "italic" if is_italic(info) else "normal"
    return ServedFace(weight, style, local=local_names(info.path))


def installed_half_faces(
    candidate: Candidate, fonts_dir: Path, settings: Settings, secret: bytes
) -> list[ServedFace]:
    settings = settings.for_family(candidate.family)
    paths = [path for path in (candidate.regular, candidate.bold) if path is not None]
    key = served_key([file_identity(path) for path in paths], settings, secret)
    plain = served_half(key, fonts_dir, candidate.regular, candidate.bold, settings)
    bold = served_bold(key, fonts_dir, candidate.regular, candidate.bold, settings)
    return [
        ServedFace(f"{round(candidate.plain_weight or 400)}", file=plain),
        ServedFace(f"{round(candidate.bold_weight or 700)}", file=bold),
    ]


def convert_installed_family(
    family: str,
    face_paths: Sequence[Path],
    fonts_dir: Path,
    settings: Settings,
    secret: bytes,
) -> Conversion:
    if len(family) > MAX_FAMILY_NAME_LENGTH:
        return Conversion(unchanged=["family name too long"])
    members = family_members(family, face_paths)
    if not members:
        return Conversion(unchanged=[f"{family}: not installed"])
    candidates = candidates_from_paths([info.path for info in members], settings)
    if not candidates:
        return Conversion(unchanged=[f"{family}: needs a second weight"])
    candidate = candidates[0]
    try:
        served = installed_half_faces(candidate, fonts_dir, settings, secret)
    except (ValueError, TTLibError) as error:
        return Conversion(unchanged=[f"{family}: {error}"])
    replaced = {candidate.regular, candidate.bold}
    others = [local_face(info) for info in members if info.path not in replaced]
    return Conversion(faces=served + others)


def install_half_family(
    family: str, face_paths: Sequence[Path], fonts_dir: Path, settings: Settings
) -> str | None:
    members = family_members(family, face_paths)
    candidates = candidates_from_paths([info.path for info in members], settings)
    if not candidates:
        return None
    candidate = replace(candidates[0], output_dir=fonts_dir)
    settings = settings.for_family(candidate.family)
    if candidate.is_stale():
        build_halfbold_font(
            candidate.regular, candidate.bold, candidate.output, settings
        )
        build_bold_face(
            candidate.regular, candidate.bold, candidate.bold_face_output, settings
        )
    return f"{candidate.family} {STYLE_SUFFIX}"


def prepare_default_fonts(
    families: dict[str, str],
    face_paths: Sequence[Path],
    fonts_dir: Path,
    settings: Settings,
) -> dict[str, str]:
    installed: dict[str, str] = {}
    for generic, family in families.items():
        try:
            half_family = install_half_family(family, face_paths, fonts_dir, settings)
        except ValueError, TTLibError:
            continue
        if half_family is not None:
            installed[generic] = half_family
    return installed
