import base64
import fcntl
import hashlib
import json
import os
import secrets
import select
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from halfbold.chrome_fonts import (
    WebFace,
    convert_installed_family,
    convert_webfont_family,
    prepare_default_fonts,
)
from halfbold.scan import installed_face_paths
from halfbold.settings import Settings, load_settings

HOST = "com.jorden.halfbold"
EXTENSION_SOURCE = Path(__file__).resolve().parents[2] / "chrome-extension"
EXTENSION_FILES = (
    "manifest.json",
    "pagefonts-core.js",
    "pagefonts.js",
    "limited-body.js",
    "autoreload.js",
)
RETIRED_EXTENSION_FILES = ("halfbold.css", "shadow.js")
MAX_MESSAGE_SIZE = 16 * 1024 * 1024
CONVERSION_TIMEOUT = 60
HEARTBEAT_INTERVAL = 2
INSTALLED_REFRESH_INTERVAL = 300
SERVED_SECRET_BYTES = 32


def support_dir() -> Path:
    return Path.home() / "Library/Application Support/halfbold/browser"


def extension_dir() -> Path:
    return support_dir() / "extension"


def served_fonts_dir() -> Path:
    return extension_dir() / "fonts"


def served_secret_path() -> Path:
    return support_dir() / "served.key"


def read_served_secret() -> bytes | None:
    try:
        secret = served_secret_path().read_bytes()
    except FileNotFoundError:
        return None
    return secret if len(secret) == SERVED_SECRET_BYTES else None


@contextmanager
def served_secret_lock():
    support_dir().mkdir(parents=True, exist_ok=True)
    with (support_dir() / "served.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def clear_served_fonts() -> None:
    if served_fonts_dir().exists():
        shutil.rmtree(served_fonts_dir())
    served_fonts_dir().mkdir(parents=True)


def publish_served_secret() -> bytes:
    clear_served_fonts()
    secret = secrets.token_bytes(SERVED_SECRET_BYTES)
    descriptor, partial = tempfile.mkstemp(dir=support_dir())
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(secret)
        os.replace(partial, served_secret_path())
    finally:
        Path(partial).unlink(missing_ok=True)
    return secret


def served_secret() -> bytes:
    if (secret := read_served_secret()) is not None:
        return secret
    with served_secret_lock():
        if (secret := read_served_secret()) is not None:
            return secret
        return publish_served_secret()


def user_fonts_dir() -> Path:
    return Path.home() / "Library/Fonts"


def extension_id(manifest: dict) -> str:
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    return digest.translate(str.maketrans("0123456789abcdef", "abcdefghijklmnop"))


def read_enabled() -> bool:
    try:
        return bool(json.loads((support_dir() / "config.json").read_text())["enabled"])
    except OSError, ValueError, KeyError, TypeError:
        return True


def write_enabled(enabled: bool) -> None:
    root = support_dir()
    root.mkdir(parents=True, exist_ok=True)
    partial = root / f"config-{os.getpid()}.tmp"
    partial.write_text(json.dumps({"enabled": enabled}))
    partial.replace(root / "config.json")


def generation(enabled: bool, settings: Settings, secret: bytes) -> str:
    digest = hashlib.sha256(f"{enabled}:{settings.cache_tag()}".encode())
    digest.update(secret)
    return digest.hexdigest()


def current_generation() -> str | None:
    secret = read_served_secret()
    if secret is None:
        return None
    return generation(read_enabled(), load_settings(), secret)


def status_acknowledges_current(status: dict) -> bool:
    current = current_generation()
    return current is not None and status.get("generation") == current


def browser_status() -> dict:
    try:
        status = json.loads((support_dir() / "status.json").read_text())
        connected = 0 <= time.time() - status["time"] < 6
    except OSError, ValueError, KeyError, TypeError:
        status, connected = {}, False
    return {
        "configured": (extension_dir() / "manifest.json").exists(),
        "connected": connected,
        "synced": connected and status_acknowledges_current(status),
        "enabled": read_enabled(),
        "converted": status.get("converted", 0) if connected else 0,
        "unchanged": status.get("unchanged", 0) if connected else 0,
        "extension_dir": str(extension_dir()),
    }


def copy_extension(source: Path) -> None:
    extension = extension_dir()
    extension.mkdir(parents=True, exist_ok=True)
    for name in EXTENSION_FILES:
        shutil.copy2(source / name, extension / name)
    for name in RETIRED_EXTENSION_FILES:
        (extension / name).unlink(missing_ok=True)
    served_fonts_dir().mkdir(exist_ok=True)


def write_launcher() -> Path:
    launcher = support_dir() / "host"
    command = (sys.executable, "-m", "halfbold.browser")
    launcher.write_text("#!/bin/sh\nexec " + shlex.join(command) + "\n")
    launcher.chmod(0o700)
    (support_dir() / "host.py").unlink(missing_ok=True)
    return launcher


def register_host(launcher: Path) -> None:
    manifest = json.loads((extension_dir() / "manifest.json").read_text())
    host_dir = (
        Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts"
    )
    host_dir.mkdir(parents=True, exist_ok=True)
    (host_dir / f"{HOST}.json").write_text(
        json.dumps(
            {
                "name": HOST,
                "description": "halfbold page font conversion",
                "path": str(launcher),
                "type": "stdio",
                "allowed_origins": [f"chrome-extension://{extension_id(manifest)}/"],
            }
        )
    )


def open_chrome_extensions() -> None:
    subprocess.run(["pbcopy"], input=str(extension_dir()), text=True, check=True)
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


def setup_browser(*, open_chrome: bool = True, source: Path = EXTENSION_SOURCE) -> dict:
    copy_extension(source)
    served_secret()
    register_host(write_launcher())
    write_enabled(True)
    if open_chrome:
        open_chrome_extensions()
    return browser_status()


def disable_browser(delete_served_fonts: bool = False) -> None:
    write_enabled(False)
    if delete_served_fonts:
        shutil.rmtree(served_fonts_dir(), ignore_errors=True)


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
    if size > MAX_MESSAGE_SIZE:
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


class InstalledFonts:
    def __init__(self) -> None:
        self.loaded_at = float("-inf")
        self.cached: list[Path] = []

    def paths(self) -> list[Path]:
        if time.monotonic() - self.loaded_at > INSTALLED_REFRESH_INTERVAL:
            self.cached = installed_face_paths(user_fonts_dir())
            self.loaded_at = time.monotonic()
        return self.cached


def web_face(entry: dict) -> WebFace:
    low, high = entry["weight"]
    return WebFace(
        weight=(float(low), float(high)),
        data=base64.b64decode(entry["data"], validate=True),
        style=str(entry.get("style", "normal")),
        unicode_range=str(entry.get("unicodeRange", "")),
    )


def handle_request(
    message: dict, settings: Settings, installed: InstalledFonts
) -> dict:
    kind = message["type"]
    if kind == "convert-webfont":
        faces = [web_face(entry) for entry in message["faces"]]
        conversion = convert_webfont_family(
            faces, served_fonts_dir(), settings, served_secret()
        )
        return {"type": "converted", **conversion.as_dict()}
    if kind == "convert-installed":
        conversion = convert_installed_family(
            str(message["family"]),
            installed.paths(),
            served_fonts_dir(),
            settings,
            served_secret(),
        )
        return {"type": "converted", **conversion.as_dict()}
    if kind == "defaults":
        families = {str(k): str(v) for k, v in dict(message["families"]).items()}
        installed_families = prepare_default_fonts(
            families, installed.paths(), user_fonts_dir(), settings
        )
        return {"type": "defaults", "families": installed_families}
    raise ValueError(f"unknown request {kind!r}")


def safe_reply(message: dict, settings: Settings, installed: InstalledFonts) -> dict:
    try:
        reply = handle_request(message, settings, installed)
    except Exception as error:
        reply = {"type": "unchanged", "reason": str(error)}
    return {**reply, "id": message["id"]}


def write_status(message: dict, acknowledged: str | None) -> None:
    root = support_dir()
    status_path = root / f"status-{os.getpid()}.tmp"
    status_path.write_text(
        json.dumps(
            {
                "time": time.time(),
                "generation": acknowledged,
                "converted": int(message.get("converted", 0)),
                "unchanged": int(message.get("unchanged", 0)),
            }
        )
    )
    status_path.replace(root / "status.json")


def timed_out_replies(pending: dict[Future, tuple[object, float]]) -> list[dict]:
    now = time.monotonic()
    expired = [
        f for f, (_, started) in pending.items() if now - started > CONVERSION_TIMEOUT
    ]
    replies = []
    for future in expired:
        request_id, _ = pending.pop(future)
        replies.append({"type": "unchanged", "id": request_id, "reason": "timed out"})
    return replies


def serve(stdin, stdout, pool: ThreadPoolExecutor) -> None:
    installed = InstalledFonts()
    pending: dict[Future, tuple[object, float]] = {}
    sent_generation = None
    acknowledged = None
    last_heartbeat = float("-inf")
    while True:
        enabled = read_enabled()
        settings = load_settings()
        current = generation(enabled, settings, served_secret())
        if current != sent_generation:
            write_message(
                stdout, {"type": "config", "enabled": enabled, "generation": current}
            )
            sent_generation = current
        for future in [f for f in pending if f.done()]:
            pending.pop(future)
            write_message(stdout, future.result())
        for reply in timed_out_replies(pending):
            write_message(stdout, reply)
        now = time.monotonic()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            write_message(stdout, {"ping": True})
            last_heartbeat = now
        readable, _, _ = select.select([stdin], [], [], 0.15)
        if not readable:
            continue
        message = read_message(stdin)
        if message is None:
            return
        if message.get("pong"):
            if message.get("generation") == current:
                acknowledged = current
            write_status(message, acknowledged)
        elif "id" in message and "type" in message:
            future = pool.submit(safe_reply, message, settings, installed)
            pending[future] = (message["id"], time.monotonic())


def native_host(stdin=None, stdout=None) -> None:
    support_dir().mkdir(parents=True, exist_ok=True)
    pool = ThreadPoolExecutor(max_workers=2)
    try:
        serve(stdin or sys.stdin.buffer.raw, stdout or sys.stdout.buffer, pool)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    try:
        native_host()
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
