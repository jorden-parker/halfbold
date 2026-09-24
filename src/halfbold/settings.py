import json
import sys
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

RULES_VERSION = 2
BOLD_SHARE = 0.5
MIN_WORD_LENGTH = 2
MAX_WORD_LENGTH = 20
REGULAR_WEIGHT = 400
BOLD_WEIGHT = 700


def default_settings_path() -> Path:
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "halfbold"
            / "settings.json"
        )
    return Path(tempfile.gettempdir()) / "halfbold" / "settings.json"


@dataclass(frozen=True)
class Settings:
    bold_share: float = BOLD_SHARE
    min_word_length: int = MIN_WORD_LENGTH
    max_word_length: int = MAX_WORD_LENGTH
    regular_weight: float = REGULAR_WEIGHT
    bold_weight: float = BOLD_WEIGHT

    def validated(self) -> Settings:
        if not 0 < self.bold_share <= 1:
            raise ValueError("bold_share must be between 0 and 1")
        if self.min_word_length < 1:
            raise ValueError("min_word_length must be at least 1")
        if self.max_word_length < self.min_word_length:
            raise ValueError("max_word_length must be at least min_word_length")
        for name in ("regular_weight", "bold_weight"):
            if not 1 <= getattr(self, name) <= 1000:
                raise ValueError(f"{name} must be between 1 and 1000")
        return self

    def merged(self, values: dict) -> Settings:
        known = {f.name: type(getattr(self, f.name)) for f in fields(self)}
        unknown = sorted(set(values) - set(known))
        if unknown:
            raise ValueError(f"unknown setting: {', '.join(unknown)}")
        coerced = {
            name: (int(value) if known[name] is int else float(value))
            for name, value in values.items()
        }
        return replace(self, **coerced).validated()

    def as_dict(self) -> dict:
        return asdict(self)

    def cache_tag(self) -> str:
        return (
            f"v{RULES_VERSION}-s{round(self.bold_share * 100)}"
            f"-m{self.min_word_length}-x{self.max_word_length}"
            f"-w{round(self.regular_weight)}-b{round(self.bold_weight)}"
        )


def load_settings(path: Path | None = None) -> Settings:
    path = path or default_settings_path()
    if not path.exists():
        return Settings()
    try:
        return Settings().merged(json.loads(path.read_text()))
    except ValueError, json.JSONDecodeError:
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    path = path or default_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.as_dict(), indent=2) + "\n")
    return path
