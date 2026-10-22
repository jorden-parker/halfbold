import argparse
import sys
import tempfile
from pathlib import Path

from halfbold.brewcask import cask_font_dir
from halfbold.build import (
    bold_face_path,
    build_bold_face,
    build_halfbold_font,
)
from halfbold.desktop import launch_desktop
from halfbold.preview import preview_candidates, preview_files
from halfbold.scan import build_all
from halfbold.settings import load_settings

DEFAULT_FONTS_DIR = Path.home() / "Library" / "Fonts"
COMMANDS = {
    "sync": ("--all",),
    "rebuild": ("--all", "--force"),
    "list": ("--all", "--dry-run"),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "desktop":
        parser = argparse.ArgumentParser(
            prog="halfbold desktop",
            description=(
                "Install app dependencies and launch the desktop app from source."
            ),
        )
        args = parser.parse_args(argv[1:])
        args.desktop = True
        return args
    command = argv.pop(0) if argv and argv[0] in COMMANDS else None
    parser = argparse.ArgumentParser(
        prog=f"halfbold {command}" if command else "halfbold",
        description=(
            "Merge two weights of a font family, or instance a variable TTF at "
            "two weights, into one font whose calt feature bolds the first half "
            "of every word. Use sync to build missing or stale Half fonts, "
            "rebuild to regenerate all of them, list to show the build plan, "
            "or desktop to launch the desktop app."
        ),
        epilog=(
            "Examples: halfbold rebuild | halfbold sync | halfbold list | "
            "halfbold rebuild --fonts-dir /path/to/fonts | "
            "halfbold rebuild --dry-run. Legacy --all flags still work."
        ),
    )
    parser.add_argument(
        "regular", type=Path, nargs="?", help="Regular weight or variable .ttf"
    )
    parser.add_argument(
        "bold",
        type=Path,
        nargs="?",
        help="Bold weight .ttf of the same family; omit for a variable font",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .ttf (default: <regular stem>-Half.ttf next to the input)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan --fonts-dir and build a Half font for every eligible family",
    )
    parser.add_argument(
        "--fonts-dir",
        type=Path,
        default=DEFAULT_FONTS_DIR,
        help=(f"Folder scanned by --all (default: {DEFAULT_FONTS_DIR})"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --all, rebuild even when the Half font is newer than its source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --all, list what would be built without writing anything",
    )
    settings = load_settings()
    parser.add_argument(
        "--bold-share",
        type=float,
        default=settings.bold_share,
        help="Share of each word to bold, 0 to 1 (default from settings)",
    )
    parser.add_argument(
        "--bold-ends",
        type=int,
        choices=(1, 2),
        default=settings.bold_ends,
        help="Bold the start of each word (1) or its start and end (2)",
    )
    parser.add_argument(
        "--min-word-length",
        type=int,
        default=settings.min_word_length,
        help="Words shorter than this stay plain (default from settings)",
    )
    parser.add_argument(
        "--regular-weight",
        type=float,
        default=settings.regular_weight,
        help=(
            "Target weight for the plain letters: the wght instance of a "
            "variable font, or the nearest installed face of a static family. "
            "Ignored when you name two font files yourself."
        ),
    )
    parser.add_argument(
        "--bold-weight",
        type=float,
        default=settings.bold_weight,
        help=(
            "Target weight for the bold letters: the wght instance of a "
            "variable font, or the nearest installed face of a static family. "
            "Ignored when you name two font files yourself."
        ),
    )
    parser.add_argument(
        "--max-word-length",
        type=int,
        default=settings.max_word_length,
        help="Longest word that gets its own rule; longer words use this one",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help=(
            "Draw a half-bold sample of REGULAR [BOLD] (or every font in a "
            "folder) in the terminal"
        ),
    )
    parser.add_argument(
        "--png", type=Path, help="With --preview, write the sample image here instead"
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="With --preview, keep the image until enter is pressed (used by the TUI)",
    )
    parser.add_argument(
        "--preview-cask",
        metavar="TOKEN",
        help="Download a Homebrew font cask without installing it and preview it",
    )
    args = parser.parse_args([*COMMANDS.get(command, ()), *argv])
    if args.all and (args.regular is not None or args.output is not None):
        parser.error(
            "sync, rebuild, list and --all use --fonts-dir, not font files or -o"
        )
    if args.preview and (args.all or args.regular is None):
        parser.error("--preview takes a font file or folder and no other mode")
    if args.preview_cask and (args.all or args.preview or args.regular is not None):
        parser.error("--preview-cask takes a cask token and no other mode")
    if (args.png or args.wait) and not args.preview and not args.preview_cask:
        parser.error("--png and --wait need --preview")
    if (
        not args.all
        and not args.preview
        and not args.preview_cask
        and args.regular is None
    ):
        parser.error("use sync, rebuild or list, or give a font file")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if getattr(args, "desktop", False):
        return launch_desktop()
    if args.preview:
        try:
            if args.regular.is_dir():
                lines = preview_candidates(args.regular, png=args.png, wait=args.wait)
            else:
                lines = preview_files(
                    args.regular, args.bold, png=args.png, wait=args.wait
                )
        except ValueError as err:
            print(err)
            return 1
        for line in lines:
            print(line)
        return 0
    if args.preview_cask:
        with tempfile.TemporaryDirectory(prefix="halfbold-cask-") as tmp:
            try:
                print(f"fetching {args.preview_cask} …", flush=True)
                fonts_dir = cask_font_dir(args.preview_cask, Path(tmp))
                lines = preview_candidates(fonts_dir, png=args.png, wait=args.wait)
            except ValueError as err:
                print(f"{args.preview_cask}: {err}")
                return 1
        for line in lines:
            print(line)
        return 0
    settings = load_settings().merged(
        {
            "bold_share": args.bold_share,
            "bold_ends": args.bold_ends,
            "min_word_length": args.min_word_length,
            "max_word_length": args.max_word_length,
            "regular_weight": args.regular_weight,
            "bold_weight": args.bold_weight,
        }
    )
    if args.all:
        for line in build_all(
            args.fonts_dir, force=args.force, dry_run=args.dry_run, settings=settings
        ):
            print(line)
        return 0
    output = args.output or args.regular.with_name(f"{args.regular.stem}-Half.ttf")
    letters = build_halfbold_font(args.regular, args.bold, output, settings)
    build_bold_face(args.regular, args.bold, bold_face_path(output), settings)
    print(f"wrote {output} ({len(letters)} letter glyphs bolded)")
    return 0
