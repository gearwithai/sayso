"""Turns a transcript into an action. Pure logic, no OS calls - easy to test."""
import re
from dataclasses import dataclass

APP_ALIASES = {
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "PowerShell",
    "powershell": "PowerShell",
    "chrome": "Chrome",
    "google chrome": "Chrome",
    "edge": "Edge",
    "cursor": "Cursor",
    "claude": "Claude",
    "notepad": "Notepad",
    "outlook": "Outlook",
    "excel": "Excel",
    "word": "Word",
    "slack": "Slack",
}

# Whisper often hears short commands with filler punctuation or case.
_TRIM = " .,!?;:\"'"


@dataclass(frozen=True)
class Action:
    kind: str          # "type", "send", "type_send", "switch", "newline", "undo", "stop", "nothing"
    text: str = ""


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(_TRIM)


def parse(transcript: str, send_word: str = "send", allow_commands: bool = True) -> Action:
    text = _clean(transcript)
    if not text:
        return Action("nothing")
    if not allow_commands:
        return Action("type", text)

    low = text.lower()
    sw = send_word.lower().strip()

    if low in (sw, f"{sw} it", "hit enter", "press enter", "enter"):
        return Action("send")
    if low in ("new line", "newline", "next line"):
        return Action("newline")
    if low in ("undo", "undo that", "scratch that", "delete that"):
        return Action("undo")
    if low in ("stop listening", "go to sleep", "pause sayso"):
        return Action("stop")

    m = re.match(r"^(?:open|switch to|go to)\s+(.+)$", low)
    if m:
        target = _clean(m.group(1))
        return Action("switch", APP_ALIASES.get(target, target))

    # "...and run the tests, send" -> type the body, then press Enter
    m = re.match(rf"^(.*\S)[\s,.;:!?]+{re.escape(sw)}$", text, flags=re.IGNORECASE)
    if m and sw:
        body = _clean(m.group(1))
        if body:
            return Action("type_send", body)

    return Action("type", text)
