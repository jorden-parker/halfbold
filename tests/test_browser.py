import base64
import io
import json
import os
import select
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from halfbold import browser
from halfbold.settings import Settings, save_settings

EXTENSION_SOURCE = Path(__file__).resolve().parents[1] / "chrome-extension"


def test_protocol_handles_unicode_and_truncated_messages():
    stream = io.BytesIO()
    browser.write_message(stream, {"family": "Français"})
    stream.seek(0)
    assert browser.read_message(stream) == {"family": "Français"}
    assert browser.read_message(stream) is None
    too_large = struct.pack("=I", browser.MAX_MESSAGE_SIZE + 1)
    for data in (b"xx", struct.pack("=I", 8) + b"{}", too_large):
        with pytest.raises(ValueError):
            browser.read_message(io.BytesIO(data))


def test_protocol_accepts_a_font_sized_message():
    stream = io.BytesIO()
    browser.write_message(stream, {"data": "x" * (1024 * 1024)})
    stream.seek(0)
    assert len(browser.read_message(stream)["data"]) == 1024 * 1024


def test_setup_registers_stable_extension_and_module_host(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    extension = browser.extension_dir()
    extension.mkdir(parents=True)
    (extension / "shadow.js").write_text("retired")

    result = browser.setup_browser(open_chrome=False)

    assert result["configured"]
    assert result["enabled"]
    assert not result["connected"]
    manifest = json.loads((extension / "manifest.json").read_text())
    host = json.loads(next(tmp_path.rglob(f"{browser.HOST}.json")).read_text())
    assert host["allowed_origins"] == [
        f"chrome-extension://{browser.extension_id(manifest)}/"
    ]
    launcher = Path(host["path"])
    assert launcher.stat().st_mode & 0o100
    assert "-m halfbold.browser" in launcher.read_text()
    assert (extension / "pagefonts.js").read_bytes() == (
        EXTENSION_SOURCE / "pagefonts.js"
    ).read_bytes()
    assert not (extension / "shadow.js").exists()
    assert browser.served_fonts_dir().is_dir()


def test_disable_turns_conversion_off_and_can_delete_served_fonts(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    browser.setup_browser(open_chrome=False)
    (browser.served_fonts_dir() / "abc.ttf").write_bytes(b"font")

    browser.disable_browser()
    assert not browser.browser_status()["enabled"]
    assert (browser.served_fonts_dir() / "abc.ttf").exists()

    browser.disable_browser(delete_served_fonts=True)
    assert not browser.served_fonts_dir().exists()


def write_status(generation, **counts):
    status = browser.support_dir() / "status.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(
        json.dumps({"time": time.time(), "generation": generation, **counts})
    )
    return status


def test_status_requires_recent_ack_of_current_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_status(browser.current_generation(), converted=3, unchanged=1)
    status = browser.browser_status()
    assert status["synced"]
    assert (status["converted"], status["unchanged"]) == (3, 1)

    save_settings(Settings(bold_share=0.3))
    assert browser.browser_status()["connected"]
    assert not browser.browser_status()["synced"]

    write_status(browser.current_generation())
    browser.write_enabled(False)
    assert not browser.browser_status()["synced"]

    stale = write_status(browser.current_generation())
    stale.write_text(json.dumps({"time": time.time() - 10}))
    assert not browser.browser_status()["connected"]
    stale.write_text("{")
    assert not browser.browser_status()["connected"]


class Host:
    def __init__(self, home: Path, setup: str = ""):
        code = "\n".join(
            ("from halfbold import browser", setup, "browser.native_host()")
        )
        self.process = subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            env={**os.environ, "HOME": str(home)},
        )

    def send(self, message: dict) -> None:
        browser.write_message(self.process.stdin, message)

    def receive(self, matches, timeout: float = 5) -> list[dict]:
        seen = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.process.stdout], [], [], 0.2)
            if ready:
                message = browser.read_message(self.process.stdout)
                seen.append(message)
                if matches(message):
                    return seen
        pytest.fail(f"host never sent the expected message; saw {seen}")

    def close(self) -> int:
        self.process.stdin.close()
        return self.process.wait(timeout=5)

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()


@pytest.fixture
def host_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def is_config(message: dict) -> bool:
    return message.get("type") == "config"


def test_host_sends_config_records_pongs_and_exits_on_disconnect(host_home):
    host = Host(host_home)
    try:
        [*_, config] = host.receive(is_config)
        assert config["enabled"]
        assert config["generation"] == browser.current_generation()
        host.send({"pong": True, "generation": config["generation"], "converted": 2})
        deadline = time.monotonic() + 3
        while not browser.browser_status()["synced"] and time.monotonic() < deadline:
            time.sleep(0.02)
        assert browser.browser_status()["converted"] == 2
        browser.write_enabled(False)
        [*_, changed] = host.receive(is_config)
        assert not changed["enabled"]
        assert changed["generation"] != config["generation"]
        assert host.close() == 0
    finally:
        host.kill()


def encoded_face(path: Path, weight: int) -> dict:
    return {
        "weight": [weight, weight],
        "data": base64.b64encode(path.read_bytes()).decode(),
    }


def test_host_converts_a_webfont_into_the_served_fonts(host_home, font_pair):
    regular, bold = font_pair
    host = Host(host_home)
    try:
        host.receive(is_config)
        host.send(
            {
                "type": "convert-webfont",
                "id": 7,
                "faces": [encoded_face(regular, 400), encoded_face(bold, 700)],
            }
        )
        [*_, reply] = host.receive(lambda m: m.get("id") == 7)
        assert reply["type"] == "converted"
        [face] = reply["faces"]
        assert (browser.served_fonts_dir() / face["file"]).exists()
    finally:
        host.kill()


def test_host_reports_malformed_requests_as_unchanged(host_home):
    host = Host(host_home)
    try:
        host.receive(is_config)
        host.send({"type": "convert-webfont", "id": "x", "faces": [{"data": "!"}]})
        [*_, reply] = host.receive(lambda m: m.get("id") == "x")
        assert reply["type"] == "unchanged"
    finally:
        host.kill()


def test_host_keeps_heartbeats_going_during_a_slow_conversion(host_home):
    slow = (
        "import time; "
        "browser.handle_request = lambda *args: time.sleep(4) or {'type': 'converted'}"
    )
    host = Host(host_home, slow)
    try:
        host.receive(is_config)
        host.send({"type": "convert-installed", "id": 1, "family": "Slow"})
        seen = host.receive(lambda m: m.get("ping"))
        seen += host.receive(lambda m: m.get("ping"))
        assert not any(message.get("id") == 1 for message in seen)
    finally:
        host.kill()
