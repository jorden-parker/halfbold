import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from fontTools.ttLib import TTLibError

from halfbold.brewcask import (
    cask_font_dir,
    cask_info,
    install_cask,
    installed_font_paths,
    search_font_casks,
)
from halfbold.build import STYLE_SUFFIX, build_halfbold_font
from halfbold.cli import DEFAULT_CSS, DEFAULT_FONTS_DIR
from halfbold.scan import (
    KINDS,
    Candidate,
    candidates_from_paths,
    find_candidates,
    find_installed_half_families,
    read_font_info,
)
from halfbold.web import get_web_fonts, set_web_font

CACHE_DIR = Path(tempfile.gettempdir()) / "halfbold-app"


def candidate_payload(candidate: Candidate) -> dict:
    return {
        "family": candidate.family,
        "kind": candidate.kind,
        "regular": str(candidate.regular),
        "bold": None if candidate.bold is None else str(candidate.bold),
        "output": str(candidate.output),
        "built": candidate.output.exists(),
        "stale": candidate.is_stale(),
    }


def candidate_from_files(regular: Path, bold: Path | None) -> Candidate:
    info = read_font_info(regular)
    if info is None:
        raise ValueError(f"{regular} is not a TrueType font")
    family = " ".join(p for p in info.family.split() if p != "Variable")
    return Candidate(family, regular, bold, info.kind)


def preview_half(candidate: Candidate, cache_dir: Path | None = None) -> Path:
    cache_dir = cache_dir or CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    half = cache_dir / candidate.output.name
    if half.exists():
        built = half.stat().st_mtime
        if all(p.stat().st_mtime <= built for p in candidate.sources):
            return half
    build_halfbold_font(candidate.regular, candidate.bold, half)
    return half


def installed(args: argparse.Namespace) -> dict:
    return {
        "fonts_dir": str(args.fonts_dir),
        "candidates": [candidate_payload(c) for c in find_candidates(args.fonts_dir)],
    }


def build(args: argparse.Namespace) -> dict:
    output = args.output or args.regular.with_name(f"{args.regular.stem}-Half.ttf")
    letters = build_halfbold_font(args.regular, args.bold, output)
    return {"output": str(output), "letters": len(letters)}


def preview(args: argparse.Namespace) -> dict:
    candidate = candidate_from_files(args.regular, args.bold)
    return {
        "family": candidate.family,
        "kind": candidate.kind,
        "regular": str(candidate.regular),
        "bold": None if candidate.bold is None else str(candidate.bold),
        "half": str(preview_half(candidate)),
    }


def casks(args: argparse.Namespace) -> dict:
    return {"casks": search_font_casks()}


def cask_fonts(args: argparse.Namespace) -> dict:
    into = CACHE_DIR / "casks" / args.token
    shutil.rmtree(into, ignore_errors=True)
    into.mkdir(parents=True)
    cask_font_dir(args.token, into)
    candidates = candidates_from_paths(sorted(into.rglob("*.ttf")))
    if not candidates:
        raise ValueError(
            f"no Regular + Bold pair or variable TrueType font in {args.token}"
        )
    return {
        "token": args.token,
        "candidates": [candidate_payload(c) for c in candidates],
    }


def cask_install(args: argparse.Namespace) -> dict:
    install_cask(args.token)
    paths = installed_font_paths(cask_info(args.token), args.fonts_dir)
    return {
        "token": args.token,
        "candidates": [candidate_payload(c) for c in candidates_from_paths(paths)],
    }


def web(args: argparse.Namespace) -> dict:
    if args.kind:
        family = args.family
        if not family.endswith(f" {STYLE_SUFFIX}"):
            family = f"{family} {STYLE_SUFFIX}"
        if family not in find_installed_half_families(args.fonts_dir):
            raise ValueError(f"{family!r} is not installed in {args.fonts_dir}")
        set_web_font(args.css, args.kind, family)
    return get_web_fonts(args.css)


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
    preview_parser.add_argument("regular", type=Path)
    preview_parser.add_argument("bold", type=Path, nargs="?")
    preview_parser.set_defaults(handler=preview)

    casks_parser = subparsers.add_parser("casks")
    casks_parser.set_defaults(handler=casks)

    cask_fonts_parser = subparsers.add_parser("cask-fonts")
    cask_fonts_parser.add_argument("token")
    cask_fonts_parser.set_defaults(handler=cask_fonts)

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

    args = parser.parse_args(argv)
    if args.command == "web" and args.kind and not args.family:
        parser.error("web KIND requires FAMILY")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = args.handler(args)
    except (ValueError, TTLibError, OSError) as err:
        print(json.dumps({"error": str(err)}))
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
