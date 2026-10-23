import hashlib
import io
from pathlib import Path

import pytest
from conftest import make_font
from fontTools.ttLib import TTFont

from halfbold import chrome_fonts
from halfbold.build import BOLD_SUFFIX
from halfbold.chrome_fonts import (
    ServedFace,
    WebFace,
    convert_installed_family,
    convert_webfont_family,
    prepare_default_fonts,
    served_key,
)
from halfbold.settings import Settings

SECRET = b"\x01" * 32
OTHER_SECRET = b"\x02" * 32


def unkeyed_served_key(sources: list[bytes], settings: Settings) -> str:
    digest = hashlib.sha256(
        f"{chrome_fonts.SERVED_FONT_VERSION}:{settings.cache_tag()}".encode()
    )
    for source in sources:
        digest.update(hashlib.sha256(source).digest())
    return digest.hexdigest()[:32]


def web_face(path: Path, weight: tuple[float, float], **descriptors) -> WebFace:
    return WebFace(weight=weight, data=path.read_bytes(), **descriptors)


def as_woff2(path: Path) -> bytes:
    font = TTFont(path)
    font.flavor = "woff2"
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def served_font(fonts_dir: Path, face: ServedFace) -> TTFont:
    assert face.file is not None
    return TTFont(fonts_dir / face.file)


def has_calt(font: TTFont) -> bool:
    records = font["GSUB"].table.FeatureList.FeatureRecord
    return any(record.FeatureTag == "calt" for record in records)


def test_static_pair_serves_a_half_font_in_place_of_the_plain_face(
    font_pair, tmp_path: Path
):
    regular, bold = font_pair
    fonts_dir = tmp_path / "served"
    faces = [web_face(regular, (400, 400)), web_face(bold, (700, 700))]

    conversion = convert_webfont_family(faces, fonts_dir, Settings(), SECRET)

    assert conversion.unchanged == []
    [face] = conversion.faces
    assert (face.weight, face.style, face.unicode_range) == ("400", "normal", "")
    font = served_font(fonts_dir, face)
    assert "a" + BOLD_SUFFIX in font.getGlyphOrder()
    assert has_calt(font)


def test_variable_webfont_serves_its_plain_weight(variable_font, tmp_path: Path):
    fonts_dir = tmp_path / "served"
    faces = [web_face(variable_font, (400, 700))]

    conversion = convert_webfont_family(faces, fonts_dir, Settings(), SECRET)

    [face] = conversion.faces
    assert face.weight == "400"
    assert "fvar" not in served_font(fonts_dir, face)


def test_woff2_source_becomes_a_plain_truetype_half_font(font_pair, tmp_path: Path):
    regular, bold = font_pair
    fonts_dir = tmp_path / "served"
    faces = [
        WebFace(weight=(400, 400), data=as_woff2(regular)),
        WebFace(weight=(700, 700), data=as_woff2(bold)),
    ]

    [face] = convert_webfont_family(faces, fonts_dir, Settings(), SECRET).faces

    font = served_font(fonts_dir, face)
    assert font.flavor is None
    assert has_calt(font)


def test_each_style_and_subset_pairs_on_its_own(font_pair, tmp_path: Path):
    regular, bold = font_pair
    fonts_dir = tmp_path / "served"
    faces = [
        web_face(regular, (400, 400), unicode_range="U+0000-00FF"),
        web_face(bold, (700, 700), unicode_range="U+0000-00FF"),
        web_face(regular, (400, 400), unicode_range="U+0100-024F"),
        web_face(bold, (700, 700), unicode_range="U+0100-024F"),
        web_face(regular, (400, 400), style="italic"),
    ]

    conversion = convert_webfont_family(faces, fonts_dir, Settings(), SECRET)

    served = {(face.style, face.unicode_range) for face in conversion.faces}
    assert served == {("normal", "U+0000-00FF"), ("normal", "U+0100-024F")}
    assert conversion.unchanged == ["italic: needs a second weight"]


def test_a_repeat_conversion_reuses_the_served_file(
    font_pair, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    regular, bold = font_pair
    fonts_dir = tmp_path / "served"
    faces = [web_face(regular, (400, 400)), web_face(bold, (700, 700))]
    [first] = convert_webfont_family(faces, fonts_dir, Settings(), SECRET).faces

    def fail(*args, **kwargs):
        raise AssertionError("rebuilt a cached font")

    monkeypatch.setattr(chrome_fonts, "build_halfbold_font", fail)
    [again] = convert_webfont_family(faces, fonts_dir, Settings(), SECRET).faces

    assert again == first


def test_changed_settings_serve_a_new_file(font_pair, tmp_path: Path):
    regular, bold = font_pair
    fonts_dir = tmp_path / "served"
    faces = [web_face(regular, (400, 400)), web_face(bold, (700, 700))]

    [default] = convert_webfont_family(faces, fonts_dir, Settings(), SECRET).faces
    [changed] = convert_webfont_family(
        faces, fonts_dir, Settings(bold_share=0.3), SECRET
    ).faces

    assert default.file != changed.file


def test_the_same_bytes_serve_the_same_name_within_one_install(
    font_pair, tmp_path: Path
):
    regular, bold = font_pair
    faces = [web_face(regular, (400, 400)), web_face(bold, (700, 700))]
    fonts_dir = tmp_path / "served"

    [first] = convert_webfont_family(faces, fonts_dir, Settings(), SECRET).faces
    [again] = convert_webfont_family(faces, fonts_dir, Settings(), SECRET).faces

    assert again.file == first.file


def test_another_install_serves_a_different_name_for_the_same_bytes(
    font_pair, tmp_path: Path
):
    regular, bold = font_pair
    faces = [web_face(regular, (400, 400)), web_face(bold, (700, 700))]

    [mine] = convert_webfont_family(faces, tmp_path / "mine", Settings(), SECRET).faces
    [theirs] = convert_webfont_family(
        faces, tmp_path / "theirs", Settings(), OTHER_SECRET
    ).faces

    assert mine.file != theirs.file


def test_served_name_is_not_the_unkeyed_digest_of_the_font_bytes(
    font_pair, tmp_path: Path
):
    regular, bold = font_pair
    faces = [web_face(regular, (400, 400)), web_face(bold, (700, 700))]

    [face] = convert_webfont_family(
        faces, tmp_path / "served", Settings(), SECRET
    ).faces

    sources = [regular.read_bytes(), bold.read_bytes()]
    assert face.file != f"{unkeyed_served_key(sources, Settings())}.ttf"


def test_served_key_depends_on_the_secret_and_the_sources():
    sources = [b"regular", b"bold"]

    assert served_key(sources, Settings(), SECRET) == served_key(
        sources, Settings(), SECRET
    )
    assert served_key(sources, Settings(), SECRET) != served_key(
        sources, Settings(), OTHER_SECRET
    )
    assert served_key(sources, Settings(), SECRET) != served_key(
        [b"regular"], Settings(), SECRET
    )


def make_icon_font(path: Path) -> Path:
    make_font(path, "Icons", "Regular", 100)
    font = TTFont(path)
    for table in font["cmap"].tables:
        table.cmap = {
            0xE000 + index if index > 2 else codepoint: name
            for index, (codepoint, name) in enumerate(sorted(table.cmap.items()))
        }
    font.save(path)
    return path


def test_icon_fonts_stay_unchanged(tmp_path: Path):
    fonts_dir = tmp_path / "served"
    icons = make_icon_font(tmp_path / "Icons.ttf")
    faces = [web_face(icons, (400, 400)), web_face(icons, (700, 700))]

    conversion = convert_webfont_family(faces, fonts_dir, Settings(), SECRET)

    assert conversion.faces == []
    assert conversion.unchanged == ["normal: icon font"]


def test_installed_family_serves_half_and_bold_and_keeps_other_faces(
    multi_weight_family: Path, tmp_path: Path
):
    fonts_dir = tmp_path / "served"
    paths = sorted(multi_weight_family.glob("*.ttf"))

    conversion = convert_installed_family("multi", paths, fonts_dir, Settings(), SECRET)

    by_weight = {(face.weight, face.style): face for face in conversion.faces}
    assert set(by_weight) == {
        ("400", "normal"),
        ("700", "normal"),
        ("300", "normal"),
        ("500", "normal"),
        ("400", "italic"),
    }
    assert has_calt(served_font(fonts_dir, by_weight["400", "normal"]))
    assert (
        "a" + BOLD_SUFFIX
        not in served_font(fonts_dir, by_weight["700", "normal"]).getGlyphOrder()
    )
    assert by_weight["300", "normal"].local == ("Multi Light", "Multi-Light")
    assert by_weight["400", "italic"].local == ("Multi Italic", "Multi-Italic")


def test_unknown_installed_family_stays_unchanged(
    multi_weight_family: Path, tmp_path: Path
):
    paths = sorted(multi_weight_family.glob("*.ttf"))

    conversion = convert_installed_family("Nope", paths, tmp_path, Settings(), SECRET)

    assert conversion.faces == []
    assert conversion.unchanged == ["Nope: not installed"]


def test_installed_family_with_one_weight_stays_unchanged(
    multi_weight_family: Path, tmp_path: Path
):
    paths = sorted(multi_weight_family.glob("*.ttf"))

    conversion = convert_installed_family("Solo", paths, tmp_path, Settings(), SECRET)

    assert conversion.unchanged == ["Solo: needs a second weight"]


def test_default_fonts_install_half_families_for_chrome(
    multi_weight_family: Path, tmp_path: Path
):
    paths = sorted(multi_weight_family.glob("*.ttf"))
    fonts_dir = tmp_path / "Fonts"

    installed = prepare_default_fonts(
        {"sansserif": "Multi", "fixed": "Solo"}, paths, fonts_dir, Settings()
    )

    assert installed == {"sansserif": "Multi Half"}
    assert (fonts_dir / "Multi-Half.ttf").exists()
    assert (fonts_dir / "Multi-HalfBold.ttf").exists()
