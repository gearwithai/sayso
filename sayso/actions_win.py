"""Windows side effects: paste text, press keys, switch to / open apps."""
import ctypes
import subprocess
import time
import webbrowser
from ctypes import wintypes

import pyperclip
from pynput.keyboard import Controller, Key

from sayso import apps as apps_mod
from sayso.commands import Action
from sayso.custom import parse_keys

kb = Controller()
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002
SW_RESTORE = 9


def _tap(key, *mods):
    for m in mods:
        kb.press(m)
    kb.press(key)
    kb.release(key)
    for m in reversed(mods):
        kb.release(m)


def paste(text: str) -> None:
    """Paste via the clipboard - instant and handles any characters. Restores the old clipboard text."""
    try:
        old = pyperclip.paste()
    except Exception:
        old = None
    pyperclip.copy(text)
    time.sleep(0.03)
    _tap("v", Key.ctrl)
    time.sleep(0.2)  # let the target app read the clipboard before restoring
    if old is not None:
        try:
            pyperclip.copy(old)
        except Exception:
            pass


_SENTINEL = "\u2063sayso-no-selection\u2063"


def copy_selection(wait: float = 0.45) -> str:
    """Ctrl+C the selected text and give it back, leaving the clipboard as it was. "" if nothing is selected."""
    try:
        old = pyperclip.paste()
    except Exception:
        old = None
    try:
        pyperclip.copy(_SENTINEL)
    except Exception:
        return ""
    _tap("c", Key.ctrl)
    got = ""
    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.04)
        try:
            cur = pyperclip.paste()
        except Exception:
            continue
        if cur != _SENTINEL:
            got = cur
            break
    try:
        pyperclip.copy(old if old is not None else "")
    except Exception:
        pass
    return got.strip()


def select_back(chars: int) -> None:
    """Select the last `chars` characters before the cursor (Shift+Left), so a paste replaces them."""
    kb.press(Key.shift)
    try:
        for _ in range(min(chars, 4000)):
            kb.press(Key.left)
            kb.release(Key.left)
    finally:
        kb.release(Key.shift)


def collapse_selection() -> None:
    _tap(Key.right)


def foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow() or 0)


def _window_exe(hwnd) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        return buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) else ""
    finally:
        kernel32.CloseHandle(h)


def _windows():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def _focus(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Windows only lets the foreground app change focus; a synthetic Alt tap unlocks it.
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def switch_to(spoken: str, app_list: list) -> str:
    app = apps_mod.find_app(app_list, spoken)
    if app:
        for hwnd, title in _windows():
            if apps_mod.match_foreground([app], _window_exe(hwnd), title):
                _focus(hwnd)
                return f"Switched to {app.name}"
        apps_mod.launch(app)
        return f"Opening {app.name}"
    # Not an installed app we know - try any open window with that name
    for hwnd, title in _windows():
        if spoken.lower() in title.lower():
            _focus(hwnd)
            return f"Switched to {title}"
    return f"Couldn't find an app called {spoken}"


KEYMAP = {
    "ctrl": Key.ctrl, "shift": Key.shift, "alt": Key.alt, "win": Key.cmd,
    "enter": Key.enter, "return": Key.enter, "tab": Key.tab, "esc": Key.esc, "escape": Key.esc,
    "space": Key.space, "backspace": Key.backspace, "delete": Key.delete, "del": Key.delete,
    "home": Key.home, "end": Key.end, "pageup": Key.page_up, "pagedown": Key.page_down,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "insert": Key.insert, "printscreen": Key.print_screen, "capslock": Key.caps_lock,
    "volumeup": Key.media_volume_up, "volumedown": Key.media_volume_down, "mute": Key.media_volume_mute,
    "playpause": Key.media_play_pause, "nexttrack": Key.media_next, "prevtrack": Key.media_previous,
}


def _key(name: str):
    if name in KEYMAP:
        return KEYMAP[name]
    if name.startswith("f") and name[1:].isdigit():
        return getattr(Key, name)
    return name  # a single character


def press_combo(spec: str) -> None:
    mods, key = parse_keys(spec)
    _tap(_key(key), *[_key(m) for m in mods])


def run_custom(entry: dict) -> str:
    say = entry["say"]
    if "keys" in entry:
        for spec in entry["keys"] if isinstance(entry["keys"], list) else [entry["keys"]]:
            press_combo(str(spec))
            time.sleep(0.05)
    elif "type" in entry:
        paste(str(entry["type"]))
    elif "url" in entry:
        webbrowser.open(str(entry["url"]))
    elif "run" in entry:
        subprocess.Popen(["cmd", "/c", "start", "", str(entry["run"])], creationflags=0x08000000)
    return f"Done: {say}"


def perform(action: Action, app_list: list, custom: dict | None = None) -> str:
    k = action.kind
    if k == "type":
        paste(action.text + " ")
        return f"Typed: {action.text}"
    if k == "type_send":
        paste(action.text)
        time.sleep(0.1)
        _tap(Key.enter)
        return f"Sent: {action.text}"
    if k == "send":
        _tap(Key.enter)
        return "Pressed Enter"
    if k == "newline":
        _tap(Key.enter, Key.shift)  # Shift+Enter = new line in chat boxes, normal newline elsewhere
        return "New line"
    if k == "undo":
        _tap("z", Key.ctrl)
        return "Undo"
    if k == "switch":
        return switch_to(action.text, app_list)
    if k == "snippet":
        paste(action.text)
        return "Inserted snippet"
    if k == "custom":
        entry = (custom or {}).get(action.text)
        return run_custom(entry) if entry else f"No command called {action.text}"
    return ""
