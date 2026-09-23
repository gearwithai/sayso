"""Settings, stored as JSON in %APPDATA%\\Sayso\\config.json."""
import json
import os
from dataclasses import dataclass, asdict, field, fields
from pathlib import Path

from sayso import APP_NAME


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = data_dir() / "config.json"

STT_MODELS = {
    "Fast (tiny)": "tiny.en",
    "Balanced (base)": "base.en",
    "Accurate (small)": "small.en",
}

PTT_KEYS = {
    "Right Ctrl": "ctrl_r",
    "Right Alt": "alt_r",
    "Right Shift": "shift_r",
    "F9": "f9",
    "Off": "",
}


@dataclass
class Config:
    hands_free: bool = True             # listen for the wake word
    wake_word: str = "Sayso"            # any word works - Whisper listens for it
    ptt_key: str = "ctrl_r"             # hold to dictate; "" = off
    stt_model: str = "base.en"
    mic_device: int | None = None       # None = Windows default mic
    silence_level: float = 0.015        # below this counts as silence
    silence_secs: float = 1.0           # pause length that ends a phrase
    max_secs: float = 45.0
    send_word: str = "send"             # "...fix the tests send" -> type + Enter
    beeps: bool = True
    launch_at_startup: bool = True
    first_run_done: bool = False
    disabled_apps: list = field(default_factory=list)   # AppIDs where Sayso stays quiet
    words_typed: int = 0                                 # shown on the home screen

    @classmethod
    def load(cls) -> "Config":
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(CONFIG_PATH)
