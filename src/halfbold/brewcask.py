import json
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError

GOOGLE_FONTS_GIT_URL = "https://github.com/google/fonts.git"
FONT_CASK_PREFIX = "font-"
CASK_INDEX_URL = "https://formulae.brew.sh/api/cask.json"
CASK_INDEX_MAX_AGE = 24 * 60 * 60

ARCHIVE_SUFFIXES = (".tar.gz", ".tar.xz", ".tar")


@dataclass(frozen=True)
class CaskInfo:
    token: str
    url: str
    branch: str
    only_path: str
    fonts: list[str]
    targets: list[str]


def cask_info_from_payload(cask: dict) -> CaskInfo:
    url_specs = cask.get("url_specs") or {}
    artifacts = [a for a in cask.get("artifacts", []) if "font" in a]
    fonts = [a["font"][0] for a in artifacts]
    targets = [a.get("target", "") for a in artifacts]
    return CaskInfo(
        token=cask["token"],
        url=cask.get("url", ""),
        branch=url_specs.get("branch", ""),
        only_path=url_specs.get("only_path", ""),
        fonts=fonts,
        targets=targets,
    )


def parse_cask_info(data: bytes) -> CaskInfo:
    payload = json.loads(data)
    casks = payload.get("casks") or []
    if not casks:
        raise ValueError("brew info returned no cask")
    return cask_info_from_payload(casks[0])


def cask_info(token: str) -> CaskInfo:
    try:
        result = subprocess.run(
            ["brew", "info", "--cask", "--json=v2", token],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as err:
        stderr = err.stderr.decode() if err.stderr else str(err)
        raise ValueError(f"brew info failed: {stderr.strip()}") from err
    return parse_cask_info(result.stdout)


def fetch_cask_index(cache: Path, max_age: float = CASK_INDEX_MAX_AGE) -> list[dict]:
    if cache.exists() and time.time() - cache.stat().st_mtime < max_age:
        return json.loads(cache.read_text())
    try:
        with urllib.request.urlopen(CASK_INDEX_URL, timeout=60) as response:
            data = response.read()
    except URLError as err:
        if cache.exists():
            return json.loads(cache.read_text())
        raise ValueError(f"cask index download failed: {err.reason}") from err
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return json.loads(data)


def is_google_fonts_cask(cask: dict) -> bool:
    url_specs = cask.get("url_specs") or {}
    return cask.get("url") == GOOGLE_FONTS_GIT_URL and bool(url_specs.get("only_path"))


ITALIC_MARKERS = ("italic", "oblique")
VARIABLE_MARKERS = ("[", "variable", "-vf", "vf.")
REGULAR_SUFFIXES = ("regular", "book", "roman", "normal", "medium")


def artifact_font_files(cask: dict) -> list[str]:
    files = []
    for artifact in cask.get("artifacts") or []:
        fonts = artifact.get("font") if isinstance(artifact, dict) else None
        if isinstance(fonts, str):
            fonts = [fonts]
        for font in fonts or []:
            files.append(font.rsplit("/", 1)[-1])
    return files


def _style_split(stem: str) -> tuple[str, str]:
    lowered = stem.lower().replace("_", "-").replace(" ", "-")
    if "-" in lowered:
        base, style = lowered.rsplit("-", 1)
        return base, style
    for suffix in ("bold", *REGULAR_SUFFIXES):
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            return lowered[: -len(suffix)], suffix
    return lowered, ""


def cask_is_convertible(cask: dict) -> bool:
    stems = []
    for name in artifact_font_files(cask):
        lowered = name.lower()
        if not lowered.endswith(".ttf"):
            continue
        stem = lowered[: -len(".ttf")]
        if any(marker in stem for marker in ITALIC_MARKERS):
            continue
        if any(marker in stem for marker in VARIABLE_MARKERS):
            return True
        stems.append(_style_split(stem))
    bases_with_bold = {base for base, style in stems if style == "bold"}
    for base, style in stems:
        if base in bases_with_bold and style in ("", *REGULAR_SUFFIXES):
            return True
    return False


def font_cask_entries(index: list[dict]) -> list[dict]:
    entries = []
    for cask in index:
        token = cask.get("token", "")
        if not token.startswith(FONT_CASK_PREFIX) or not cask_is_convertible(cask):
            continue
        names = cask.get("name") or []
        entries.append(
            {
                "token": token,
                "name": ", ".join(names) or token,
                "google": is_google_fonts_cask(cask),
            }
        )
    return sorted(entries, key=lambda e: e["name"].lower())


def google_fonts_urls(info: CaskInfo) -> list[str]:
    if info.url != GOOGLE_FONTS_GIT_URL or not info.only_path:
        return []
    branch = info.branch or "main"
    urls = []
    for font in info.fonts:
        lowered = font.lower()
        if not lowered.endswith(".ttf") or "italic" in lowered:
            continue
        urls.append(
            f"https://raw.githubusercontent.com/google/fonts/{branch}/"
            f"{info.only_path}/{urllib.parse.quote(font)}"
        )
    return urls


def download_google_face(info: CaskInfo, into: Path) -> Path | None:
    urls = google_fonts_urls(info)
    if not urls:
        return None
    url = urls[0]
    path = into / urllib.parse.unquote(Path(url).name)
    if path.exists():
        return path
    into.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            path.write_bytes(response.read())
    except URLError as err:
        raise ValueError(f"download failed: {url}: {err.reason}") from err
    return path


def download_google_fonts(info: CaskInfo, into: Path) -> list[Path]:
    paths = []
    for url in google_fonts_urls(info):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read()
        except URLError as err:
            raise ValueError(f"download failed: {url}: {err.reason}") from err
        path = into / urllib.parse.unquote(Path(url).name)
        path.write_bytes(content)
        paths.append(path)
    return paths


def fetch_cask_archive(token: str) -> Path:
    try:
        subprocess.run(
            ["brew", "fetch", "--cask", token],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as err:
        stderr = err.stderr.decode() if err.stderr else str(err)
        raise ValueError(f"brew fetch failed: {stderr.strip()}") from err
    try:
        result = subprocess.run(
            ["brew", "--cache", "--cask", token],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as err:
        stderr = err.stderr.decode() if err.stderr else str(err)
        raise ValueError(f"brew --cache failed: {stderr.strip()}") from err
    path = Path(result.stdout.decode().strip())
    if not path.exists():
        raise ValueError(f"brew fetch left no file at {path}")
    return path


def _extract_zip(archive: Path, into: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            normalized = Path(member)
            if normalized.is_absolute() or ".." in normalized.parts:
                raise ValueError("unsafe archive member")
        zf.extractall(into)


def _extract_dmg(archive: Path, into: Path) -> list[Path]:
    mount = into / "dmg"
    mount.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "hdiutil",
            "attach",
            "-nobrowse",
            "-readonly",
            "-mountpoint",
            str(mount),
            str(archive),
        ],
        capture_output=True,
        check=True,
    )
    try:
        fonts_dir = into / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)
        found = []
        for pattern in ("*.ttf", "*.otf"):
            for path in mount.rglob(pattern):
                dest = fonts_dir / path.name
                shutil.copy2(path, dest)
                found.append(dest)
        return found
    finally:
        subprocess.run(
            ["hdiutil", "detach", str(mount)],
            capture_output=True,
            check=True,
        )


def extract_fonts(archive: Path, into: Path) -> list[Path]:
    name = archive.name.lower()
    if name.endswith((".ttf", ".otf")):
        dest = into / archive.name
        shutil.copy2(archive, dest)
    elif name.endswith(".zip"):
        _extract_zip(archive, into)
    elif name.endswith(ARCHIVE_SUFFIXES) or name.endswith((".tgz", ".txz")):
        with tarfile.open(archive) as tf:
            tf.extractall(into, filter="data")
    elif name.endswith(".dmg"):
        _extract_dmg(archive, into)
    else:
        raise ValueError(f"cannot preview {archive.name}: unsupported download format")
    return sorted(into.rglob("*.ttf"))


def cask_font_dir(token: str, into: Path) -> Path:
    info = cask_info(token)
    urls = google_fonts_urls(info)
    if urls:
        download_google_fonts(info, into)
    elif info.url.endswith(".git"):
        raise ValueError(
            f"{token} is a git-based cask that is not on Google Fonts; "
            "install it to preview"
        )
    else:
        extract_fonts(fetch_cask_archive(token), into)
    return into


def search_font_casks() -> list[str]:
    try:
        result = subprocess.run(
            ["brew", "search", "--cask", FONT_CASK_PREFIX],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as err:
        stderr = err.stderr.decode() if err.stderr else str(err)
        raise ValueError(f"brew search failed: {stderr.strip()}") from err
    return parse_font_cask_tokens(result.stdout.decode())


def parse_font_cask_tokens(text: str) -> list[str]:
    tokens = [line.strip() for line in text.splitlines()]
    return [t for t in tokens if t.startswith(FONT_CASK_PREFIX)]


def install_cask(token: str) -> None:
    try:
        subprocess.run(
            ["brew", "install", "--cask", token],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as err:
        stderr = err.stderr.decode() if err.stderr else str(err)
        raise ValueError(f"brew install failed: {stderr.strip()}") from err


def installed_font_paths(info: CaskInfo, fonts_dir: Path) -> list[Path]:
    paths = []
    for font, target in zip(info.fonts, info.targets, strict=True):
        path = Path(target) if target else fonts_dir / Path(font).name
        if path.exists():
            paths.append(path)
    return paths
