import io
import json
import select
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from halfbold import browser


def test_protocol_handles_unicode_and_truncated_messages():
    stream = io.BytesIO()
    browser.write_message(stream, {"css": 'font-family: "Français"'})
    stream.seek(0)
    assert browser.read_message(stream) == {"css": 'font-family: "Français"'}
    assert browser.read_message(stream) is None
    for data in (b"xx", struct.pack("=I", 8) + b"{}", struct.pack("=I", 65537)):
        with pytest.raises(ValueError):
            browser.read_message(io.BytesIO(data))


def test_setup_registers_stable_extension_and_executable_host(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    css = Path(__file__).resolve().parents[1] / "chrome-extension/halfbold.css"
    result = browser.setup_browser(css, open_chrome=False)
    extension = Path(result["extension_dir"])
    assert result["configured"]
    assert not result["connected"]
    manifest = json.loads((extension / "manifest.json").read_text())
    host_path = next(tmp_path.rglob(f"{browser.HOST}.json"))
    host = json.loads(host_path.read_text())
    assert host["allowed_origins"] == [
        f"chrome-extension://{browser.extension_id(manifest)}/"
    ]
    assert Path(host["path"]).stat().st_mode & 0o100
    assert (extension / "shadow.js").read_bytes() == (
        css.parent / "shadow.js"
    ).read_bytes()


def test_status_requires_recent_ack_of_current_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "support_dir", lambda: tmp_path)
    css = tmp_path / "test.css"
    css.write_text("first")
    status = tmp_path / "status.json"
    status.write_text(
        json.dumps({"time": time.time(), "revision": browser.revision("first")})
    )
    assert browser.browser_status(css)["synced"]
    css.write_text("second")
    assert browser.browser_status(css)["connected"]
    assert not browser.browser_status(css)["synced"]
    status.write_text(json.dumps({"time": time.time() - 10}))
    assert not browser.browser_status(css)["connected"]
    status.write_text("{")
    assert not browser.browser_status(css)["connected"]


def test_host_pushes_changes_acknowledges_and_exits_on_disconnect(tmp_path):
    css = tmp_path / "test.css"
    css.write_text("first")
    code = (
        "from pathlib import Path; from halfbold import browser; "
        f"browser.support_dir = lambda: Path({str(tmp_path)!r}); "
        f"browser.native_host(Path({str(css)!r}))"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    def receive_style():
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], 0.2)
            if ready:
                message = browser.read_message(process.stdout)
                if "css" in message:
                    return message
        pytest.fail("host did not push a stylesheet")

    try:
        first = receive_style()
        assert first["css"] == "first"
        browser.write_message(process.stdin, {"revision": first["revision"]})
        browser.write_message(process.stdin, {"pong": True})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status = tmp_path / "status.json"
            if (
                status.exists()
                and json.loads(status.read_text()).get("revision") == first["revision"]
            ):
                break
            time.sleep(0.02)
        assert (
            json.loads((tmp_path / "status.json").read_text())["revision"]
            == first["revision"]
        )
        css.write_text("second")
        assert receive_style()["css"] == "second"
        process.stdin.close()
        assert process.wait(timeout=3) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
