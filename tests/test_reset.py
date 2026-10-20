import json
from pathlib import Path

from test_web import CSS

from halfbold.reset import (
    VSCODE,
    WEB,
    load_originals,
    remember,
    restore_originals,
    vscode_values,
)
from halfbold.web import get_web_fonts, set_web_font


def test_remember_keeps_the_first_values(tmp_path: Path):
    path = tmp_path / "halfbold" / "originals.json"

    remember(path, WEB, {"sans": "First Half"})
    remember(path, WEB, {"sans": "Second Half"})

    assert load_originals(path) == {WEB: {"sans": "First Half"}}


def test_vscode_values_reports_missing_keys_as_none(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"editor.fontFamily": "Menlo"}')

    assert vscode_values(settings) == {
        "editor.fontFamily": "Menlo",
        "editor.fontLigatures": None,
    }


def test_restore_puts_back_vscode_and_slots(tmp_path: Path):
    path = tmp_path / "originals.json"
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{\n    "editor.fontFamily": "Menlo",\n    "editor.tabSize": 2\n}\n'
    )
    remember(path, WEB, get_web_fonts(css))
    remember(path, VSCODE, vscode_values(settings))
    set_web_font(css, "sans", "Pair Half")
    settings.write_text(
        '{\n    "editor.fontFamily": "\'Pair Half\', monospace",\n'
        '    "editor.tabSize": 2,\n    "editor.fontLigatures": true\n}\n'
    )

    restored = restore_originals(path, css, settings)

    assert restored == [VSCODE, WEB]
    assert css.read_text() == CSS
    assert json.loads(settings.read_text()) == {
        "editor.fontFamily": "Menlo",
        "editor.tabSize": 2,
    }
    assert not path.exists()


def test_restore_without_originals_changes_nothing(tmp_path: Path):
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)

    restored = restore_originals(tmp_path / "originals.json", css, tmp_path / "s.json")

    assert restored == []
    assert css.read_text() == CSS
