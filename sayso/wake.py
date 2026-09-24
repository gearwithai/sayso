"""Spots the wake word ("Sayso" by default) at the start of a transcript.

Instead of a trained wake-word model we let Whisper transcribe the first couple of seconds of any
speech and check whether it starts with the wake word. That means any word can be the wake word,
and the user can say it and the command in one breath: "Sayso, open Chrome".
"""
import re
from difflib import SequenceMatcher

LEADING_FILLERS = {"hey", "hi", "ok", "okay", "yo", "oh", "uh", "um", "so"}


def _letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _close_enough(heard: str, target: str, score: float, threshold: float) -> bool:
    """A near-exact spelling always counts. A looser one ("Seso", "Saso") only counts when it is about
    the same length and ends the same way - so "Say hi", "Stay safe" or "Sadly so" don't wake Sayso."""
    if abs(len(heard) - len(target)) > 1:
        return False
    return score >= 0.8 or (score >= threshold and heard[-2:] == target[-2:])


def match(transcript: str, wake: str = "Sayso", threshold: float = 0.66):
    """Returns (matched, remainder). Remainder is what was said after the wake word."""
    target = _letters(wake)
    if not target:
        return False, transcript
    # keep original tokens (for the remainder) alongside their letters-only form
    tokens = re.findall(r"\S+", transcript.strip())
    start = 0
    while start < len(tokens) - 1 and _letters(tokens[start]) in LEADING_FILLERS \
            and _letters(tokens[start]) != target:
        start += 1
    # Whisper may split "Sayso" into "Say so" / "Say, so" - try joining up to 3 tokens
    best, best_n = 0.0, 0
    joined = ""
    # the wake word must be the first thing said ("I'd say so" doesn't count)
    if start >= len(tokens) or not _letters(tokens[start])[:1] == target[:1]:
        return False, transcript
    for n in range(1, min(3, len(tokens) - start) + 1):
        joined += _letters(tokens[start + n - 1])
        if not joined:
            continue
        score = SequenceMatcher(None, joined, target).ratio()
        if score > best:
            best, best_n = score, n
        if len(joined) > len(target) + 3:
            break
    if not _close_enough(_letters("".join(tokens[start:start + best_n])), target, best, threshold):
        return False, transcript
    rest = " ".join(tokens[start + best_n:])
    return True, rest.lstrip(" ,.;:!?-").strip()
