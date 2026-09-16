import argparse
from pathlib import Path

from halfbold.build import MAX_WORD_LENGTH, build_halfbold_font


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="halfbold",
        description=(
            "Merge a Regular and a Bold TTF into one font whose calt feature "
            "bolds the first half of every word."
        ),
    )
    parser.add_argument("regular", type=Path, help="Regular weight .ttf")
    parser.add_argument("bold", type=Path, help="Bold weight .ttf of the same family")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .ttf (default: <regular stem>-Half.ttf next to the input)",
    )
    parser.add_argument(
        "--max-word-length",
        type=int,
        default=MAX_WORD_LENGTH,
        help="Longest word that gets its own rule; longer words use this one",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output or args.regular.with_name(f"{args.regular.stem}-Half.ttf")
    letters = build_halfbold_font(
        args.regular, args.bold, output, max_word_length=args.max_word_length
    )
    print(f"wrote {output} ({len(letters)} letter glyphs bolded)")
    return 0
