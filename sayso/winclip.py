"""The Windows clipboard, done properly.

Sayso types by pasting, so it borrows the clipboard for a moment. This module saves whatever was
there - text, images, copied files - and puts it all back afterwards, retries when another app is
holding the clipboard, and keeps dictated text out of Windows clipboard history (Win+V).
"""
import ctypes
import time
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.OpenClipboard.argtypes = [w.HWND]
user32.OpenClipboard.restype = w.BOOL
user32.CloseClipboard.restype = w.BOOL
user32.EmptyClipboard.restype = w.BOOL
user32.EnumClipboardFormats.argtypes = [w.UINT]
user32.EnumClipboardFormats.restype = w.UINT
user32.CountClipboardFormats.restype = ctypes.c_int
user32.GetClipboardData.argtypes = [w.UINT]
user32.GetClipboardData.restype = w.HANDLE
user32.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
user32.SetClipboardData.restype = w.HANDLE
user32.GetClipboardSequenceNumber.restype = w.DWORD
user32.RegisterClipboardFormatW.argtypes = [w.LPCWSTR]
user32.RegisterClipboardFormatW.restype = w.UINT
user32.GetClipboardFormatNameW.argtypes = [w.UINT, w.LPWSTR, ctypes.c_int]
user32.GetClipboardFormatNameW.restype = ctypes.c_int
kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = w.HGLOBAL
kernel32.GlobalLock.argtypes = [w.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [w.HGLOBAL]
kernel32.GlobalUnlock.restype = w.BOOL
kernel32.GlobalSize.argtypes = [w.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalFree.argtypes = [w.HGLOBAL]
kernel32.GlobalFree.restype = w.HGLOBAL

CF_UNICODETEXT = 13
CF_DIB, CF_DIBV5, CF_HDROP = 8, 17, 15
GMEM_MOVEABLE = 0x0002
# GDI / owner-drawn formats aren't memory blocks; Windows rebuilds CF_BITMAP from CF_DIB anyway
_NOT_MEMORY = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
_KEEP_NAMED = {"HTML Format", "Rich Text Format", "PNG", "FileGroupDescriptorW", "Shell IDList Array",
               "Preferred DropEffect"}
MAX_BYTES = 64 * 1024 * 1024


def _open(tries: int = 25) -> bool:
    for _ in range(tries):  # another app (or a clipboard manager) may be holding it for a moment
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def _name(fmt: int) -> str:
    buf = ctypes.create_unicode_buffer(128)
    return buf.value if user32.GetClipboardFormatNameW(fmt, buf, 128) else ""


def _read(fmt: int) -> bytes | None:
    h = user32.GetClipboardData(fmt)
    if not h:
        return None
    size = kernel32.GlobalSize(h)
    if not size or size > MAX_BYTES:
        return None
    p = kernel32.GlobalLock(h)
    if not p:
        return None
    try:
        return ctypes.string_at(p, size)
    finally:
        kernel32.GlobalUnlock(h)


def _alloc(data: bytes):
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    if not h:
        return None
    p = kernel32.GlobalLock(h)
    if not p:
        kernel32.GlobalFree(h)
        return None
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def _put(fmt: int, data: bytes) -> bool:
    h = _alloc(data)
    if h is None:
        return False
    if not user32.SetClipboardData(fmt, h):
        kernel32.GlobalFree(h)  # ownership only passes on success
        return False
    return True


def sequence() -> int:
    return int(user32.GetClipboardSequenceNumber())


def snapshot():
    """Everything on the clipboard as [(format, bytes)], or None if it couldn't be read."""
    if not _open():
        return None
    try:
        many = user32.CountClipboardFormats() > 12  # e.g. an Excel copy: only keep the useful formats
        saved, total, fmt = [], 0, 0
        while True:
            fmt = user32.EnumClipboardFormats(fmt)
            if not fmt:
                break
            if fmt in _NOT_MEMORY:
                continue
            if many and fmt not in (CF_UNICODETEXT, CF_DIB, CF_DIBV5, CF_HDROP) and _name(fmt) not in _KEEP_NAMED:
                continue
            data = _read(fmt)
            if data is None:
                continue
            total += len(data)
            if total > MAX_BYTES:
                break
            saved.append((fmt, data))
        return saved
    finally:
        user32.CloseClipboard()


def restore(saved) -> None:
    if saved is None or not _open():
        return
    try:
        user32.EmptyClipboard()
        for fmt, data in saved:
            _put(fmt, data)
    finally:
        user32.CloseClipboard()


def set_text(text: str, private: bool = True) -> bool:
    """Put text on the clipboard. private=True keeps it out of clipboard history and cloud sync."""
    if not _open():
        return False
    try:
        user32.EmptyClipboard()
        ok = _put(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        if private:
            for name in ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory",
                         "CanUploadToCloudClipboard"):
                fmt = user32.RegisterClipboardFormatW(name)
                _put(fmt, b"" if name.startswith("Exclude") else b"\0\0\0\0")
        return ok
    finally:
        user32.CloseClipboard()


def get_text() -> str:
    if not _open():
        return ""
    try:
        data = _read(CF_UNICODETEXT)
        if not data:
            return ""
        return data.decode("utf-16-le", errors="replace").split("\0", 1)[0]
    finally:
        user32.CloseClipboard()


def has_format(fmt: int) -> bool:
    user32.IsClipboardFormatAvailable.argtypes = [w.UINT]
    return bool(user32.IsClipboardFormatAvailable(fmt))
