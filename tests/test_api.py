import io
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


def test_settings_command_saves_and_reports(monkeypatch, tmp_path: Path, capsys):
    path = tmp_path / "settings.json"
    monkeypatch.setattr("halfbold.settings.default_settings_path", lambda: path)

    assert main(["settings", json.dumps({"bold_share": 0.4, "bold_weight": 800})]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["settings"]["bold_share"] == 0.4
    assert payload["defaults"]["bold_share"] == 0.5

    assert main(["settings"]) == 0
    assert json.loads(capsys.readouterr().out)["settings"]["bold_weight"] == 800

    assert main(["settings", json.dumps({"bold_share": 2})]) == 1
    assert "bold_share" in json.loads(capsys.readouterr().out)["error"]


def test_preview_cache_key_includes_settings(
    font_pair, tmp_path: Path, capsys, monkeypatch
):
    regular, bold = font_pair
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path / "cache")
    path = tmp_path / "settings.json"
    monkeypatch.setattr("halfbold.settings.default_settings_path", lambda: path)

    assert main(["preview", str(regular), str(bold)]) == 0
    first = json.loads(capsys.readouterr().out)["half"]
    assert main(["settings", json.dumps({"bold_share": 0.75})]) == 0
    capsys.readouterr()
    assert main(["preview", str(regular), str(bold)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["half"] != first
    assert second["settings"]["bold_share"] == 0.75


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


def test_cask_fonts_reuses_downloaded_fonts(monkeypatch, tmp_path: Path, capsys):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)
    downloads = []

    def fake_cask_font_dir(token, into):
        downloads.append(token)
        make_font(into / "Test-Regular.ttf", "Test", "Regular", 100)
        make_font(into / "Test-Bold.ttf", "Test", "Bold", 200)
        return into

    monkeypatch.setattr(api, "cask_font_dir", fake_cask_font_dir)

    assert main(["cask-fonts", "font-test"]) == 0
    assert main(["cask-fonts", "font-test"]) == 0

    assert downloads == ["font-test"]
    payloads = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert payloads[0] == payloads[1]


def test_cask_fonts_explains_why_nothing_converts(monkeypatch, tmp_path: Path, capsys):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)

    def fake_cask_font_dir(token, into):
        make_font(into / "Lonely-Regular.ttf", "Lonely", "Regular", 100)
        return into

    monkeypatch.setattr(api, "cask_font_dir", fake_cask_font_dir)

    assert main(["cask-fonts", "font-lonely"]) == 1

    error = json.loads(capsys.readouterr().out)["error"]
    assert "Lonely (Regular)" in error
    assert "Regular and Bold pair" in error


def test_serve_answers_requests_by_id(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    requests = [
        {"id": 1, "args": ["installed", "--fonts-dir", str(fonts)]},
        {"id": 2, "args": ["preview", str(tmp_path / "missing.ttf")]},
        {"id": 3, "args": ["serve"]},
    ]
    stdin = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    stdout = io.StringIO()

    assert api.serve(stdin, stdout) == 0

    replies = {r["id"]: r for r in map(json.loads, stdout.getvalue().splitlines())}
    assert replies[1]["ok"] is True
    families = sorted(c["family"] for c in replies[1]["result"]["candidates"])
    assert families == ["Pair", "Var"]
    assert replies[2]["ok"] is False
    assert "missing.ttf" in replies[2]["error"]
    assert replies[3] == {"id": 3, "ok": False, "error": "serve cannot be nested"}


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


def test_casks_returns_names_from_index(monkeypatch, capsys):
    def fake_cask_index():
        return [
            {
                "token": "font-roboto",
                "name": ["Roboto"],
                "url": "https://github.com/google/fonts.git",
                "url_specs": {"only_path": "ofl/roboto"},
                "artifacts": [{"font": ["Roboto[wdth,wght].ttf"]}],
            },
            {
                "token": "font-noto",
                "name": ["Noto Sans"],
                "url": "https://x.zip",
                "artifacts": [
                    {"font": ["NotoSans-Regular.ttf"]},
                    {"font": ["NotoSans-Bold.ttf"]},
                ],
            },
            {
                "token": "not-font",
                "name": ["X"],
            },
        ]

    monkeypatch.setattr(api, "cask_index", fake_cask_index)

    result = main(["casks"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["casks"]) == 2
    assert payload["casks"][0]["token"] == "font-noto"
    assert payload["casks"][0]["name"] == "Noto Sans"
    assert payload["casks"][0]["google"] is False
    assert payload["casks"][1]["token"] == "font-roboto"
    assert payload["casks"][1]["name"] == "Roboto"
    assert payload["casks"][1]["google"] is True


def test_casks_falls_back_to_brew_search(monkeypatch, capsys):
    def fake_cask_index():
        raise ValueError("index unavailable")

    def fake_search_font_casks():
        return ["font-z"]

    monkeypatch.setattr(api, "cask_index", fake_cask_index)
    monkeypatch.setattr(api, "search_font_casks", fake_search_font_casks)

    result = main(["casks"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["casks"]) == 1
    assert payload["casks"][0]["token"] == "font-z"
    assert payload["casks"][0]["name"] == "font-z"
    assert payload["casks"][0]["google"] is False


def test_cask_face_google(monkeypatch, capsys, tmp_path):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)

    def fake_cask_index():
        return [
            {
                "token": "font-roboto",
                "url": "https://github.com/google/fonts.git",
                "url_specs": {"only_path": "ofl/roboto"},
            }
        ]

    def fake_download_google_face(info, into):
        path = into / "Roboto.ttf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"font")
        return path

    monkeypatch.setattr(api, "cask_index", fake_cask_index)
    monkeypatch.setattr(api, "download_google_face", fake_download_google_face)

    result = main(["cask-face", "font-roboto"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["token"] == "font-roboto"
    assert payload["face"].endswith("Roboto.ttf")
    assert (cache_dir / "faces" / "font-roboto" / "Roboto.ttf").exists()


def test_cask_face_non_google(monkeypatch, capsys, tmp_path):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)

    def fake_cask_index():
        return [
            {
                "token": "font-0xproto",
                "url": "https://x.zip",
            }
        ]

    def fake_download_google_face(info, into):
        return None

    monkeypatch.setattr(api, "cask_index", fake_cask_index)
    monkeypatch.setattr(api, "download_google_face", fake_download_google_face)

    result = main(["cask-face", "font-0xproto"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["token"] == "font-0xproto"
    assert payload["face"] is None


def test_cask_face_unknown_token(monkeypatch, capsys):
    def fake_cask_index():
        return []

    monkeypatch.setattr(api, "cask_index", fake_cask_index)

    result = main(["cask-face", "font-nope"])

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "unknown cask: font-nope"


def test_casks_reports_brew_failure(monkeypatch, capsys):
    def fake_cask_index():
        raise ValueError("index failed")

    def fake_search_font_casks():
        raise ValueError("brew search failed: x")

    monkeypatch.setattr(api, "cask_index", fake_cask_index)
    monkeypatch.setattr(api, "search_font_casks", fake_search_font_casks)

    result = main(["casks"])

    assert result == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "brew search failed: x"
