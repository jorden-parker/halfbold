import base64
import math
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageDraw, ImageFont

from halfbold.build import bold_prefix_length
from halfbold.scan import Candidate, candidates_from_paths, read_font_info
from halfbold.settings import BOLD_WEIGHT, REGULAR_WEIGHT

SAMPLE_TEXT = (
    "The quick brown fox jumps over the lazy dog. Reading gets faster when "
    "the first half of every word is bold, because your eyes only need the "
    "start of a word to recognise it."
)
FONT_SIZE = 40
CANVAS_WIDTH = 1400
MARGIN = 40
LINE_HEIGHT = 56

_CHUNK_SIZE = 4096


def load_faces(
    regular: Path, bold: Path | None
) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    if bold is not None:
        return (
            ImageFont.truetype(str(regular), FONT_SIZE),
            ImageFont.truetype(str(bold), FONT_SIZE),
        )
    regular_face = ImageFont.truetype(str(regular), FONT_SIZE)
    bold_face = ImageFont.truetype(str(regular), FONT_SIZE)
    try:
        axes = regular_face.get_variation_axes()
    except OSError as err:
        raise ValueError(
            f"{regular} is not a variable font; pass a Bold file as well"
        ) from err
    weight_names = {axis["name"] for axis in axes}
    if b"Weight" not in weight_names:
        raise ValueError("variable font has no weight axis")
    regular_axes = [
        REGULAR_WEIGHT if axis["name"] == b"Weight" else axis["default"]
        for axis in axes
    ]
    bold_axes = [
        BOLD_WEIGHT if axis["name"] == b"Weight" else axis["default"] for axis in axes
    ]
    regular_face.set_variation_by_axes(regular_axes)
    bold_face.set_variation_by_axes(bold_axes)
    return regular_face, bold_face


def wrap_words(words: list[str], face, max_width: int) -> list[list[str]]:
    lines: list[list[str]] = []
    current: list[str] = []
    for word in words:
        candidate = [*current, word]
        if current and face.getlength(" ".join(candidate)) > max_width:
            lines.append(current)
            current = [word]
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_preview(family: str, regular: Path, bold: Path | None) -> Image.Image:
    regular_face, bold_face = load_faces(regular, bold)
    max_width = CANVAS_WIDTH - 2 * MARGIN
    words = SAMPLE_TEXT.split()
    lines = wrap_words(words, bold_face, max_width)
    height = MARGIN * 2 + LINE_HEIGHT * (3 + 2 * len(lines))
    image = Image.new("RGB", (CANVAS_WIDTH, height), "white")
    draw = ImageDraw.Draw(image)
    y = MARGIN
    draw.text(
        (MARGIN, y), f"{family} — half bold preview", font=regular_face, fill="black"
    )
    y += LINE_HEIGHT * 2
    for line in lines:
        x = MARGIN
        for word in line:
            n = bold_prefix_length(len(word))
            head, tail = word[:n], word[n:]
            draw.text((x, y), head, font=bold_face, fill="black")
            x += bold_face.getlength(head)
            draw.text((x, y), tail, font=regular_face, fill="black")
            x += regular_face.getlength(tail) + regular_face.getlength(" ")
        y += LINE_HEIGHT
    y += LINE_HEIGHT
    for line in lines:
        text = " ".join(line)
        draw.text((MARGIN, y), text, font=regular_face, fill="black")
        y += LINE_HEIGHT
    return image


def kitty_chunks(png: bytes, columns: int, tmux: bool) -> list[bytes]:
    encoded = base64.b64encode(png)
    pieces = [
        encoded[i : i + _CHUNK_SIZE] for i in range(0, len(encoded), _CHUNK_SIZE)
    ] or [b""]
    commands: list[bytes] = []
    for index, piece in enumerate(pieces):
        is_last = index == len(pieces) - 1
        if index == 0:
            control = f"f=100,a=T,q=2,c={columns},m={0 if is_last else 1}".encode()
        else:
            control = f"m={0 if is_last else 1}".encode()
        command = b"\x1b_G" + control + b";" + piece + b"\x1b\\"
        if tmux:
            command = b"\x1bPtmux;" + command.replace(b"\x1b", b"\x1b\x1b") + b"\x1b\\"
        commands.append(command)
    return commands


def kitty_delete_all(tmux: bool) -> bytes:
    command = b"\x1b_Ga=d,d=A,q=2\x1b\\"
    if tmux:
        command = b"\x1bPtmux;" + command.replace(b"\x1b", b"\x1b\x1b") + b"\x1b\\"
    return command


def supports_kitty_graphics(env: Mapping[str, str]) -> bool:
    return (
        "GHOSTTY_RESOURCES_DIR" in env
        or "KITTY_WINDOW_ID" in env
        or "kitty" in env.get("TERM", "")
    )


def show_image(
    image: Image.Image, out: BinaryIO, env: Mapping[str, str], columns: int
) -> None:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    columns = min(columns, 120)
    for chunk in kitty_chunks(buffer.getvalue(), columns, tmux="TMUX" in env):
        out.write(chunk)
    rows = math.ceil(columns * image.height / image.width / 2)
    out.write(b"\n" * rows)
    out.flush()


def preview_images(
    candidates: list[Candidate], *, png: Path | None, wait: bool
) -> list[str]:
    if not candidates:
        raise ValueError("no Regular + Bold pair or variable TrueType font to preview")
    shown = candidates[:3]
    lines: list[str] = []
    for index, candidate in enumerate(shown, start=1):
        image = render_preview(candidate.family, candidate.regular, candidate.bold)
        if png is not None:
            path = png if index == 1 else png.with_stem(f"{png.stem}-{index}")
            image.save(path)
            lines.append(f"wrote {path}")
        elif supports_kitty_graphics(os.environ):
            show_image(
                image, sys.stdout.buffer, os.environ, shutil.get_terminal_size().columns
            )
        else:
            stem = candidate.family.replace(" ", "")
            path = Path(tempfile.gettempdir()) / f"halfbold-preview-{stem}.png"
            image.save(path)
            lines.append(f"this terminal has no kitty graphics support; wrote {path}")
    remaining = len(candidates) - len(shown)
    if remaining > 0:
        lines.append(f"… and {remaining} more")
    if wait:
        print("enter: back")
        sys.stdout.flush()
        sys.stdin.readline()
        sys.stdout.buffer.write(kitty_delete_all(tmux="TMUX" in os.environ))
        sys.stdout.buffer.flush()
    return lines


def preview_candidates(target_dir: Path, *, png: Path | None, wait: bool) -> list[str]:
    candidates = candidates_from_paths(sorted(target_dir.rglob("*.ttf")))
    if not candidates:
        raise ValueError(
            f"no Regular + Bold pair or variable TrueType font in {target_dir}"
        )
    return preview_images(candidates, png=png, wait=wait)


def preview_files(
    regular: Path, bold: Path | None, *, png: Path | None, wait: bool
) -> list[str]:
    info = read_font_info(regular)
    if info is None:
        raise ValueError(f"{regular} is not a TrueType font")
    family = " ".join(p for p in info.family.split() if p != "Variable")
    candidate = Candidate(family, regular, bold, info.kind)
    return preview_images([candidate], png=png, wait=wait)
