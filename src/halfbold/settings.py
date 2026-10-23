import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

RULES_VERSION = 4
BOLD_SHARE = 0.5
BOLD_ENDS = 1
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


TUNING_NAMES = (
    "bold_share",
    "bold_ends",
    "min_word_length",
    "max_word_length",
    "regular_weight",
    "bold_weight",
)


@dataclass(frozen=True)
class Settings:
    bold_share: float = BOLD_SHARE
    bold_ends: int = BOLD_ENDS
    min_word_length: int = MIN_WORD_LENGTH
    max_word_length: int = MAX_WORD_LENGTH
    regular_weight: float = REGULAR_WEIGHT
    bold_weight: float = BOLD_WEIGHT
    fonts: dict[str, dict[str, float]] = field(default_factory=dict)

    def validated(self) -> Settings:
        if not 0 < self.bold_share <= 1:
            raise ValueError("bold_share must be between 0 and 1")
        if self.bold_ends not in (1, 2):
            raise ValueError("bold_ends must be 1 (start) or 2 (start and end)")
        if self.min_word_length < 1:
            raise ValueError("min_word_length must be at least 1")
        if self.max_word_length < self.min_word_length:
            raise ValueError("max_word_length must be at least min_word_length")
        for name in ("regular_weight", "bold_weight"):
            if not 1 <= getattr(self, name) <= 1000:
                raise ValueError(f"{name} must be between 1 and 1000")
        return self

    def merged(self, values: dict) -> Settings:
        known = {name: type(getattr(self, name)) for name in TUNING_NAMES}
        unknown = sorted(set(values) - set(known))
        if unknown:
            raise ValueError(f"unknown setting: {', '.join(unknown)}")
        coerced = {
            name: (int(value) if known[name] is int else float(value))
            for name, value in values.items()
        }
        return replace(self, **coerced).validated()

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in TUNING_NAMES}

    def for_family(self, family: str) -> Settings:
        return replace(self.merged(self.fonts.get(family, {})), fonts={})

    def with_font(self, family: str, values: dict) -> Settings:
        chosen = {**self.fonts.get(family, {}), **values}
        validated = self.merged(chosen)
        coerced = {name: getattr(validated, name) for name in chosen}
        return replace(self, fonts={**self.fonts, family: coerced})

    def without_font(self, family: str) -> Settings:
        remaining = {name: v for name, v in self.fonts.items() if name != family}
        return replace(self, fonts=remaining)

    def fonts_tag(self) -> str:
        if not self.fonts:
            return ""
        digest = hashlib.sha256(json.dumps(self.fonts, sort_keys=True).encode())
        return f"-f{digest.hexdigest()[:8]}"

    def rules_tag(self) -> str:
        return (
            f"v{RULES_VERSION}-s{round(self.bold_share * 100)}"
            f"-m{self.min_word_length}-x{self.max_word_length}"
            f"-e{self.bold_ends}"
        )

    def cache_tag(self) -> str:
        return (
            f"{self.rules_tag()}"
            f"-w{round(self.regular_weight)}-b{round(self.bold_weight)}"
            f"{self.fonts_tag()}"
        )


def load_settings(path: Path | None = None) -> Settings:
    path = path or default_settings_path()
    if not path.exists():
        return Settings()
    try:
        fonts = json.loads(path.read_text()).get("fonts", {})
        settings = Settings()
        for family, values in fonts.items():
            settings = settings.with_font(family, values)
        return settings
    except ValueError, AttributeError, TypeError:
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    path = path or default_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fonts": settings.fonts}, indent=2) + "\n")
    return path
