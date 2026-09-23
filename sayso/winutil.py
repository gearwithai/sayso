"""Small Windows helpers: single instance, start with Windows, beeps."""
import ctypes
import sys
import threading
import winreg

from sayso import APP_NAME

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_mutex = None


def already_running() -> bool:
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}SingleInstance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def launch_command() -> str:
    if getattr(sys, "frozen", False):  # packaged Sayso.exe
        return f'"{sys.executable}"'
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{pyw}" -m sayso'


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def beep(high: bool = True) -> None:
    import winsound
    threading.Thread(target=winsound.Beep, args=(1200 if high else 700, 80), daemon=True).start()


def message(title: str, text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)


# ---------------- API keys are stored encrypted with Windows DPAPI (only this Windows user can read them)

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def protect(secret: str) -> str:
    import base64
    if not secret:
        return ""
    data = secret.encode("utf-8")
    inp = _BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out)):
        raise OSError("couldn't encrypt the key")
    try:
        return base64.b64encode(ctypes.string_at(out.pbData, out.cbData)).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def unprotect(blob: str) -> str:
    import base64
    if not blob:
        return ""
    data = base64.b64decode(blob)
    inp = _BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out)):
        return ""
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)
