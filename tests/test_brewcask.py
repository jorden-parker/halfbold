import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from halfbold import brewcask, cli
from halfbold.brewcask import (
    CaskInfo,
    cask_font_dir,
    extract_fonts,
    google_fonts_urls,
    parse_cask_info,
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
