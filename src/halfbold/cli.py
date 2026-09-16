import argparse
from pathlib import Path

from halfbold.build import (
    BOLD_WEIGHT,
    MAX_WORD_LENGTH,
    REGULAR_WEIGHT,
    STYLE_SUFFIX,
    build_halfbold_font,
)
from halfbold.scan import KINDS, build_all, find_installed_half_families
from halfbold.web import set_web_font

DEFAULT_FONTS_DIR = Path.home() / "Library" / "Fonts"
DEFAULT_CSS = Path(__file__).resolve().parents[2] / "chrome-extension" / "halfbold.css"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="halfbold",
        description=(
            "Merge a Regular and a Bold TTF, or instance a variable TTF at two "
            "weights, into one font whose calt feature bolds the first half of "
            "every word. With --all, scan a fonts folder and build every "
            "missing or outdated Half font."
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
        help=(
            "Folder scanned by --all and checked by --sans/--serif/--mono "
            f"(default: {DEFAULT_FONTS_DIR})"
        ),
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
    for kind in KINDS:
        parser.add_argument(
            f"--{kind}",
            metavar="FAMILY",
            help=f'Make FAMILY the extension\'s {kind} font ("Half" suffix optional)',
        )
    parser.add_argument(
        "--css",
        type=Path,
        default=DEFAULT_CSS,
        help=(
            "Extension stylesheet edited by --sans/--serif/--mono "
            f"(default: {DEFAULT_CSS})"
        ),
    )
    parser.add_argument(
        "--regular-weight",
        type=float,
        default=REGULAR_WEIGHT,
        help="wght value for the plain letters when instancing a variable font",
    )
    parser.add_argument(
        "--bold-weight",
        type=float,
        default=BOLD_WEIGHT,
        help="wght value for the bold letters when instancing a variable font",
    )
    parser.add_argument(
        "--max-word-length",
        type=int,
        default=MAX_WORD_LENGTH,
        help="Longest word that gets its own rule; longer words use this one",
    )
    args = parser.parse_args(argv)
    args.web = {kind: getattr(args, kind) for kind in KINDS if getattr(args, kind)}
    if args.web and (args.all or args.regular is not None):
        parser.error(
            "--sans/--serif/--mono cannot be combined with a font file or --all"
        )
    if not args.web and not args.all and args.regular is None:
        parser.error(
            "give a font file, --all to scan the fonts folder, or --sans/--serif/--mono"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.web:
        installed = find_installed_half_families(args.fonts_dir)
        for kind, family in args.web.items():
            if not family.endswith(f" {STYLE_SUFFIX}"):
                family = f"{family} {STYLE_SUFFIX}"
            if family not in installed:
                names = ", ".join(sorted(installed)) or "none"
                print(
                    f"{family!r} is not installed in {args.fonts_dir}; "
                    f"installed Half fonts: {names}"
                )
                return 1
            print(set_web_font(args.css, kind, family))
        return 0
    if args.all:
        for line in build_all(args.fonts_dir, force=args.force, dry_run=args.dry_run):
            print(line)
        return 0
    output = args.output or args.regular.with_name(f"{args.regular.stem}-Half.ttf")
    letters = build_halfbold_font(
        args.regular,
        args.bold,
        output,
        max_word_length=args.max_word_length,
        regular_weight=args.regular_weight,
        bold_weight=args.bold_weight,
    )
    print(f"wrote {output} ({len(letters)} letter glyphs bolded)")
    return 0
