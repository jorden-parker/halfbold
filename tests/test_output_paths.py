from pathlib import Path

import pytest

from halfbold.output_paths import contained_file, file_stem


@pytest.mark.parametrize(
    ("family", "stem"),
    [
        ("My Font", "MyFont"),
        ("Name/../../evil", "Name_.._.._evil"),
        ("/etc/passwd", "_etc_passwd"),
        ("C:\\Windows\\win.ini", "C:_Windows_win.ini"),
        ("a\x00b", "a_b"),
    ],
)
def test_file_stem_is_one_safe_component(family: str, stem: str):
    assert file_stem(family) == stem


def test_contained_file_places_a_plain_name_in_the_folder(tmp_path: Path):
    assert contained_file(tmp_path, "Pair-Half.ttf") == tmp_path / "Pair-Half.ttf"


@pytest.mark.parametrize("name", ["", ".", "..", "../escape.ttf", "/abs.ttf", "a/b"])
def test_contained_file_refuses_a_name_that_is_not_one_component(
    tmp_path: Path, name: str
):
    with pytest.raises(ValueError):
        contained_file(tmp_path, name)


def test_contained_file_refuses_a_symlink_at_the_target(tmp_path: Path):
    outside = tmp_path / "outside.ttf"
    outside.write_bytes(b"keep")
    folder = tmp_path / "fonts"
    folder.mkdir()
    (folder / "Pair-Half.ttf").symlink_to(outside)

    with pytest.raises(ValueError):
        contained_file(folder, "Pair-Half.ttf")
