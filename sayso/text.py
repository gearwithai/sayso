"""Makes dictated text read like typed text.

- drops filler sounds ("um", "uh")
- spoken punctuation: "comma", "question mark", "new line", "new paragraph", ...
- your own words: replacements ("gear with ai" -> "GearWithAI")
- capital letter at the start
"""
import re

FILLERS = re.compile(r"(?i)(?<![\w'])(?:u+m+|u+h+|e+r+m+|u+h+m+|h+m+|a+h+)(?![\w'])[,.]?\s*")

# spoken -> written; applied only when said as separate words
SPOKEN = [
    (r"new paragraph", "\n\n"),
    (r"new line", "\n"),
    (r"question mark", "?"),
    (r"exclamation (?:mark|point)", "!"),
    (r"full stop", "."),
    (r"semicolon", ";"),
    (r"colon", ":"),
    (r"comma", ","),
    (r"open quote", '"'),
    (r"close quote", '"'),
]
_SPOKEN_RE = [(re.compile(rf"(?i)[ \t]*\b{p}\b[\s,.]*" if rep.startswith("\n") else rf"(?i)[\s,.]*\b{p}\b[\s,.]*"), rep)
              for p, rep in SPOKEN]
# "period" is also a normal word ("a period of time") - only treat it as "." at the end
_PERIOD_END = re.compile(r"(?i)[\s,]*\bperiod\b[\s.]*$")


def _spoken_punctuation(t: str) -> str:
    for rx, rep in _SPOKEN_RE:
        if rep in ("\n", "\n\n"):
            t = rx.sub(rep, t)
        elif rep == '"':
            t = rx.sub(' "' if "open" in rx.pattern else '" ', t)
        else:
            t = rx.sub(rep + " ", t)
    t = _PERIOD_END.sub(".", t)
    t = re.sub(r"\s+([,.;:?!])", r"\1", t)          # no space before punctuation
    t = re.sub(r"([,.;:?!])\1+", r"\1", t)           # ",," -> ","
    t = re.sub(r"[,;:]([.?!])", r"\1", t)            # ",." -> "."
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip(" ")


def _replacements(t: str, words: dict) -> str:
    # longest first so "gear with ai pro" wins over "gear with ai"
    for said in sorted(words, key=len, reverse=True):
        typed = words[said]
        if said.strip():
            t = re.sub(rf"(?i)(?<![\w]){re.escape(said.strip())}(?![\w])", lambda _: typed, t)
    return t


def _capitalize(t: str) -> str:
    t = re.sub(r"^(\W*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    # after . ? ! or a new line
    return re.sub(r"([.?!]\s+|\n+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)


def clean(text: str, replacements: dict | None = None, cleanup: bool = True) -> str:
    t = text.strip()
    if cleanup:
        t = FILLERS.sub("", t)
        t = _spoken_punctuation(t)
    if replacements:
        t = _replacements(t, replacements)
    if cleanup:
        t = re.sub(r"^[\s,.;:]+", "", t)
        t = _capitalize(t)
    return t.strip(" ")
