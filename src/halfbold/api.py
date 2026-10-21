import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import replace
from pathlib import Path

from fontTools.ttLib import TTLibError

from halfbold.brewcask import (
    cask_font_dir,
    cask_info,
    cask_info_from_payload,
    download_google_face,
    fetch_cask_index,
    font_cask_entries,
    install_cask,
    installed_font_paths,
    search_font_casks,
)
from halfbold.browser import browser_status, setup_browser
from halfbold.build import (
    STYLE_SUFFIX,
    bold_face_path,
    build_bold_face,
    build_halfbold_font,
)
from halfbold.cli import DEFAULT_CSS, DEFAULT_FONTS_DIR
from halfbold.collection import open_font, split_member
from halfbold.reset import (
    VSCODE,
    WEB,
    default_originals_path,
    remember,
    restore_originals,
    vscode_values,
)
from halfbold.scan import (
    KINDS,
    Candidate,
    Face,
    candidates_from_paths,
    find_installed_candidates,
    find_installed_half_families,
    find_installed_half_fonts,
    read_font_info,
)
from halfbold.settings import Settings, load_settings, save_settings
from halfbold.vscode import default_settings_path, use_in_vscode
from halfbold.watcher import default_plist_path, remove_watcher
from halfbold.web import get_web_fonts, set_web_font


def default_cache_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "halfbold"
    return Path(tempfile.gettempdir()) / "halfbold-app"


CACHE_DIR = default_cache_dir()
ORIGINALS_PATH = default_originals_path()
WATCHER_PLIST = default_plist_path()
CASK_INDEX_CACHE = "cask-index.json"
NON_TAG = re.compile(r"[^A-Za-z0-9]")
CACHE_LOCKS: dict[Path, threading.Lock] = {}
CACHE_LOCKS_GUARD = threading.Lock()


def face_payload(face: Face | None) -> dict | None:
    if face is None:
        return None
    return {"path": str(face.path), "style": face.style, "weight": face.weight}


def candidate_payload(candidate: Candidate) -> dict:
    return {
        "family": candidate.family,
        "kind": candidate.kind,
        "regular": str(candidate.regular),
        "bold": None if candidate.bold is None else str(candidate.bold),
        "output": str(candidate.output),
        "built": candidate.output.exists(),
        "stale": candidate.is_stale(),
        "faces": [face_payload(face) for face in candidate.faces],
        "plain_face": face_payload(candidate.plain_face),
        "bold_face": face_payload(candidate.bold_face),
        "plain_weight": candidate.plain_weight,
        "bold_weight": candidate.bold_weight,
        "faces_label": candidate.faces_label,
    }


def candidate_from_files(regular: Path, bold: Path | None) -> Candidate:
    info = read_font_info(regular)
    if info is None:
        raise ValueError(f"{regular} is not a TrueType font")
    family = " ".join(p for p in info.family.split() if p != "Variable")
    return Candidate(family, regular, bold, info.kind)


def faces_tag(candidate: Candidate) -> str:
    if candidate.bold is None:
        plain = candidate.plain_weight or 0
        bold = candidate.bold_weight or 0
        return f"w{round(plain)}-b{round(bold)}"
    plain_face = candidate.plain_face
    bold_face = candidate.bold_face
    if plain_face is None or bold_face is None:
        return f"{tag_part(candidate.regular.stem)}-{tag_part(candidate.bold.stem)}"
    return (
        f"{tag_part(plain_face.path.stem)}{round(plain_face.weight)}"
        f"-{tag_part(bold_face.path.stem)}{round(bold_face.weight)}"
    )


def tag_part(text: str) -> str:
    return NON_TAG.sub("", text) or "x"


def is_fresh(target: Path, sources: list[Path]) -> bool:
    if not target.exists():
        return False
    built = target.stat().st_mtime
    return all(path.stat().st_mtime <= built for path in sources)


def cache_lock(path: Path) -> threading.Lock:
    with CACHE_LOCKS_GUARD:
        return CACHE_LOCKS.setdefault(path, threading.Lock())


def build_into_cache(candidate: Candidate, half: Path, settings: Settings) -> None:
    with cache_lock(half):
        if is_fresh(half, candidate.sources):
            return
        part = half.with_name(f"{half.name}.{os.getpid()}.{threading.get_ident()}.part")
        try:
            build_halfbold_font(candidate.regular, candidate.bold, part, settings)
            os.replace(part, half)
        finally:
            part.unlink(missing_ok=True)


def standalone_face(path: Path) -> Path:
    file, number = split_member(path)
    if number is None:
        return path
    folder = CACHE_DIR / "collections" / file.parent.relative_to(file.anchor)
    target = folder / f"{file.stem}-{number}.ttf"
    if not is_fresh(target, [file]):
        extract_into_cache(path, target)
    return target


def extract_into_cache(path: Path, target: Path) -> None:
    with cache_lock(target):
        if is_fresh(target, [split_member(path)[0]]):
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(
            f"{target.name}.{os.getpid()}.{threading.get_ident()}.part"
        )
        try:
            with open_font(path) as font:
                font.save(part)
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)


def face_file(args: argparse.Namespace) -> dict:
    return {"path": str(standalone_face(args.path))}


def preview_half(
    candidate: Candidate,
    settings: Settings | None = None,
    cache_dir: Path | None = None,
) -> Path:
    settings = settings or load_settings()
    cache_dir = cache_dir or CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    stem = candidate.output.stem
    tag = f"{settings.rules_tag()}-{faces_tag(candidate)}"
    half = cache_dir / f"{stem}.{tag}{candidate.output.suffix}"
    if not is_fresh(half, candidate.sources):
        build_into_cache(candidate, half, settings)
    return half


def installed(args: argparse.Namespace) -> dict:
    return {
        "fonts_dir": str(args.fonts_dir),
        "candidates": [
            candidate_payload(c)
            for c in find_installed_candidates(args.fonts_dir, load_settings())
        ],
    }


def build(args: argparse.Namespace) -> dict:
    output = args.output or args.regular.with_name(f"{args.regular.stem}-Half.ttf")
    settings = load_settings()
    letters = build_halfbold_font(args.regular, args.bold, output, settings)
    build_bold_face(args.regular, args.bold, bold_face_path(output), settings)
    return {
        "output": str(output),
        "bold_face": str(bold_face_path(output)),
        "letters": len(letters),
        "settings": settings.as_dict(),
    }


def candidate_from_family(faces: list[Path], settings: Settings) -> Candidate:
    found = candidates_from_paths(faces, settings)
    if len(found) != 1:
        raise ValueError(f"{len(found)} convertible families in {len(faces)} faces")
    return found[0]


def preview(args: argparse.Namespace) -> dict:
    settings = load_settings()
    if args.faces:
        candidate = candidate_from_family(args.faces, settings)
        if args.fonts_dir is not None:
            candidate = replace(candidate, output_dir=args.fonts_dir)
    else:
        candidate = candidate_from_files(args.regular, args.bold)
    return candidate_payload(candidate) | {
        "half": str(preview_half(candidate, settings)),
        "settings": settings.as_dict(),
    }


def cask_index() -> list[dict]:
    return fetch_cask_index(CACHE_DIR / CASK_INDEX_CACHE)


def casks(args: argparse.Namespace) -> dict:
    try:
        return {"casks": font_cask_entries(cask_index())}
    except ValueError:
        tokens = search_font_casks()
        return {"casks": [{"token": t, "name": t, "google": False} for t in tokens]}


def cached_cask_fonts(token: str) -> list[Path]:
    into = CACHE_DIR / "casks" / token
    fonts = sorted(into.rglob("*.ttf")) if into.is_dir() else []
    if fonts:
        return fonts
    into.mkdir(parents=True, exist_ok=True)
    cask_font_dir(token, into)
    return sorted(into.rglob("*.ttf"))


def unconvertible_reason(token: str, into: Path) -> str:
    files = sorted(p for p in into.rglob("*") if p.suffix.lower() in {".ttf", ".otf"})
    infos = [
        info
        for path in files
        if not path.name.startswith("._") and (info := read_font_info(path))
    ]
    if not infos:
        return f"{token} contains no font files halfbold can read"
    families: dict[str, list[str]] = {}
    for info in infos:
        families.setdefault(info.family, []).append(info.style)
    described = "; ".join(
        f"{family} ({', '.join(styles)})" for family, styles in families.items()
    )
    hint = "halfbold needs two weights of the same family or a variable font"
    if all(p.suffix.lower() == ".otf" for p in files):
        hint += ", and .otf files with CFF outlines are not supported"
    return f"{token} only has {described}. {hint}."


def cask_fonts(args: argparse.Namespace) -> dict:
    candidates = candidates_from_paths(cached_cask_fonts(args.token), load_settings())
    if not candidates:
        raise ValueError(
            unconvertible_reason(args.token, CACHE_DIR / "casks" / args.token)
        )
    return {
        "token": args.token,
        "candidates": [candidate_payload(c) for c in candidates],
    }


def cask_face(args: argparse.Namespace) -> dict:
    entry = next((c for c in cask_index() if c.get("token") == args.token), None)
    if entry is None:
        raise ValueError(f"unknown cask: {args.token}")
    face = download_google_face(
        cask_info_from_payload(entry), CACHE_DIR / "faces" / args.token
    )
    return {"token": args.token, "face": None if face is None else str(face)}


def cask_install(args: argparse.Namespace) -> dict:
    install_cask(args.token)
    paths = installed_font_paths(cask_info(args.token), args.fonts_dir)
    return {
        "token": args.token,
        "candidates": [
            candidate_payload(c) for c in candidates_from_paths(paths, load_settings())
        ],
    }


def settings_command(args: argparse.Namespace) -> dict:
    current = load_settings()
    if args.values:
        current = current.merged(json.loads(args.values))
        save_settings(current)
    return {"settings": current.as_dict(), "defaults": Settings().as_dict()}


def installed_half_family(family: str, fonts_dir: Path) -> str:
    if not family.endswith(f" {STYLE_SUFFIX}"):
        family = f"{family} {STYLE_SUFFIX}"
    if family not in find_installed_half_families(fonts_dir):
        raise ValueError(f"{family!r} is not installed in {fonts_dir}")
    return family


def web(args: argparse.Namespace) -> dict:
    if args.kind:
        family = installed_half_family(args.family, args.fonts_dir)
        remember(ORIGINALS_PATH, WEB, get_web_fonts(args.css))
        set_web_font(args.css, args.kind, family)
    return get_web_fonts(args.css)


def vscode(args: argparse.Namespace) -> dict:
    family = installed_half_family(args.family, args.fonts_dir)
    remember(ORIGINALS_PATH, VSCODE, vscode_values(args.settings))
    return use_in_vscode(args.settings, family)


def delete_half_fonts(fonts_dir: Path) -> list[str]:
    fonts = find_installed_half_fonts(fonts_dir)
    for path in fonts:
        path.unlink()
    return sorted(set(fonts.values()))


def reset(args: argparse.Namespace) -> dict:
    restored = restore_originals(ORIGINALS_PATH, args.css, args.settings)
    watcher_removed = args.delete_fonts and remove_watcher(WATCHER_PLIST)
    deleted = delete_half_fonts(args.fonts_dir) if args.delete_fonts else []
    return {
        "restored": restored,
        "deleted": deleted,
        "watcher_removed": watcher_removed,
        "web": get_web_fonts(args.css),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="halfbold-api")
    subparsers = parser.add_subparsers(dest="command", required=True)

    installed_parser = subparsers.add_parser("installed")
    installed_parser.add_argument("--fonts-dir", type=Path, default=DEFAULT_FONTS_DIR)
    installed_parser.set_defaults(handler=installed)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("regular", type=Path)
    build_parser.add_argument("bold", type=Path, nargs="?")
    build_parser.add_argument("-o", "--output", type=Path)
    build_parser.set_defaults(handler=build)

    preview_parser = subparsers.add_parser("preview")
    preview_parser.add_argument("regular", type=Path, nargs="?")
    preview_parser.add_argument("bold", type=Path, nargs="?")
    preview_parser.add_argument("--face", type=Path, action="append", dest="faces")
    preview_parser.add_argument("--fonts-dir", type=Path)
    preview_parser.set_defaults(handler=preview)

    casks_parser = subparsers.add_parser("casks")
    casks_parser.set_defaults(handler=casks)

    cask_fonts_parser = subparsers.add_parser("cask-fonts")
    cask_fonts_parser.add_argument("token")
    cask_fonts_parser.set_defaults(handler=cask_fonts)

    cask_face_parser = subparsers.add_parser("cask-face")
    cask_face_parser.add_argument("token")
    cask_face_parser.set_defaults(handler=cask_face)

    face_file_parser = subparsers.add_parser("face-file")
    face_file_parser.add_argument("path", type=Path)
    face_file_parser.set_defaults(handler=face_file)

    cask_install_parser = subparsers.add_parser("cask-install")
    cask_install_parser.add_argument("token")
    cask_install_parser.add_argument(
        "--fonts-dir", type=Path, default=DEFAULT_FONTS_DIR
    )
    cask_install_parser.set_defaults(handler=cask_install)

    web_parser = subparsers.add_parser("web")
    web_parser.add_argument("kind", nargs="?", choices=KINDS)
    web_parser.add_argument("family", nargs="?")
    web_parser.add_argument("--css", type=Path, default=DEFAULT_CSS)
    web_parser.add_argument("--fonts-dir", type=Path, default=DEFAULT_FONTS_DIR)
    web_parser.set_defaults(handler=web)

    vscode_parser = subparsers.add_parser("vscode")
    vscode_parser.add_argument("family")
    vscode_parser.add_argument("--settings", type=Path, default=default_settings_path())
    vscode_parser.add_argument("--fonts-dir", type=Path, default=DEFAULT_FONTS_DIR)
    vscode_parser.set_defaults(handler=vscode)

    reset_parser = subparsers.add_parser("reset")
    reset_parser.add_argument("--delete-fonts", action="store_true")
    reset_parser.add_argument("--css", type=Path, default=DEFAULT_CSS)
    reset_parser.add_argument("--settings", type=Path, default=default_settings_path())
    reset_parser.add_argument("--fonts-dir", type=Path, default=DEFAULT_FONTS_DIR)
    reset_parser.set_defaults(handler=reset)
    browser_parser = subparsers.add_parser("browser")
    browser_parser.add_argument("--setup", action="store_true")
    browser_parser.set_defaults(
        handler=lambda args: (
            setup_browser(DEFAULT_CSS) if args.setup else browser_status(DEFAULT_CSS)
        )
    )

    settings_parser = subparsers.add_parser("settings")
    settings_parser.add_argument("values", nargs="?")
    settings_parser.set_defaults(handler=settings_command)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.set_defaults(handler=None)

    args = parser.parse_args(argv)
    if args.command == "web" and args.kind and not args.family:
        parser.error("web KIND requires FAMILY")
    if args.command == "preview" and bool(args.regular) == bool(args.faces):
        parser.error("preview takes either REGULAR or --face, not both")
    return args


API_ERRORS = (ValueError, TTLibError, OSError, subprocess.SubprocessError)


def handle(argv: list[str]) -> dict:
    args = parse_args(argv)
    if args.handler is None:
        raise ValueError("serve cannot be nested")
    return args.handler(args)


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    write_lock = threading.Lock()

    def respond(payload: dict) -> None:
        with write_lock:
            stdout.write(json.dumps(payload) + "\n")
            stdout.flush()

    def work(request: dict) -> None:
        request_id = request.get("id")
        try:
            result = handle([str(a) for a in request.get("args", [])])
            respond({"id": request_id, "ok": True, "result": result})
        except (*API_ERRORS, SystemExit) as err:
            respond({"id": request_id, "ok": False, "error": str(err)})

    threads: list[threading.Thread] = []
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        thread = threading.Thread(target=work, args=(request,), daemon=True)
        thread.start()
        threads = [t for t in threads if t.is_alive()]
        threads.append(thread)
    for thread in threads:
        thread.join()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.handler is None:
        return serve()
    try:
        payload = args.handler(args)
    except API_ERRORS as err:
        print(json.dumps({"error": str(err)}))
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
