import json
from pathlib import Path

from halfbold.settings import default_settings_path
from halfbold.vscode import (
    FONT_FAMILY,
    FONT_LIGATURES,
    get_setting,
    remove_setting,
    set_setting,
)
from halfbold.web import set_web_font

VSCODE = "vscode"
WEB = "web"


def default_originals_path() -> Path:
    return default_settings_path().with_name("originals.json")


def load_originals(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def remember(path: Path, section: str, values: dict) -> None:
    originals = load_originals(path)
    if section in originals:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**originals, section: values}, indent=2) + "\n")


def vscode_values(settings_path: Path) -> dict:
    text = settings_path.read_text() if settings_path.exists() else "{}"
    return {key: get_setting(text, key) for key in (FONT_FAMILY, FONT_LIGATURES)}


def restore_vscode(settings_path: Path, values: dict) -> None:
    if not settings_path.exists():
        return
    text = settings_path.read_text()
    for key, value in values.items():
        if value is None:
            text = remove_setting(text, key)
        else:
            text = set_setting(text, key, value)
    settings_path.write_text(text)


def restore_web(css_path: Path, values: dict) -> None:
    for kind, family in values.items():
        set_web_font(css_path, kind, family)


def restore_originals(path: Path, css_path: Path, settings_path: Path) -> list[str]:
    originals = load_originals(path)
    if VSCODE in originals:
        restore_vscode(settings_path, originals[VSCODE])
    if WEB in originals:
        restore_web(css_path, originals[WEB])
    path.unlink(missing_ok=True)
    return sorted(originals)
