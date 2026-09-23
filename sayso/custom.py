"""Your own voice commands, from %APPDATA%\\Sayso\\commands.json.

Each entry: a phrase to say after "Sayso", and one thing to do:

  {"say": "new tab",      "keys": "ctrl+t"}                 press keys
  {"say": "sign off",     "type": "Thanks,\\nSunny"}          type text
  {"say": "open my crm",  "url":  "https://app.example.com"} open a web page
  {"say": "start music",  "run":  "spotify"}                 start a program / file
  {"say": "clean up",     "keys": ["ctrl+a", "delete"]}      several key presses in a row

Edit the file, save it, and Sayso picks it up - no restart needed.
"""
import json
import logging
import os

from sayso.config import data_dir

log = logging.getLogger("sayso.custom")
PATH = data_dir() / "commands.json"
ACTIONS = ("keys", "type", "url", "run")

MODIFIERS = {"ctrl", "control", "shift", "alt", "win", "cmd"}
NAMED_KEYS = {
    "enter", "return", "tab", "esc", "escape", "space", "backspace", "delete", "del", "home", "end",
    "pageup", "pagedown", "up", "down", "left", "right", "insert", "printscreen", "capslock",
    *(f"f{i}" for i in range(1, 25)),
    "volumeup", "volumedown", "mute", "playpause", "nexttrack", "prevtrack",
}

EXAMPLE = {
    "_help": "Say 'Sayso, <say>' to run a command. Actions: keys, type, url, run. "
             "Docs: https://github.com/gearwithai/sayso#your-own-voice-commands",
    "commands": [
        {"say": "new tab", "keys": "ctrl+t"},
        {"say": "close tab", "keys": "ctrl+w"},
        {"say": "select all", "keys": "ctrl+a"},
        {"say": "copy that", "keys": "ctrl+c"},
        {"say": "paste that", "keys": "ctrl+v"},
        {"say": "save file", "keys": "ctrl+s"},
        {"say": "show desktop", "keys": "win+d"},
        {"say": "next song", "keys": "nexttrack"},
        {"say": "search google", "url": "https://www.google.com"},
    ],
}


def parse_keys(spec: str) -> tuple[list[str], str]:
    """'ctrl+shift+t' -> (['ctrl', 'shift'], 't'). Raises ValueError on nonsense."""
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("empty key combination")
    *mods, key = parts
    for m in mods:
        if m not in MODIFIERS:
            raise ValueError(f"'{m}' isn't a modifier (use ctrl, shift, alt, win)")
    if not (len(key) == 1 or key in NAMED_KEYS or key in MODIFIERS):
        raise ValueError(f"unknown key '{key}'")
    mods = ["ctrl" if m == "control" else "win" if m == "cmd" else m for m in mods]
    return mods, key


def validate(entry: dict) -> str | None:
    """Returns a problem description, or None if the entry is fine."""
    if not isinstance(entry, dict) or not str(entry.get("say", "")).strip():
        return "every command needs a \"say\" phrase"
    acts = [a for a in ACTIONS if a in entry]
    if len(acts) != 1:
        return f"\"{entry.get('say')}\" needs exactly one of: keys, type, url, run"
    if "keys" in entry:
        seq = entry["keys"] if isinstance(entry["keys"], list) else [entry["keys"]]
        try:
            for k in seq:
                parse_keys(str(k))
        except ValueError as e:
            return f"\"{entry['say']}\": {e}"
    return None


def load_from(data) -> tuple[dict, list[str]]:
    """-> ({phrase: entry}, [problems])"""
    items = data.get("commands", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    good, problems = {}, []
    for e in items:
        p = validate(e)
        if p:
            problems.append(p)
        else:
            good[str(e["say"]).strip()] = e
    return good, problems


class CustomCommands:
    """Reloads commands.json whenever it changes on disk."""

    def __init__(self):
        self._mtime = None
        self.commands: dict = {}
        self.problems: list[str] = []
        if not PATH.exists():
            PATH.write_text(json.dumps(EXAMPLE, indent=2), encoding="utf-8")

    def get(self) -> dict:
        try:
            m = PATH.stat().st_mtime
        except FileNotFoundError:
            self.commands, self.problems = {}, []
            return self.commands
        if m != self._mtime:
            self._mtime = m
            try:
                self.commands, self.problems = load_from(json.loads(PATH.read_text(encoding="utf-8")))
            except ValueError as e:
                self.commands, self.problems = {}, [f"commands.json isn't valid JSON: {e}"]
            for p in self.problems:
                log.warning("commands.json: %s", p)
        return self.commands

    def open_file(self):
        os.startfile(PATH)
