"""Windows side effects: paste text, press keys, switch to / open apps."""
import ctypes
import subprocess
import time
import webbrowser
from ctypes import wintypes

from pynput.keyboard import Controller, Key, KeyCode

from sayso import winclip

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


# Letter keys by virtual-key code, so Ctrl+V etc. work on any keyboard layout (Russian, Greek, Hindi...)
VK = {"a": KeyCode.from_vk(0x41), "c": KeyCode.from_vk(0x43), "v": KeyCode.from_vk(0x56), "z": KeyCode.from_vk(0x5A)}
PASTE_SETTLE_SECS = 0.45   # give slow apps (Electron, Office, remote desktop) time to read the clipboard


def paste(text: str) -> None:
    """Paste via the clipboard - instant and handles any characters. Everything that was on the
    clipboard before (text, images, files) is put back afterwards."""
    saved = winclip.snapshot()
    if not winclip.set_text(text):
        raise RuntimeError("the clipboard is busy - another app is holding it")
    time.sleep(0.03)
    _tap(VK["v"], Key.ctrl)
    time.sleep(PASTE_SETTLE_SECS)
    winclip.restore(saved)


def copy_selection(wait: float = 0.5) -> str:
    """Ctrl+C the selected text and give it back, leaving the clipboard as it was. "" if nothing is selected."""
    saved = winclip.snapshot()
    before = winclip.sequence()
    _tap(VK["c"], Key.ctrl)
    got = ""
    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.04)
        if winclip.sequence() != before:
            time.sleep(0.03)
            got = winclip.get_text()
            break
    if got:
        winclip.restore(saved)
    return got


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


def _elevated(pid: int) -> bool | None:
    """True if the process runs as administrator. None if we can't tell."""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)   # own instance: typed 64-bit handles
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD)]
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        tok = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(h, 0x0008, ctypes.byref(tok)):
            return ctypes.get_last_error() == 5  # access denied: it's elevated and we're not
        try:
            elev, size = wintypes.DWORD(), wintypes.DWORD()
            if not advapi32.GetTokenInformation(tok, 20, ctypes.byref(elev), 4, ctypes.byref(size)):
                return None
            return bool(elev.value)
        finally:
            k32.CloseHandle(tok)
    finally:
        k32.CloseHandle(h)


def foreground_is_admin() -> bool:
    """Windows won't let a normal app type into an app running as administrator."""
    import os
    if _elevated(os.getpid()):
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return bool(pid.value) and _elevated(pid.value) is True


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
        _tap(VK["z"], Key.ctrl)
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
