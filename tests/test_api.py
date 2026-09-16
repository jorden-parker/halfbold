import json
import os
from pathlib import Path

from conftest import make_font
from test_scan import fill_fonts_dir
from test_web import CSS

from halfbold import api
from halfbold.api import main
from halfbold.brewcask import CaskInfo
from halfbold.scan import build_all


def test_installed_lists_candidates_with_flags(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)

    result = main(["installed", "--fonts-dir", str(fonts)])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    families = sorted(c["family"] for c in payload["candidates"])
    assert families == ["Pair", "Var"]
    for candidate in payload["candidates"]:
        assert candidate["built"] is False
        assert candidate["stale"] is True
        if candidate["family"] == "Var":
            assert candidate["bold"] is None


def test_build_writes_half_font(font_pair, tmp_path: Path, capsys):
    regular, bold = font_pair
    output = tmp_path / "Out-Half.ttf"

    result = main(["build", str(regular), str(bold), "-o", str(output)])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert output.exists()
    assert payload["letters"] == 26


def test_preview_caches_half_in_cache_dir(
    font_pair, tmp_path: Path, capsys, monkeypatch
):
    regular, bold = font_pair
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)

    result = main(["preview", str(regular), str(bold)])
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    half = Path(payload["half"])
    assert half.exists()
    assert half.parent == cache_dir
    first_mtime = half.stat().st_mtime

    result = main(["preview", str(regular), str(bold)])
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["half"]).stat().st_mtime == first_mtime

    future = first_mtime + 10
    os.utime(regular, (future, future))
    result = main(["preview", str(regular), str(bold)])
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["half"]).stat().st_mtime != first_mtime


def test_preview_rejects_non_font(tmp_path: Path, capsys):
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"nope")

    result = main(["preview", str(bad)])

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert "not a TrueType font" in payload["error"]


def test_cask_fonts_downloads_into_cache(monkeypatch, tmp_path: Path, capsys):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)

    def fake_cask_font_dir(token, into):
        make_font(into / "Test-Regular.ttf", "Test", "Regular", 100)
        make_font(into / "Test-Bold.ttf", "Test", "Bold", 200)
        return into

    monkeypatch.setattr(api, "cask_font_dir", fake_cask_font_dir)

    result = main(["cask-fonts", "font-test"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["token"] == "font-test"
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["family"] == "Test"


def test_cask_install_returns_installed_candidates(monkeypatch, tmp_path: Path, capsys):
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    regular = make_font(fonts_dir / "Test-Regular.ttf", "Test", "Regular", 100)
    bold = make_font(fonts_dir / "Test-Bold.ttf", "Test", "Bold", 200)
    calls = []

    def fake_install_cask(token):
        calls.append(token)

    def fake_cask_info(token):
        return CaskInfo(
            token=token,
            url="",
            branch="",
            only_path="",
            fonts=[regular.name, bold.name],
            targets=["", ""],
        )

    monkeypatch.setattr(api, "install_cask", fake_install_cask)
    monkeypatch.setattr(api, "cask_info", fake_cask_info)

    result = main(["cask-install", "font-test", "--fonts-dir", str(fonts_dir)])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["token"] == "font-test"
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["family"] == "Test"
    assert calls == ["font-test"]


def test_web_sets_slot_and_reads_back(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)

    result = main(
        ["web", "serif", "Pair", "--css", str(css), "--fonts-dir", str(fonts)]
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["serif"] == "Pair Half"

    result = main(
        ["web", "serif", "Nope", "--css", str(css), "--fonts-dir", str(fonts)]
    )
    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert "Nope Half" in payload["error"]


def test_casks_reports_brew_failure(monkeypatch, capsys):
    def fake_search_font_casks():
        raise ValueError("brew search failed: x")

    monkeypatch.setattr(api, "search_font_casks", fake_search_font_casks)

    result = main(["casks"])

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "brew search failed: x"
