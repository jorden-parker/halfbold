import json
from pathlib import Path

from halfbold.reset import (
    VSCODE,
    load_originals,
    remember,
    restore_originals,
    vscode_values,
)


def test_remember_keeps_the_first_values(tmp_path: Path):
    path = tmp_path / "halfbold" / "originals.json"

    remember(path, VSCODE, {"editor.fontFamily": "Menlo"})
    remember(path, VSCODE, {"editor.fontFamily": "Pair Half"})

    assert load_originals(path) == {VSCODE: {"editor.fontFamily": "Menlo"}}


def test_vscode_values_reports_missing_keys_as_none(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"editor.fontFamily": "Menlo"}')

    assert vscode_values(settings) == {
        "editor.fontFamily": "Menlo",
        "editor.fontLigatures": None,
    }


def test_restore_puts_back_vscode(tmp_path: Path):
    path = tmp_path / "originals.json"
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{\n    "editor.fontFamily": "Menlo",\n    "editor.tabSize": 2\n}\n'
    )
    remember(path, VSCODE, vscode_values(settings))
    settings.write_text(
        '{\n    "editor.fontFamily": "\'Pair Half\', monospace",\n'
        '    "editor.tabSize": 2,\n    "editor.fontLigatures": true\n}\n'
    )

    restored = restore_originals(path, settings)

    assert restored == [VSCODE]
    assert json.loads(settings.read_text()) == {
        "editor.fontFamily": "Menlo",
        "editor.tabSize": 2,
    }
    assert not path.exists()


def test_restore_ignores_slots_recorded_by_older_versions(tmp_path: Path):
    path = tmp_path / "originals.json"
    path.write_text(json.dumps({"web": {"sans": "Inter Half"}}))

    restored = restore_originals(path, tmp_path / "s.json")

    assert restored == ["web"]
    assert not path.exists()


def test_restore_without_originals_changes_nothing(tmp_path: Path):
    restored = restore_originals(tmp_path / "originals.json", tmp_path / "s.json")

    assert restored == []
