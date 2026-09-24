from pathlib import Path
from subprocess import CompletedProcess

import pytest

from halfbold import desktop
from halfbold.cli import main


@pytest.fixture
def desktop_repo(tmp_path: Path, monkeypatch):
    app = tmp_path / "app"
    (app / "src-tauri").mkdir(parents=True)
    (app / "src-tauri" / "tauri.conf.json").write_text("{}")
    monkeypatch.setenv("HALFBOLD_REPO", str(tmp_path))
    monkeypatch.setattr(desktop.shutil, "which", lambda tool, path: f"/bin/{tool}")
    monkeypatch.chdir(tmp_path.parent)
    return tmp_path


def test_desktop_launches_from_another_directory(desktop_repo, monkeypatch):
    calls = []

    def run(args, *, cwd, env):
        calls.append(args)
        assert cwd == desktop_repo / "app"
        assert env["HALFBOLD_REPO"] == str(desktop_repo)
        assert "/opt/homebrew/opt/rustup/bin" in env["PATH"]
        return CompletedProcess(args, 0)

    monkeypatch.setattr(desktop.subprocess, "run", run)

    assert main(["desktop"]) == 0
    assert calls == [["bun", "install"], ["bun", "tauri", "dev"]]


def test_install_failure_does_not_launch(desktop_repo, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return CompletedProcess(args, 1)

    monkeypatch.setattr(desktop.subprocess, "run", run)

    assert main(["desktop"]) == 1
    assert calls == [["bun", "install"]]


def test_missing_tool_is_actionable(desktop_repo, monkeypatch, capsys):
    monkeypatch.setattr(desktop.shutil, "which", lambda tool, path: None)

    assert main(["desktop"]) == 1
    assert "Desktop needs bun" in capsys.readouterr().out


def test_missing_checkout_is_actionable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HALFBOLD_REPO", str(tmp_path))

    assert main(["desktop"]) == 1
    assert "Set HALFBOLD_REPO" in capsys.readouterr().out


def test_desktop_help_does_not_launch(monkeypatch, capsys):
    def unexpected_launch():
        pytest.fail("help should not launch the app")

    monkeypatch.setattr("halfbold.cli.launch_desktop", unexpected_launch)
    with pytest.raises(SystemExit) as error:
        main(["desktop", "--help"])

    assert error.value.code == 0
    assert "launch the desktop app" in capsys.readouterr().out
