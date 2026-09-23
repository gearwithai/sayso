"""Turns a transcript into an action. Pure logic, no OS calls - easy to test."""
import re
from dataclasses import dataclass

# Whisper often hears short commands with filler punctuation or case.
_TRIM = " .,!?;:\"'"


@dataclass(frozen=True)
class Action:
    # type, type_send, send, newline, undo, stop, switch, snippet, custom, nothing
    kind: str
    text: str = ""


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(_TRIM)


def norm(s: str) -> str:
    """How phrases are compared: lower case, letters/digits/spaces only."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def parse(transcript: str, send_word: str = "send", allow_commands: bool = True,
          snippets: dict | None = None, custom: list | None = None) -> Action:
    raw = re.sub(r"\s+", " ", transcript).strip()
    text = _clean(raw)
    if not text:
        return Action("nothing")
    # keep what Whisper punctuated ("How are you?") - only drop leading junk
    typed = raw.lstrip(_TRIM)
    if not allow_commands:
        return Action("type", typed)

    low = norm(text)
    sw = norm(send_word)

    if low in (sw, f"{sw} it", "hit enter", "press enter", "enter"):
        return Action("send")
    if low in ("new line", "newline", "next line"):
        return Action("newline")
    if low in ("undo", "undo that", "scratch that", "delete that"):
        return Action("undo")
    if low in ("stop listening", "go to sleep", "pause sayso"):
        return Action("stop")

    # your own voice commands (commands.json) - exact phrase
    for phrase in custom or []:
        if norm(phrase) == low:
            return Action("custom", phrase)

    # "insert my email" -> saved snippet
    m = re.match(r"^(?:insert|paste|type out)\s+(?:my\s+|the\s+)?(.+)$", low)
    if m and snippets:
        want = m.group(1)
        for name, value in snippets.items():
            n = norm(name)
            if want in (n, f"my {n}", f"the {n}") or n == want.removeprefix("my ").removeprefix("the "):
                return Action("snippet", value)
        # no such snippet: it was probably just dictation ("insert a table here") - type it

    m = re.match(r"^(?:open|switch to|go to)\s+(.+)$", low)
    if m:
        return Action("switch", _clean(m.group(1)))

    # "...and run the tests, send" -> type the body, then press Enter
    if sw:
        m = re.match(rf"^(.*\S)[\s,.;:!?]+{re.escape(send_word.strip())}[\s.!]*$", raw, flags=re.IGNORECASE)
        if m:
            body = m.group(1).lstrip(_TRIM).rstrip(" ,.;:")
            if body:
                return Action("type_send", body)

    return Action("type", typed)
