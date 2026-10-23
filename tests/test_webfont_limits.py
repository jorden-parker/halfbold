import io
import struct
from pathlib import Path

import brotli
import pytest
from conftest import make_font
from fontTools.ttLib import TTFont

from halfbold.chrome_fonts import (
    MAX_EXPANDED_BYTES,
    WebFace,
    WebfontLimits,
    convert_webfont_family,
    write_webfont_truetype,
)
from halfbold.settings import Settings

SECRET = b"\x01" * 32
WOFF2_HEADER = struct.Struct(">4sLLHHLLHHLLLLL")
BOMB_BYTES = 300 << 20
TEST_MEMORY_BYTES = 160 << 20
TEST_LIMITS = WebfontLimits(seconds=60, cpu_seconds=60, memory_bytes=TEST_MEMORY_BYTES)


def woff2_header(declared_expanded: int, compressed_length: int) -> bytes:
    return WOFF2_HEADER.pack(
        b"wOF2",
        0x00010000,
        WOFF2_HEADER.size + compressed_length,
        0,
        0,
        declared_expanded,
        compressed_length,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def variable_face(data: bytes) -> WebFace:
    return WebFace(weight=(100.0, 900.0), data=data)


def as_woff2_bytes(path: Path) -> bytes:
    font = TTFont(path)
    font.flavor = "woff2"
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def test_declared_expansion_over_the_cap_is_refused_before_decoding(tmp_path: Path):
    header = woff2_header(MAX_EXPANDED_BYTES + 1, 0)

    with pytest.raises(ValueError):
        write_webfont_truetype(header, tmp_path / "plain.ttf")


def test_brotli_bomb_ends_unchanged(tmp_path: Path):
    blob = brotli.compress(bytes(BOMB_BYTES), quality=1)
    bomb = woff2_header(0, len(blob)) + blob

    conversion = convert_webfont_family(
        [variable_face(bomb)], tmp_path / "fonts", Settings(), SECRET, TEST_LIMITS
    )

    assert conversion.faces == []
    assert conversion.unchanged == ["normal: web font conversion exceeded its limits"]


def test_conversion_past_its_time_limit_ends_unchanged(tmp_path: Path):
    font = make_font(tmp_path / "Slow-Regular.ttf", "Slow", "Regular", 100)
    too_slow = WebfontLimits(seconds=0.001, cpu_seconds=60, memory_bytes=1 << 30)

    conversion = convert_webfont_family(
        [variable_face(as_woff2_bytes(font))],
        tmp_path / "fonts",
        Settings(),
        SECRET,
        too_slow,
    )

    assert conversion.faces == []
    assert conversion.unchanged == ["normal: web font conversion exceeded its limits"]


def test_normal_webfont_converts_to_the_same_truetype_bytes(tmp_path: Path):
    font = make_font(tmp_path / "Normal-Regular.ttf", "Normal", "Regular", 100)
    woff2 = as_woff2_bytes(font)
    expected_font = TTFont(io.BytesIO(woff2))
    expected_font.flavor = None
    expected_font.save(tmp_path / "expected.ttf")

    converted = write_webfont_truetype(woff2, tmp_path / "plain.ttf")

    assert converted.read_bytes() == (tmp_path / "expected.ttf").read_bytes()


def test_normal_webfont_pair_still_serves_a_half_face(tmp_path: Path):
    regular = make_font(tmp_path / "Pair-Regular.ttf", "Pair", "Regular", 100)
    bold = make_font(tmp_path / "Pair-Bold.ttf", "Pair", "Bold", 200)
    faces = [
        WebFace(weight=(400.0, 400.0), data=as_woff2_bytes(regular)),
        WebFace(weight=(700.0, 700.0), data=as_woff2_bytes(bold)),
    ]

    conversion = convert_webfont_family(faces, tmp_path / "fonts", Settings(), SECRET)

    assert conversion.unchanged == []
    assert len(conversion.faces) == 1
