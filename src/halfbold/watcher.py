import os
import subprocess
from pathlib import Path

LABEL = "com.jorden.halfbold"


def default_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def remove_watcher(plist: Path) -> bool:
    if not plist.exists():
        return False
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
        capture_output=True,
        check=False,
    )
    plist.unlink()
    return True
