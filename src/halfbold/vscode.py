import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FONT_FAMILY = "editor.fontFamily"
FONT_LIGATURES = "editor.fontLigatures"
TOKEN = re.compile(
    r'"(?:[^"\\]|\\.)*"|//[^\n]*|/\*.*?\*/|[{}\[\]:,]|[^\s{}\[\]:,"/]+',
    re.DOTALL,
)


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


def default_settings_path() -> Path:
    if sys.platform == "darwin":
        support = Path.home() / "Library" / "Application Support"
    else:
        support = Path.home() / ".config"
    return support / "Code" / "User" / "settings.json"


def tokens(text: str) -> list[Token]:
    return [
        Token(match.group(), match.start(), match.end())
        for match in TOKEN.finditer(text)
        if not match.group().startswith(("//", "/*"))
    ]


def value_end(items: list[Token], index: int) -> int:
    depth = 0
    for position in range(index, len(items)):
        text = items[position].text
        if text in "{[":
            depth += 1
        elif text in "}]":
            depth -= 1
        if depth == 0:
            return position
    raise ValueError("settings.json has an unclosed value")


def top_level_values(text: str) -> tuple[Token, dict[str, tuple[int, int]]]:
    items = tokens(text)
    if not items or items[0].text != "{":
        raise ValueError("settings.json is not a JSON object")
    values: dict[str, tuple[int, int]] = {}
    index = 1
    while index < len(items) and items[index].text != "}":
        if items[index].text == ",":
            index += 1
            continue
        key = json.loads(items[index].text)
        last = value_end(items, index + 2)
        values[key] = (items[index + 2].start, items[last].end)
        index = last + 1
    return items[0], values


def set_setting(text: str, key: str, value: object) -> str:
    opening, values = top_level_values(text)
    encoded = json.dumps(value)
    if key in values:
        start, end = values[key]
        return text[:start] + encoded + text[end:]
    separator = "," if values else "\n"
    insertion = f'\n    "{key}": {encoded}{separator}'
    return text[: opening.end] + insertion + text[opening.end :]


def remove_setting(text: str, key: str) -> str:
    _, values = top_level_values(text)
    if key not in values:
        return text
    items = tokens(text)
    value_index = next(
        i for i, item in enumerate(items) if item.start == values[key][0]
    )
    key_index = value_index - 2
    last = value_end(items, value_index)
    start = len(text[: items[key_index].start].rstrip())
    following = items[last + 1]
    if following.text == ",":
        return text[:start] + text[following.end :]
    preceding = items[key_index - 1]
    if preceding.text == ",":
        return (
            text[: preceding.start]
            + text[preceding.end : start]
            + text[items[last].end :]
        )
    return text[:start] + text[items[last].end :]


def get_setting(text: str, key: str) -> object:
    _, values = top_level_values(text)
    if key not in values:
        return None
    start, end = values[key]
    return json.loads(text[start:end])


def use_in_vscode(settings_path: Path, family: str) -> dict:
    if not settings_path.parent.is_dir():
        raise ValueError(
            f"Visual Studio Code settings folder not found: {settings_path.parent}"
        )
    text = settings_path.read_text() if settings_path.exists() else "{}\n"
    text = set_setting(text, FONT_FAMILY, f"'{family}', monospace")
    if not get_setting(text, FONT_LIGATURES):
        text = set_setting(text, FONT_LIGATURES, True)
    settings_path.write_text(text)
    return {
        "settings": str(settings_path),
        "font_family": get_setting(text, FONT_FAMILY),
    }
