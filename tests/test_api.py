import io
import json
import os
from pathlib import Path

import pytest
from conftest import make_collection, make_font
from fontTools.ttLib import TTFont
from test_scan import fill_fonts_dir
from test_web import CSS

from halfbold import api
from halfbold.api import main
from halfbold.brewcask import CaskInfo
from halfbold.scan import build_all, candidates_from_paths
from halfbold.settings import Settings


@pytest.fixture(autouse=True)
def isolated_reset_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "ORIGINALS_PATH", tmp_path / "originals.json")
    monkeypatch.setattr(api, "WATCHER_PLIST", tmp_path / "watcher.plist")


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
    assert (tmp_path / "Out-HalfBold.ttf").exists()
    assert payload["bold_face"] == str(tmp_path / "Out-HalfBold.ttf")
    assert payload["letters"] == 52


def test_preview_writes_no_half_bold_face(
    font_pair, tmp_path: Path, capsys, monkeypatch
):
    regular, bold = font_pair
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)

    assert main(["preview", str(regular), str(bold)]) == 0

    assert not list(cache_dir.glob("*HalfBold*"))


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
    assert "two weights of the same family" in error


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


def test_installed_discovers_system_fonts_and_builds_into_user_folder(
    tmp_path, monkeypatch, capsys
):
    from halfbold import scan

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    fonts = tmp_path / "Library/Fonts"
    fonts.mkdir(parents=True)
    system = tmp_path / "system"
    supplemental = system / "Supplemental"
    supplemental.mkdir(parents=True)
    regular = make_font(supplemental / "Arial.TTF", "Arial", "Regular", 100)
    bold = make_font(supplemental / "Arial Bold.ttf", "Arial", "Bold", 200)
    monkeypatch.setattr(scan, "installed_font_dirs", lambda: [system])

    assert main(["installed", "--fonts-dir", str(fonts)]) == 0
    candidate = json.loads(capsys.readouterr().out)["candidates"][0]
    assert candidate["family"] == "Arial"
    assert candidate["regular"] == str(regular)
    assert candidate["bold"] == str(bold)
    assert candidate["output"] == str(fonts / "Arial-Half.ttf")
    assert main(["build", str(regular), str(bold), "-o", candidate["output"]]) == 0
    capsys.readouterr()
    assert main(["installed", "--fonts-dir", str(fonts)]) == 0
    rebuilt = json.loads(capsys.readouterr().out)["candidates"][0]
    assert rebuilt["built"] is True
    assert rebuilt["stale"] is False
    assert not (supplemental / "Arial-Half.ttf").exists()


def make_menlo_collection(tmp_path, family="Menlo"):
    parts = tmp_path / "parts"
    parts.mkdir(exist_ok=True)
    system = tmp_path / "system"
    system.mkdir(exist_ok=True)
    regular = make_font(parts / "Menlo-Regular.ttf", family, "Regular", 100, weight=400)
    bold = make_font(parts / "Menlo-Bold.ttf", family, "Bold", 200, weight=700)
    return make_collection(system / "Menlo.ttc", [regular, bold])


def test_build_accepts_collection_faces(tmp_path, capsys):
    ttc = make_menlo_collection(tmp_path)
    out = tmp_path / "Menlo-Half.ttf"

    assert main(["build", f"{ttc}#0", f"{ttc}#1", "-o", str(out)]) == 0
    capsys.readouterr()

    assert out.exists()
    assert TTFont(out)["name"].getDebugName(1) == "Menlo Half"


def test_preview_accepts_collection_faces_and_caches_half(
    tmp_path, capsys, monkeypatch
):
    ttc = make_menlo_collection(tmp_path)
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)
    faces = ["--face", f"{ttc}#0", "--face", f"{ttc}#1"]

    assert main(["preview", *faces]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "error" not in payload
    first_mtime = Path(payload["half"]).stat().st_mtime

    assert main(["preview", *faces]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["half"]).stat().st_mtime == first_mtime


def test_face_file_extracts_a_collection_face_once(tmp_path, capsys, monkeypatch):
    ttc = make_menlo_collection(tmp_path)
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)

    assert main(["face-file", f"{ttc}#1"]) == 0
    extracted = Path(json.loads(capsys.readouterr().out)["path"])
    assert extracted.suffix == ".ttf"
    assert cache_dir / "collections" in extracted.parents
    assert TTFont(extracted)["name"].getDebugName(2) == "Bold"
    first_mtime = extracted.stat().st_mtime

    assert main(["face-file", f"{ttc}#1"]) == 0
    again = Path(json.loads(capsys.readouterr().out)["path"])
    assert again == extracted
    assert again.stat().st_mtime == first_mtime


def test_face_file_returns_plain_font_paths_unchanged(
    font_pair, tmp_path, capsys, monkeypatch
):
    regular, _ = font_pair
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(api, "CACHE_DIR", cache_dir)

    assert main(["face-file", str(regular)]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == str(regular)
    assert not cache_dir.exists()


def test_installed_lists_faces_inside_a_collection(tmp_path, monkeypatch, capsys):
    from halfbold import scan

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    fonts = tmp_path / "Library/Fonts"
    fonts.mkdir(parents=True)
    ttc = make_menlo_collection(tmp_path)
    monkeypatch.setattr(scan, "installed_font_dirs", lambda: [tmp_path / "system"])

    assert main(["installed", "--fonts-dir", str(fonts)]) == 0
    candidate = json.loads(capsys.readouterr().out)["candidates"][0]
    assert candidate["family"] == "Menlo"
    assert candidate["regular"] == f"{ttc}#0"
    assert candidate["bold"] == f"{ttc}#1"
    assert candidate["output"] == str(fonts / "Menlo-Half.ttf")
    assert candidate["built"] is False
    assert candidate["stale"] is True


def test_installed_hides_collections_of_private_dot_families(
    tmp_path, monkeypatch, capsys
):
    from halfbold import scan

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    fonts = tmp_path / "Library/Fonts"
    fonts.mkdir(parents=True)
    make_menlo_collection(tmp_path, family=".Hidden")
    monkeypatch.setattr(scan, "installed_font_dirs", lambda: [tmp_path / "system"])

    assert main(["installed", "--fonts-dir", str(fonts)]) == 0
    assert json.loads(capsys.readouterr().out)["candidates"] == []


def test_installed_prefers_user_pair_over_duplicate_system_pair(tmp_path, monkeypatch):
    from halfbold import scan

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    fonts = tmp_path / "Library/Fonts"
    system = tmp_path / "system"
    for root in (fonts, system):
        root.mkdir(parents=True)
        make_font(root / "Arial.ttf", "Arial", "Regular", 100)
        make_font(root / "Arial Bold.ttf", "Arial", "Bold", 200)
    monkeypatch.setattr(scan, "installed_font_dirs", lambda: [system])

    candidates = scan.find_installed_candidates(fonts)
    assert len(candidates) == 1
    assert candidates[0].regular.parent == fonts
    assert candidates[0].bold.parent == fonts


def test_installed_custom_folder_stays_scoped(tmp_path, monkeypatch):
    from halfbold import scan

    fonts = tmp_path / "custom"
    system = tmp_path / "system"
    fill_fonts_dir(fonts)
    system.mkdir()
    make_font(system / "Arial.ttf", "Arial", "Regular", 100)
    make_font(system / "Arial Bold.ttf", "Arial", "Bold", 200)
    monkeypatch.setattr(scan, "installed_font_dirs", lambda: [system])

    assert {c.family for c in scan.find_installed_candidates(fonts)} == {"Pair", "Var"}


def test_installed_payload_reports_the_resolved_faces(
    multi_weight_family: Path, monkeypatch, capsys
):
    path = multi_weight_family / "settings.json"
    monkeypatch.setattr("halfbold.settings.default_settings_path", lambda: path)
    assert (
        main(["settings", json.dumps({"regular_weight": 300, "bold_weight": 500})]) == 0
    )
    capsys.readouterr()

    assert main(["installed", "--fonts-dir", str(multi_weight_family)]) == 0

    candidate = json.loads(capsys.readouterr().out)["candidates"][0]
    assert Path(candidate["regular"]).name == "Multi-Light.ttf"
    assert Path(candidate["bold"]).name == "Multi-Medium.ttf"
    assert candidate["plain_face"]["weight"] == 300
    assert candidate["bold_face"]["style"] == "Medium"
    assert candidate["faces_label"] == "plain Light 300, bold Medium 500"
    assert [f["weight"] for f in candidate["faces"]] == [300, 400, 500, 700]


def test_preview_reuses_one_build_across_weight_stops(
    font_pair, tmp_path: Path, capsys, monkeypatch
):
    regular, bold = font_pair
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        "halfbold.settings.default_settings_path", lambda: tmp_path / "settings.json"
    )

    assert main(["preview", str(regular), str(bold)]) == 0
    first = json.loads(capsys.readouterr().out)["half"]
    built = Path(first).stat().st_mtime

    for weight in (350, 450, 500):
        assert main(["settings", json.dumps({"regular_weight": weight})]) == 0
        capsys.readouterr()
        assert main(["preview", str(regular), str(bold)]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["half"] == first
        assert Path(payload["half"]).stat().st_mtime == built


def test_preview_cache_key_tracks_the_resolved_faces(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    light = make_font(fonts / "Three-Light.ttf", "Three", "Light", 80)
    make_font(fonts / "Three-Regular.ttf", "Three", "Regular", 100)
    make_font(fonts / "Three-Bold.ttf", "Three", "Bold", 200)

    def tag(regular_weight: float) -> str:
        settings = Settings(regular_weight=regular_weight)
        paths = sorted(fonts.glob("Three-*.ttf"))
        candidate = next(
            c for c in candidates_from_paths(paths, settings) if c.family == "Three"
        )
        return api.faces_tag(candidate)

    assert tag(380) == tag(420)
    assert tag(300) != tag(420)
    assert light.stem.replace("-", "") in tag(300)


def test_preview_cache_key_clamps_variable_weights(tmp_path: Path):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)

    def tag(regular_weight: float) -> str:
        settings = Settings(regular_weight=regular_weight)
        candidate = next(
            c
            for c in candidates_from_paths([fonts / "Var.ttf"], settings)
            if c.family == "Var"
        )
        return api.faces_tag(candidate)

    assert tag(100) == tag(150)
    assert tag(100) != tag(500)


def test_preview_from_faces_resolves_the_pair(tmp_path: Path, capsys, monkeypatch):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    light = make_font(fonts / "Three-Light.ttf", "Three", "Light", 80)
    regular = make_font(fonts / "Three-Regular.ttf", "Three", "Regular", 100)
    bold = make_font(fonts / "Three-Bold.ttf", "Three", "Bold", 200)
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        "halfbold.settings.default_settings_path", lambda: tmp_path / "settings.json"
    )
    faces = ["--face", str(light), "--face", str(regular), "--face", str(bold)]

    assert main(["preview", *faces, "--fonts-dir", str(fonts)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["family"] == "Three"
    assert payload["regular"] == str(regular)
    assert payload["plain_face"]["style"] == "Regular"
    assert payload["bold_face"]["style"] == "Bold"
    assert [f["style"] for f in payload["faces"]] == ["Light", "Regular", "Bold"]
    assert payload["output"] == str(fonts / "Three-Half.ttf")

    assert main(["settings", json.dumps({"regular_weight": 300})]) == 0
    capsys.readouterr()
    assert main(["preview", *faces, "--fonts-dir", str(fonts)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["regular"] == str(light)
    assert payload["plain_face"]["style"] == "Light"


def test_preview_needs_either_a_file_or_faces(tmp_path: Path):
    with pytest.raises(SystemExit):
        api.parse_args(["preview"])
    with pytest.raises(SystemExit):
        api.parse_args(["preview", str(tmp_path / "a.ttf"), "--face", "b.ttf"])


def test_vscode_sets_editor_font_for_installed_half(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n")

    result = main(
        ["vscode", "Pair", "--settings", str(settings), "--fonts-dir", str(fonts)]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["font_family"] == "'Pair Half', monospace"
    assert json.loads(settings.read_text())["editor.fontLigatures"] is True


def test_vscode_rejects_family_without_half(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n")

    result = main(
        ["vscode", "Pair", "--settings", str(settings), "--fonts-dir", str(fonts)]
    )

    assert result == 1
    assert "Pair Half" in json.loads(capsys.readouterr().out)["error"]
    assert settings.read_text() == "{}\n"


def test_reset_restores_slots_and_vscode(tmp_path: Path, capsys):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)
    vscode_dir = tmp_path / "Code" / "User"
    vscode_dir.mkdir(parents=True)
    settings = vscode_dir / "settings.json"
    settings.write_text('{"editor.fontFamily": "Menlo"}')
    common = ["--fonts-dir", str(fonts)]
    main(["web", "sans", "Pair", "--css", str(css), *common])
    main(["vscode", "Pair", "--settings", str(settings), *common])
    capsys.readouterr()

    result = main(["reset", "--css", str(css), "--settings", str(settings), *common])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["restored"] == ["vscode", "web"]
    assert payload["web"]["sans"] == "Inter Half"
    assert payload["deleted"] == []
    assert json.loads(settings.read_text()) == {"editor.fontFamily": "Menlo"}
    assert list(fonts.glob("*-Half.ttf")) != []


def test_reset_delete_fonts_removes_watcher_then_half_fonts(
    monkeypatch, tmp_path: Path, capsys
):
    fonts = tmp_path / "fonts"
    fill_fonts_dir(fonts)
    build_all(fonts)
    css = tmp_path / "halfbold.css"
    css.write_text(CSS)
    events = []

    def fake_remove_watcher(plist: Path) -> bool:
        events.append(("watcher", sorted(p.name for p in fonts.glob("*-Half.ttf"))))
        return True

    monkeypatch.setattr(api, "remove_watcher", fake_remove_watcher)

    result = main(
        [
            "reset",
            "--delete-fonts",
            "--css",
            str(css),
            "--settings",
            str(tmp_path / "settings.json"),
            "--fonts-dir",
            str(fonts),
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["watcher_removed"] is True
    assert payload["deleted"] == ["Pair Half", "Var Half"]
    assert events[0][1] != []
    assert list(fonts.glob("*-Half.ttf")) == []
    assert list(fonts.glob("*-HalfBold.ttf")) == []
    assert (fonts / "Pair-Regular.ttf").exists()
