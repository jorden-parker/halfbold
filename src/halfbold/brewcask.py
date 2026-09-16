import json
import shutil
import subprocess
import tarfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError

GOOGLE_FONTS_GIT_URL = "https://github.com/google/fonts.git"

ARCHIVE_SUFFIXES = (".tar.gz", ".tar.xz", ".tar")


@dataclass(frozen=True)
class CaskInfo:
    token: str
    url: str
    branch: str
    only_path: str
    fonts: list[str]


def parse_cask_info(data: bytes) -> CaskInfo:
    payload = json.loads(data)
    casks = payload.get("casks") or []
    if not casks:
        raise ValueError("brew info returned no cask")
    cask = casks[0]
    url_specs = cask.get("url_specs") or {}
    fonts = [a["font"][0] for a in cask.get("artifacts", []) if "font" in a]
    return CaskInfo(
        token=cask["token"],
        url=cask.get("url", ""),
        branch=url_specs.get("branch", ""),
        only_path=url_specs.get("only_path", ""),
        fonts=fonts,
    )


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
