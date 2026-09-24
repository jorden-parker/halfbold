import os
import shutil
import subprocess
from pathlib import Path


def launch_desktop() -> int:
    repo = Path(
        os.environ.get("HALFBOLD_REPO", Path(__file__).resolve().parents[2])
    ).resolve()
    app = repo / "app"
    if not (app / "src-tauri" / "tauri.conf.json").is_file():
        print("Desktop sources not found. Set HALFBOLD_REPO to your halfbold checkout.")
        return 1
    env = os.environ.copy()
    env["HALFBOLD_REPO"] = str(repo)
    env["PATH"] = os.pathsep.join(
        [
            env.get("PATH", ""),
            str(Path.home() / ".cargo" / "bin"),
            str(Path.home() / ".bun" / "bin"),
            "/opt/homebrew/bin",
            "/opt/homebrew/opt/rustup/bin",
            "/usr/local/bin",
            "/usr/local/opt/rustup/bin",
        ]
    )
    for tool in ("bun", "cargo", "uv"):
        if shutil.which(tool, path=env["PATH"]) is None:
            print(f"Desktop needs {tool}. Install it, then run halfbold desktop again.")
            return 1
    try:
        installed = subprocess.run(["bun", "install"], cwd=app, env=env)
        if installed.returncode:
            return installed.returncode
        return subprocess.run(["bun", "tauri", "dev"], cwd=app, env=env).returncode
    except OSError as err:
        print(f"Could not launch desktop: {err}")
        return 1
    except KeyboardInterrupt:
        return 130
