import base64
import hashlib
import json
import os
import select
import shlex
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

HOST = "com.jorden.halfbold"


def support_dir() -> Path:
    return Path.home() / "Library/Application Support/halfbold/browser"


def extension_id(manifest: dict) -> str:
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    return digest.translate(str.maketrans("0123456789abcdef", "abcdefghijklmnop"))


def revision(css: str) -> str:
    return hashlib.sha256(css.encode()).hexdigest()


def browser_status(css_path: Path) -> dict:
    root = support_dir()
    try:
        status = json.loads((root / "status.json").read_text())
        connected = 0 <= time.time() - status["time"] < 6
    except OSError, ValueError, KeyError, TypeError:
        status, connected = {}, False
    return {
        "configured": (root / "extension/manifest.json").exists(),
        "connected": connected,
        "synced": connected
        and status.get("revision") == revision(css_path.read_text()),
        "extension_dir": str(root / "extension"),
    }


def setup_browser(css_path: Path, *, open_chrome: bool = True) -> dict:
    root = support_dir()
    extension = root / "extension"
    extension.mkdir(parents=True, exist_ok=True)
    source = css_path.parent
    for name in ("manifest.json", "halfbold.css", "shadow.js", "autoreload.js"):
        shutil.copy2(source / name, extension / name)
    shutil.copy2(Path(__file__), root / "host.py")
    launcher = root / "host"
    launcher.write_text(
        "#!/bin/sh\nexec "
        + " ".join(
            shlex.quote(str(p)) for p in (sys.executable, root / "host.py", css_path)
        )
        + "\n"
    )
    launcher.chmod(0o700)
    manifest = json.loads((extension / "manifest.json").read_text())
    host_dir = (
        Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts"
    )
    host_dir.mkdir(parents=True, exist_ok=True)
    (host_dir / f"{HOST}.json").write_text(
        json.dumps(
            {
                "name": HOST,
                "description": "halfbold live font updates",
                "path": str(launcher),
                "type": "stdio",
                "allowed_origins": [f"chrome-extension://{extension_id(manifest)}/"],
            }
        )
    )
    if open_chrome:
        subprocess.run(["pbcopy"], input=str(extension), text=True, check=True)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Google Chrome"\n'
                "activate\nif (count of windows) = 0 then make new window\n"
                "make new tab at end of tabs of front window with properties "
                '{URL:"chrome://extensions"}\nend tell',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    return browser_status(css_path)


def read_message(stream) -> dict | None:
    def read_exact(size):
        chunks = bytearray()
        while len(chunks) < size:
            chunk = stream.read(size - len(chunks))
            if not chunk:
                break
            chunks.extend(chunk)
        return bytes(chunks)

    header = read_exact(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("Incomplete native message header")
    size = struct.unpack("=I", header)[0]
    if size > 65536:
        raise ValueError("Native message too large")
    body = read_exact(size)
    if len(body) != size:
        raise ValueError("Incomplete native message")
    message = json.loads(body)
    if not isinstance(message, dict):
        raise ValueError("Native message must be an object")
    return message


def write_message(stream, message: dict) -> None:
    body = json.dumps(message).encode()
    stream.write(struct.pack("=I", len(body)) + body)
    stream.flush()


def native_host(css_path: Path, stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin.buffer.raw
    stdout = stdout or sys.stdout.buffer
    root = support_dir()
    root.mkdir(parents=True, exist_ok=True)
    last_revision = None
    acknowledged = None
    last_heartbeat = 0
    while True:
        css = css_path.read_text()
        current = revision(css)
        if current != last_revision:
            write_message(stdout, {"css": css, "revision": current})
            last_revision = current
        now = time.monotonic()
        if now - last_heartbeat >= 2:
            write_message(stdout, {"ping": True})
            last_heartbeat = now
        readable, _, _ = select.select([stdin], [], [], 0.15)
        if readable:
            message = read_message(stdin)
            if message is None:
                return
            if message.get("revision") == current:
                acknowledged = current
            if message.get("pong") or message.get("revision") == current:
                status_path = root / f"status-{os.getpid()}.tmp"
                status_path.write_text(
                    json.dumps({"time": time.time(), "revision": acknowledged})
                )
                status_path.replace(root / "status.json")


if __name__ == "__main__":
    try:
        native_host(Path(sys.argv[1]))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
