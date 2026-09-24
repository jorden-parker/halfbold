import json
from pathlib import Path

import pytest

from halfbold.settings import Settings, load_settings, save_settings


def test_defaults_round_trip(tmp_path: Path):
    path = tmp_path / "settings.json"
    assert load_settings(path) == Settings()
    saved = save_settings(Settings(bold_share=0.3, bold_weight=800), path)
    assert saved == path
    assert load_settings(path) == Settings(bold_share=0.3, bold_weight=800)


def test_merged_coerces_and_validates():
    merged = Settings().merged({"min_word_length": "3", "bold_share": "0.75"})
    assert merged.min_word_length == 3
    assert merged.bold_share == 0.75
    with pytest.raises(ValueError, match="unknown setting"):
        Settings().merged({"nope": 1})
    with pytest.raises(ValueError, match="bold_share"):
        Settings().merged({"bold_share": 0})
    with pytest.raises(ValueError, match="max_word_length"):
        Settings().merged({"min_word_length": 30})


def test_corrupt_file_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert load_settings(path) == Settings()
    path.write_text(json.dumps({"bold_share": 5}))
    assert load_settings(path) == Settings()


def test_cache_tag_changes_with_values():
    assert Settings().cache_tag() != Settings(bold_share=0.6).cache_tag()


def test_cache_tag_carries_rules_version():
    assert Settings().cache_tag().startswith("v3-")
