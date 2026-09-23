"""Free trial + license keys, backed by the Sayso cloud API (Supabase edge function).

- First launch registers this PC and gets a device token. No sign-up needed.
- Words typed are counted locally and reported in batches.
- Works offline: if the server can't be reached, Sayso keeps working and syncs later.
"""
import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from sayso import __version__
from sayso.config import data_dir

log = logging.getLogger("sayso.license")

API_URL = "https://laeitoulfslncjyolkpg.supabase.co/functions/v1/sayso-api"
BUY_URL = "https://gearwithai.com/sayso"  # checkout page - change once payments are live
ACCOUNT_PATH = data_dir() / "account.json"
SYNC_EVERY_SECS = 60
STATUS_EVERY_SECS = 600


class ApiError(Exception):
    pass


def machine_id() -> str:
    """Stable per-PC id so a reinstall keeps the same trial. Hashed - the raw id never leaves the PC."""
    raw = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            raw = winreg.QueryValueEx(k, "MachineGuid")[0]
    except Exception:
        import uuid
        raw = str(uuid.getnode())
    return hashlib.sha256(f"sayso:{raw}".encode()).hexdigest()


def _post(body: dict, token: str | None = None, timeout: float = 10) -> dict:
    data = json.dumps({**body, "version": __version__}).encode()
    req = urllib.request.Request(API_URL, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("x-sayso-token", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read())
        except Exception:
            payload = {}
        if payload.get("reregister"):
            raise ApiError("reregister")
        raise ApiError(payload.get("error") or f"Server error ({e.code})")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ConnectionError(str(e))


class License:
    def __init__(self, on_change=lambda: None, post=_post):
        self._post = post
        self.on_change = on_change
        self._lock = threading.Lock()
        self.token: str | None = None
        self.status: dict = {"plan": "trial", "allowed": True, "words_used": 0, "word_limit": 2000}
        self.unsynced = 0
        self.online = False
        self._load()

    # ---------- persistence ----------
    def _load(self):
        try:
            d = json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
            self.token = d.get("token")
            self.status = d.get("status") or self.status
            self.unsynced = int(d.get("unsynced", 0))
        except (FileNotFoundError, ValueError):
            pass

    def _save(self):
        ACCOUNT_PATH.write_text(json.dumps(
            {"token": self.token, "status": self.status, "unsynced": self.unsynced}), encoding="utf-8")

    # ---------- queries (called from the engine thread) ----------
    @property
    def is_pro(self) -> bool:
        return self.status.get("plan") == "pro"

    def words_left(self) -> int | None:
        if self.is_pro:
            return None
        limit = self.status.get("word_limit") or 2000
        return max(0, limit - int(self.status.get("words_used", 0)) - self.unsynced)

    def blocked_reason(self) -> str | None:
        if self.is_pro:
            return None
        if self.words_left() == 0:
            return "Your free words are used up - open Settings to get Sayso Pro."
        return None

    def summary(self) -> str:
        if self.is_pro:
            email = self.status.get("email")
            return "Sayso Pro - unlimited" + (f" ({email})" if email else "")
        used = int(self.status.get("words_used", 0)) + self.unsynced
        limit = self.status.get("word_limit") or 2000
        return f"Free trial - {min(used, limit):,} of {limit:,} words used"

    def add_words(self, n: int):
        with self._lock:
            self.unsynced += n
            self._save()
        self.on_change()

    # ---------- network ----------
    def _call(self, body: dict) -> dict:
        if not self.token:
            self._register()
        try:
            return self._post(body, self.token)
        except ApiError as e:
            if str(e) != "reregister":
                raise
            self.token = None
            self._register()
            return self._post(body, self.token)

    def _register(self):
        res = self._post({"action": "register", "machine": machine_id()})
        self.token = res.pop("token")
        self.status = res
        self._save()

    def sync(self) -> None:
        """Send unsynced words and refresh status. Raises ConnectionError when offline."""
        with self._lock:
            n = self.unsynced
        res = self._call({"action": "usage", "words": n} if n else {"action": "status"})
        with self._lock:
            self.unsynced -= n
            self.status = res
            self._save()
        self.online = True
        self.on_change()

    def activate(self, key: str) -> str:
        res = self._call({"action": "activate", "key": key.strip()})
        self.status = res
        self._save()
        self.on_change()
        return "Sayso Pro activated. Thank you!"

    def deactivate(self) -> None:
        self.status = self._call({"action": "deactivate"})
        self._save()
        self.on_change()

    def run_background_sync(self, stop: threading.Event):
        last_status = 0.0
        while not stop.is_set():
            due_status = time.time() - last_status > STATUS_EVERY_SECS
            if self.unsynced or due_status:
                try:
                    self.sync()
                    last_status = time.time()
                except ConnectionError as e:
                    self.online = False
                    log.info("offline, will retry: %s", e)
                except Exception:
                    log.exception("license sync failed")
            stop.wait(SYNC_EVERY_SECS)
