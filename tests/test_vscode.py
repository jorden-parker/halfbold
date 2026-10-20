import json
from pathlib import Path

import pytest

from halfbold.vscode import get_setting, remove_setting, set_setting, use_in_vscode

WITH_COMMENTS = """{
    // Editor look
    "editor.fontSize": 14,
    /* "editor.fontFamily": "Commented Out" */
    "[python]": {
        "editor.fontFamily": "Language Font"
    },
    "editor.fontFamily": "Menlo, monospace",
}
"""


def test_set_setting_replaces_only_the_top_level_value():
    text = set_setting(WITH_COMMENTS, "editor.fontFamily", "'Pair Half', monospace")

    assert "// Editor look" in text
    assert '/* "editor.fontFamily": "Commented Out" */' in text
    assert '"editor.fontFamily": "Language Font"' in text
    assert '"editor.fontFamily": "\'Pair Half\', monospace",' in text
    assert get_setting(text, "editor.fontFamily") == "'Pair Half', monospace"


def test_set_setting_adds_a_missing_key():
    text = set_setting(WITH_COMMENTS, "editor.fontLigatures", True)

    assert get_setting(text, "editor.fontLigatures") is True
    assert get_setting(text, "editor.fontSize") == 14


def test_set_setting_fills_an_empty_object():
    text = set_setting("{}\n", "editor.fontLigatures", True)

    assert json.loads(text) == {"editor.fontLigatures": True}


def test_set_setting_rejects_a_non_object():
    with pytest.raises(ValueError, match="not a JSON object"):
        set_setting("[]", "editor.fontFamily", "x")


def test_remove_setting_drops_a_middle_key_and_keeps_comments():
    text = remove_setting(WITH_COMMENTS, "editor.fontSize")

    assert "// Editor look" in text
    assert get_setting(text, "editor.fontSize") is None
    assert get_setting(text, "editor.fontFamily") == "Menlo, monospace"


def test_remove_setting_drops_the_last_key_and_its_comma():
    text = '{\n    "a": 1,\n    "b": 2\n}\n'

    assert remove_setting(text, "b") == '{\n    "a": 1\n}\n'


def test_remove_setting_drops_the_first_key():
    text = '{\n    "a": 1,\n    "b": 2\n}\n'

    assert remove_setting(text, "a") == '{\n    "b": 2\n}\n'


def test_remove_setting_empties_a_single_key_object():
    assert json.loads(remove_setting('{"a": [1, {"b": 2}]}', "a")) == {}


def test_remove_setting_ignores_a_missing_key():
    assert remove_setting(WITH_COMMENTS, "editor.tabSize") == WITH_COMMENTS


def test_use_in_vscode_sets_family_and_turns_on_ligatures(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{\n    "editor.fontLigatures": false\n}\n')

    result = use_in_vscode(settings, "Pair Half")

    assert json.loads(settings.read_text()) == {
        "editor.fontFamily": "'Pair Half', monospace",
        "editor.fontLigatures": True,
    }
    assert result == {
        "settings": str(settings),
        "font_family": "'Pair Half', monospace",
    }


def test_use_in_vscode_keeps_a_custom_ligature_string(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"editor.fontLigatures": "\'ss01\'"}')

    use_in_vscode(settings, "Pair Half")

    assert get_setting(settings.read_text(), "editor.fontLigatures") == "'ss01'"


def test_use_in_vscode_creates_settings_in_an_existing_folder(tmp_path: Path):
    settings = tmp_path / "settings.json"

    use_in_vscode(settings, "Pair Half")

    assert json.loads(settings.read_text())["editor.fontLigatures"] is True


def test_use_in_vscode_without_vscode_raises(tmp_path: Path):
    settings = tmp_path / "Code" / "User" / "settings.json"

    with pytest.raises(ValueError, match="Visual Studio Code settings folder"):
        use_in_vscode(settings, "Pair Half")
