from pathlib import Path

from halfbold import watcher
from halfbold.watcher import LABEL, remove_watcher


def test_remove_watcher_boots_out_and_deletes_the_plist(monkeypatch, tmp_path: Path):
    plist = tmp_path / f"{LABEL}.plist"
    plist.write_text("<plist/>")
    calls = []
    monkeypatch.setattr(watcher.subprocess, "run", lambda cmd, **_: calls.append(cmd))

    assert remove_watcher(plist) is True

    assert calls[0][:2] == ["launchctl", "bootout"]
    assert calls[0][2].endswith(f"/{LABEL}")
    assert not plist.exists()


def test_remove_watcher_without_plist_does_nothing(monkeypatch, tmp_path: Path):
    calls = []
    monkeypatch.setattr(watcher.subprocess, "run", lambda cmd, **_: calls.append(cmd))

    assert remove_watcher(tmp_path / f"{LABEL}.plist") is False
    assert calls == []
