import sys
from pathlib import Path

import pytest
from conftest import make_font

from halfbold.cli import main

HOSTILE_FAMILY = "Ev\x1b]0;pwn\x07\r\n\x9b\x7f Name"
HOSTILE_FAMILY_ESCAPED = "Ev\\x1b]0;pwn\\x07\\x0d\\x0a\\x9b\\x7f Name"
HOSTILE_STEM_ESCAPED = "Ev\\x1b]0;pwn\\x07\\x0d\\x0a\\x9b\\x7fName"
DETAIL = "  plain Regular 400, bold Bold 700 (sans)"


def write_family(fonts: Path, family: str) -> Path:
    make_font(fonts / "Family-Regular.ttf", family, "Regular", 100)
    make_font(fonts / "Family-Bold.ttf", family, "Bold", 200)
    return fonts


def test_sync_skips_current_fonts_and_rebuild_regenerates_them(
    font_pair: tuple[Path, Path], capsys
):
    fonts = font_pair[0].parent
    args = ["--fonts-dir", str(fonts)]

    assert main(["sync", *args]) == 0
    assert "built" in capsys.readouterr().out
    output = fonts / "Test-Half.ttf"
    assert output.exists()
    modified = output.stat().st_mtime_ns

    assert main(["sync", *args]) == 0
    assert "up to date" in capsys.readouterr().out
    assert output.stat().st_mtime_ns == modified

    assert main(["rebuild", *args]) == 0
    assert "built" in capsys.readouterr().out
    assert output.stat().st_mtime_ns > modified


@pytest.mark.parametrize("command", [["list"], ["rebuild", "--dry-run"]])
def test_plan_does_not_write_fonts(command, font_pair: tuple[Path, Path], capsys):
    fonts = font_pair[0].parent

    assert main([*command, "--fonts-dir", str(fonts)]) == 0

    assert "would build Test-Half.ttf" in capsys.readouterr().out
    assert not (fonts / "Test-Half.ttf").exists()


def test_command_from_process_arguments(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(sys, "argv", ["halfbold", "list", "--fonts-dir", str(tmp_path)])

    assert main() == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("command", ["sync", "rebuild", "list", "--all"])
def test_bulk_commands_reject_font_paths(command, capsys):
    with pytest.raises(SystemExit) as error:
        main([command, "Regular.ttf"])

    assert error.value.code == 2
    assert "use --fonts-dir" in capsys.readouterr().err


def test_list_reports_the_resolved_faces(multi_weight_family: Path, capsys):
    assert (
        main(
            [
                "list",
                "--fonts-dir",
                str(multi_weight_family),
                "--regular-weight",
                "300",
                "--bold-weight",
                "700",
            ]
        )
        == 0
    )
    assert "plain Light 300, bold Bold 700" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("command", "prefix"), [("list", "would build "), ("sync", "built       ")]
)
def test_family_control_characters_print_escaped(
    command: str, prefix: str, tmp_path: Path, capsys
):
    write_family(tmp_path, HOSTILE_FAMILY)

    assert main([command, "--fonts-dir", str(tmp_path)]) == 0

    assert capsys.readouterr().out.splitlines() == [
        f"{prefix}{HOSTILE_STEM_ESCAPED}-Half.ttf  <- {HOSTILE_FAMILY_ESCAPED}{DETAIL}"
    ]


@pytest.mark.parametrize(
    ("family", "stem"), [("Test", "Test"), ("Café 黒体 😀", "Café黒体😀")]
)
def test_printable_family_names_print_unchanged(
    family: str, stem: str, tmp_path: Path, capsys
):
    write_family(tmp_path, family)

    assert main(["list", "--fonts-dir", str(tmp_path)]) == 0

    assert (
        capsys.readouterr().out == f"would build {stem}-Half.ttf  <- {family}{DETAIL}\n"
    )


def test_convert_refuses_to_write_the_bold_face_through_a_symlink(tmp_path: Path):
    (tmp_path / "fonts").mkdir()
    fonts = write_family(tmp_path / "fonts", "Family")
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    (fonts / "Family-HalfBold.ttf").symlink_to(victim)

    with pytest.raises(ValueError, match="symbolic link"):
        main(
            [
                str(fonts / "Family-Regular.ttf"),
                str(fonts / "Family-Bold.ttf"),
                "-o",
                str(fonts / "Family-Half.ttf"),
            ]
        )

    assert victim.read_text() == "keep"
