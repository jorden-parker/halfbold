import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from halfbold import brewcask, cli
from halfbold.brewcask import (
    CaskInfo,
    cask_font_dir,
    cask_info_from_payload,
    download_google_face,
    extract_fonts,
    fetch_cask_index,
    font_cask_entries,
    google_fonts_urls,
    installed_font_paths,
    parse_cask_info,
    parse_font_cask_tokens,
    search_font_casks,
)

ROBOTO_JSON = {
    "casks": [
        {
            "token": "font-roboto",
            "url": "https://github.com/google/fonts.git",
            "url_specs": {"branch": "main", "only_path": "ofl/roboto"},
            "artifacts": [
                {
                    "font": ["Roboto[wdth,wght].ttf"],
                    "target": "/Users/x/Library/Fonts/Roboto[wdth,wght].ttf",
                }
            ],
        }
    ]
}


def test_parse_cask_info_google():
    info = parse_cask_info(json.dumps(ROBOTO_JSON).encode())
    assert info.only_path == "ofl/roboto"
    assert info.branch == "main"
    assert info.fonts == ["Roboto[wdth,wght].ttf"]


def test_parse_cask_info_targets():
    info = parse_cask_info(json.dumps(ROBOTO_JSON).encode())
    assert info.targets == ["/Users/x/Library/Fonts/Roboto[wdth,wght].ttf"]


def test_parse_cask_info_without_url_specs():
    data = {
        "casks": [
            {
                "token": "font-inter",
                "url": "https://example.com/Inter.zip",
                "artifacts": [{"font": ["Inter.ttf"]}],
            }
        ]
    }
    info = parse_cask_info(json.dumps(data).encode())
    assert info.only_path == ""


def test_google_fonts_urls_skips_italic_and_encodes_brackets():
    info = CaskInfo(
        token="font-roboto",
        url="https://github.com/google/fonts.git",
        branch="main",
        only_path="ofl/roboto",
        fonts=["Roboto-Italic[wdth,wght].ttf", "Roboto[wdth,wght].ttf"],
        targets=[],
    )
    urls = google_fonts_urls(info)
    assert len(urls) == 1
    assert urls[0].endswith("/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf")


def test_google_fonts_urls_empty_for_other_git():
    info = CaskInfo(
        token="font-x",
        url="https://github.com/x/y.git",
        branch="main",
        only_path="fonts",
        fonts=["X.ttf"],
        targets=[],
    )
    assert google_fonts_urls(info) == []


def test_extract_zip_returns_ttfs(tmp_path, font_pair):
    regular, bold = font_pair
    archive = tmp_path / "fonts.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(regular, f"fonts/ttf/{regular.name}")
        zf.write(bold, f"fonts/ttf/{bold.name}")
    into = tmp_path / "out"
    into.mkdir()
    found = extract_fonts(archive, into)
    assert len(found) == 2


def test_extract_zip_rejects_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.ttf", b"data")
    into = tmp_path / "out"
    into.mkdir()
    with pytest.raises(ValueError, match="unsafe"):
        extract_fonts(archive, into)


def test_extract_tar_xz(tmp_path, variable_font):
    archive = tmp_path / "font.tar.xz"
    with tarfile.open(archive, "w:xz") as tf:
        tf.add(variable_font, arcname=variable_font.name)
    into = tmp_path / "out"
    into.mkdir()
    found = extract_fonts(archive, into)
    assert len(found) == 1


def test_extract_unknown_suffix(tmp_path):
    archive = tmp_path / "x.exe"
    archive.write_bytes(b"data")
    into = tmp_path / "out"
    into.mkdir()
    with pytest.raises(ValueError, match="unsupported"):
        extract_fonts(archive, into)


def test_cask_font_dir_uses_google_download(monkeypatch, tmp_path, variable_font):
    info = CaskInfo(
        token="font-testvar",
        url="https://github.com/google/fonts.git",
        branch="main",
        only_path="ofl/testvar",
        fonts=["TestVar.ttf"],
        targets=[],
    )

    def fake_download(info, into):
        dest = into / "TestVar.ttf"
        dest.write_bytes(variable_font.read_bytes())
        return [dest]

    def fail_fetch(token):
        raise AssertionError("fetch_cask_archive should not be called")

    monkeypatch.setattr(brewcask, "cask_info", lambda token: info)
    monkeypatch.setattr(brewcask, "download_google_fonts", fake_download)
    monkeypatch.setattr(brewcask, "fetch_cask_archive", fail_fetch)

    into = tmp_path / "out"
    into.mkdir()
    result = cask_font_dir("font-testvar", into)
    assert list(result.glob("*.ttf"))


def test_cli_preview_cask_png(monkeypatch, tmp_path, variable_font, capsys):
    def fake_cask_font_dir(token, into):
        dest = Path(into) / "TestVar.ttf"
        dest.write_bytes(variable_font.read_bytes())
        return Path(into)

    monkeypatch.setattr(cli, "cask_font_dir", fake_cask_font_dir)
    out_png = tmp_path / "o.png"
    result = cli.main(["--preview-cask", "font-x", "--png", str(out_png)])
    assert result == 0
    assert out_png.exists()


def test_cli_preview_cask_rejects_other_modes():
    with pytest.raises(SystemExit):
        cli.main(["--preview-cask", "font-x", "--all"])


def test_parse_font_cask_tokens_keeps_only_font_prefix():
    text = "==> Casks\nfont-roboto\n  font-inter \nnot-a-font\n\n"
    assert parse_font_cask_tokens(text) == ["font-roboto", "font-inter"]


def test_installed_font_paths_falls_back_to_fonts_dir(tmp_path):
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    sub = tmp_path / "sub"
    sub.mkdir()
    a_path = fonts_dir / "A.ttf"
    a_path.write_bytes(b"a")
    b_path = sub / "B.ttf"
    b_path.write_bytes(b"b")
    info = CaskInfo(
        token="font-x",
        url="",
        branch="",
        only_path="",
        fonts=["A.ttf", "B.ttf"],
        targets=["", str(b_path)],
    )

    paths = installed_font_paths(info, fonts_dir)
    assert paths == [a_path, b_path]

    a_path.unlink()
    paths = installed_font_paths(info, fonts_dir)
    assert paths == [b_path]


def test_cask_info_from_payload_matches_parse_cask_info():
    cask = ROBOTO_JSON["casks"][0]
    from_payload = cask_info_from_payload(cask)
    from_parse = parse_cask_info(json.dumps(ROBOTO_JSON).encode())
    assert from_payload == from_parse


def test_font_cask_entries_names_and_google_flag():
    index = [
        {
            "token": "font-b",
            "name": ["B Font"],
            "url": "https://github.com/google/fonts.git",
            "url_specs": {"only_path": "ofl/b"},
        },
        {
            "token": "font-a",
            "name": [],
            "url": "https://x/a.zip",
        },
        {
            "token": "not-font",
            "name": ["X"],
        },
    ]
    entries = font_cask_entries(index)
    assert len(entries) == 2
    assert entries[0] == {"token": "font-b", "name": "B Font", "google": True}
    assert entries[1] == {"token": "font-a", "name": "font-a", "google": False}


def test_fetch_cask_index_uses_fresh_cache(tmp_path, monkeypatch):
    cache = tmp_path / "index.json"
    cache.write_text(json.dumps([{"token": "font-x"}]))

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("network used")

    monkeypatch.setattr(brewcask.urllib.request, "urlopen", fail_urlopen)
    result = fetch_cask_index(cache)
    assert result == [{"token": "font-x"}]


def test_fetch_cask_index_downloads_when_stale(tmp_path, monkeypatch):
    import os

    cache = tmp_path / "index.json"
    cache.write_text(json.dumps([{"token": "font-x"}]))
    os.utime(cache, (0, 0))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'[{"token": "font-y"}]'

    def fake_urlopen(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(brewcask.urllib.request, "urlopen", fake_urlopen)
    result = fetch_cask_index(cache)
    assert result == [{"token": "font-y"}]
    assert cache.read_text() == '[{"token": "font-y"}]'


def test_fetch_cask_index_falls_back_to_stale_cache_offline(tmp_path, monkeypatch):
    from urllib.error import URLError

    cache = tmp_path / "index.json"
    cache.write_text(json.dumps([{"token": "font-x"}]))

    def fail_urlopen(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr(brewcask.urllib.request, "urlopen", fail_urlopen)
    result = fetch_cask_index(cache)
    assert result == [{"token": "font-x"}]


def test_download_google_face_downloads_first_regular(tmp_path, monkeypatch):
    info = CaskInfo(
        token="font-roboto",
        url="https://github.com/google/fonts.git",
        branch="main",
        only_path="ofl/roboto",
        fonts=["Roboto-Italic[wdth,wght].ttf", "Roboto[wdth,wght].ttf"],
        targets=[],
    )

    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b"ttf"

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        return FakeResponse()

    monkeypatch.setattr(brewcask.urllib.request, "urlopen", fake_urlopen)
    result = download_google_face(info, tmp_path)
    assert result == tmp_path / "Roboto[wdth,wght].ttf"
    assert result.read_bytes() == b"ttf"
    assert len(calls) == 1
    assert calls[0].endswith("Roboto%5Bwdth%2Cwght%5D.ttf")

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("network used again")

    monkeypatch.setattr(brewcask.urllib.request, "urlopen", fail_urlopen)
    result2 = download_google_face(info, tmp_path)
    assert result2 == result


def test_download_google_face_none_for_other_casks():
    info = CaskInfo(
        token="font-x",
        url="https://x.com/x.zip",
        branch="",
        only_path="",
        fonts=["X.ttf"],
        targets=[],
    )
    result = download_google_face(info, Path("/tmp"))
    assert result is None


def test_search_font_casks_reports_brew_failure(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "brew", stderr=b"boom")

    monkeypatch.setattr(brewcask.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="brew search failed: boom"):
        search_font_casks()
