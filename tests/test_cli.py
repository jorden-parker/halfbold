import sys
from pathlib import Path

import pytest

from halfbold.cli import main


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
