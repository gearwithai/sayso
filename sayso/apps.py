"""Installed apps: find them, let the user turn Sayso on/off per app, open them by voice.

The app list comes from the Start menu (PowerShell's Get-StartApps, plus shortcut targets so we
know each app's .exe). Every app has a stable AppID that Windows can launch with
`explorer shell:AppsFolder\\<AppID>`, for classic and Store apps alike.
"""
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher

from sayso.config import data_dir

log = logging.getLogger("sayso.apps")
CACHE = data_dir() / "apps.json"

JUNK_NAME = re.compile(r"\b(uninstall|uninstaller|readme|read me|release notes|documentation|help|"
                       r"manual|license|website|web site|support|changelog|what's new|safe mode)\b", re.I)
JUNK_TARGET = re.compile(r"\.(url|chm|txt|html?|pdf|rtf|md|msc|ini|log)$|^https?://", re.I)
UWP_HOST = "applicationframehost.exe"

PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$sh = New-Object -ComObject WScript.Shell
$dirs = @("$env:ProgramData\Microsoft\Windows\Start Menu\Programs", "$env:APPDATA\Microsoft\Windows\Start Menu\Programs")
$lnk = foreach ($d in $dirs) { Get-ChildItem $d -Recurse -Filter *.lnk | ForEach-Object {
  [pscustomobject]@{ n = $_.BaseName; t = $sh.CreateShortcut($_.FullName).TargetPath } } }
$start = Get-StartApps | ForEach-Object { [pscustomobject]@{ n = $_.Name; id = $_.AppID } }
[pscustomobject]@{ start = @($start); lnk = @($lnk) } | ConvertTo-Json -Depth 3 -Compress
"""


@dataclass
class App:
    id: str            # Windows AppID (launchable)
    name: str
    exe: str = ""      # lower-case .exe file name when known, e.g. "chrome.exe"

    @property
    def is_store_app(self) -> bool:
        return "!" in self.id


def _exe_name(path: str) -> str:
    path = (path or "").strip().strip('"')
    return os.path.basename(path.replace("/", "\\").split("\\")[-1]).lower() if path.lower().endswith(".exe") else ""


def build_list(start: list[dict], shortcuts: list[dict]) -> list[App]:
    """Merge Get-StartApps entries with shortcut targets; drop uninstallers, docs and links."""
    by_name = {}
    for s in shortcuts or []:
        name, target = (s.get("n") or "").strip(), (s.get("t") or "").strip()
        if name and target:
            by_name.setdefault(name.lower(), target)

    apps, seen = [], set()
    for s in start or []:
        name, app_id = (s.get("n") or "").strip(), (s.get("id") or "").strip()
        if not name or not app_id or name.lower() in seen:
            continue
        target = by_name.get(name.lower(), "")
        if JUNK_NAME.search(name) or JUNK_TARGET.search(app_id) or (target and JUNK_TARGET.search(target)):
            continue
        exe = _exe_name(target) or _exe_name(app_id)
        if exe.startswith("unins"):
            continue
        seen.add(name.lower())
        apps.append(App(id=app_id, name=name, exe=exe))
    apps.sort(key=lambda a: a.name.lower())
    return apps


def match_foreground(apps: list[App], exe_path: str, title: str) -> App | None:
    """Which listed app does the window in front belong to?"""
    exe = os.path.basename((exe_path or "").replace("/", "\\").split("\\")[-1]).lower()
    if exe and exe != UWP_HOST:
        hits = [a for a in apps if a.exe and a.exe == exe]
        if hits:
            # several shortcuts can share one exe (e.g. Office); prefer the one named in the title
            t = (title or "").lower()
            return next((a for a in hits if a.name.lower() in t), hits[0])
    t = (title or "").lower()
    if t:
        named = [a for a in apps if len(a.name) > 2 and a.name.lower() in t]
        if named:
            return max(named, key=lambda a: len(a.name))
    return None


ALIASES = {
    "vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
    "chrome": "google chrome", "edge": "microsoft edge", "terminal": "terminal",
    "word": "word", "excel": "excel", "outlook": "outlook", "powerpoint": "powerpoint",
    "file explorer": "file explorer", "explorer": "file explorer", "files": "file explorer",
    "calculator": "calculator", "settings": "settings",
}


def find_app(apps: list[App], spoken: str) -> App | None:
    """Fuzzy match 'open <spoken>' to an installed app."""
    q = ALIASES.get(spoken.lower().strip(), spoken.lower().strip())
    if not q:
        return None
    best, score = None, 0.0
    for a in apps:
        n = a.name.lower()
        if n == q:
            return a
        s = SequenceMatcher(None, q, n).ratio()
        if q in n.split() or n.startswith(q):
            s = max(s, 0.9 - 0.01 * (len(n) - len(q)))  # 'chrome' -> 'Google Chrome'
        elif q in n:
            s = max(s, 0.8)
        if s > score:
            best, score = a, s
    return best if score >= 0.7 else None


# ---------------- Windows side ----------------

def scan() -> list[App]:
    """Reads the Start menu (~1-3 s). Falls back to the last saved list."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", PS_SCRIPT],
            capture_output=True, timeout=60, creationflags=0x08000000)
        data = json.loads(out.stdout.decode("utf-8", "replace") or "{}")
        start, lnk = data.get("start") or [], data.get("lnk") or []
        if isinstance(start, dict):
            start = [start]
        if isinstance(lnk, dict):
            lnk = [lnk]
        apps = build_list(start, lnk)
        if apps:
            CACHE.write_text(json.dumps([asdict(a) for a in apps]), encoding="utf-8")
            return apps
    except Exception:
        log.exception("app scan failed")
    return load_cached()


def load_cached() -> list[App]:
    try:
        return [App(**a) for a in json.loads(CACHE.read_text(encoding="utf-8"))]
    except Exception:
        return []


def foreground() -> tuple[str, str, int]:
    """(exe path, window title, hwnd) of the window in front."""
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        size = wintypes.DWORD(1024)
        path = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, path, ctypes.byref(size)):
            exe = path.value
        kernel32.CloseHandle(h)
    return exe, buf.value, hwnd


def launch(app: App) -> None:
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app.id}"], creationflags=0x08000000)
