"""AI voice actions: "Sayso, make that more professional", "Sayso, translate this to Spanish",
"Sayso, write a reply saying I'll be there at 5".

Works with a model on your own PC (Ollama or LM Studio - free and private) or your own API key
(OpenAI, Anthropic, Groq, or any OpenAI-compatible server). Off until you pick one.
"""
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

PROVIDERS = {
    # label shown in Settings -> (id, default base url, needs key, default model)
    "Off": ("off", "", False, ""),
    "Ollama (on this PC, free)": ("ollama", "http://localhost:11434", False, ""),
    "LM Studio (on this PC, free)": ("lmstudio", "http://localhost:1234/v1", False, ""),
    "OpenAI (your key)": ("openai", "https://api.openai.com/v1", True, "gpt-4o-mini"),
    "Anthropic Claude (your key)": ("anthropic", "https://api.anthropic.com/v1", True, "claude-haiku-4-5"),
    "Groq (your key, very fast)": ("groq", "https://api.groq.com/openai/v1", True, "llama-3.3-70b-versatile"),
    "Other OpenAI-compatible": ("custom", "", True, ""),
}
BY_ID = {v[0]: (label, *v[1:]) for label, v in PROVIDERS.items()}
OPENAI_STYLE = {"lmstudio", "openai", "groq", "custom"}

SYSTEM = ("You are the writing assistant inside Sayso, a voice typing app. The user dictates an instruction. "
          "Reply with ONLY the finished text to be typed - no preamble, no explanations, no quotes around it, "
          "no markdown unless the text needs it. Keep the language of the original text unless asked to translate.")


class AIError(Exception):
    pass


# ---------------------------------------------------------------- intent parsing (pure)

@dataclass(frozen=True)
class Intent:
    op: str            # "edit" (changes selected / last text) or "write" (new text at the cursor)
    instruction: str   # what to do, in plain words


_EDIT = [
    r"(?:re ?write|rephrase|reword)\b.*",
    r"make (?:this|that|it)\b.+",
    r"fix (?:the |my )?(?:grammar|spelling|typos|punctuation)\b.*",
    r"(?:proof ?read|clean up|tidy up|polish|improve) (?:this|that|it)\b.*",
    r"translate (?:this |that |it )?(?:in)?to .+",
    r"summari[sz]e (?:this|that|it)\b.*",
    r"(?:shorten|expand|simplify) (?:this|that|it)\b.*",
    r"turn (?:this|that|it) into .+",
    r"(?:put|convert) (?:this|that|it) (?:in|into|as) .+",
]
_WRITE = [
    r"(?:write|draft|compose)\s+(?:me\s+)?(?:a|an|the|some|my)\b.+",
    r"(?:write|draft|compose)\s+.+",
    r"reply (?:saying|that|with|to say|and say)\b.+",
    r"(?:ask ai|ask claude|ask gpt|ask chat ?gpt)\b.+",
]
_EDIT_RE = [re.compile(rf"^{p}$") for p in _EDIT]
_WRITE_RE = [re.compile(rf"^{p}$") for p in _WRITE]


def parse_intent(low: str) -> Intent | None:
    """`low` is the normalized transcript after the wake word (lower case, no punctuation)."""
    low = low.strip()
    if not low:
        return None
    if any(r.match(low) for r in _EDIT_RE):
        return Intent("edit", low)
    if any(r.match(low) for r in _WRITE_RE):
        instr = re.sub(r"^ask (?:ai|claude|gpt|chat ?gpt)\s*", "", low)
        return Intent("write", instr)
    return None


def build_prompt(intent: Intent, text: str | None) -> str:
    if intent.op == "edit":
        return f"Instruction: {intent.instruction}\n\nText:\n{text}"
    if text:
        return f"Instruction: {intent.instruction}\n\nFor context, the selected text is:\n{text}"
    return f"Instruction: {intent.instruction}"


# ---------------------------------------------------------------- HTTP (pure builders + one sender)

def build_request(provider: str, base_url: str, model: str, key: str, system: str, user: str):
    base = base_url.rstrip("/")
    if provider == "ollama":
        return (f"{base}/api/chat", {"Content-Type": "application/json"},
                {"model": model, "stream": False, "options": {"temperature": 0.3},
                 "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    if provider == "anthropic":
        return (f"{base}/messages",
                {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"},
                {"model": model, "max_tokens": 1500, "temperature": 0.3, "system": system,
                 "messages": [{"role": "user", "content": user}]})
    if provider in OPENAI_STYLE:
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return (f"{base}/chat/completions", headers,
                {"model": model, "temperature": 0.3,
                 "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    raise AIError("AI is turned off. Pick a provider in Settings > AI.")


def parse_response(provider: str, data: dict) -> str:
    try:
        if provider == "ollama":
            text = data["message"]["content"]
        elif provider == "anthropic":
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        else:
            text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise AIError("The AI sent back something unexpected.")
    return tidy(text)


def tidy(text: str) -> str:
    """Strip the chatter models add despite instructions."""
    t = re.sub(r"(?s)<think>.*?</think>", "", text).strip()           # reasoning models
    lines = t.split("\n")
    first = lines[0].strip()
    if len(lines) > 1 and len(first) < 90 and (
            re.match(r"(?i)^(?:sure|okay|ok|certainly|of course|absolutely|here(?:'s| is| are))\b", first)
            or (first.endswith(":") and re.search(r"(?i)(here|rewrit|translat|version|summary|revised|improved)", first))):
        t = "\n".join(lines[1:]).strip()
    if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'“":
        t = t[1:-1]
    if t.startswith("“") and t.endswith("”"):
        t = t[1:-1]
    return t.strip()


def _http(url, headers, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read()).get("error", "")
            detail = detail.get("message", "") if isinstance(detail, dict) else str(detail)
        except Exception:
            pass
        if e.code in (401, 403):
            raise AIError("The API key was refused. Check it in Settings > AI.")
        raise AIError(f"AI error {e.code}: {detail or e.reason}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AIError(f"Couldn't reach the AI ({getattr(e, 'reason', e)}).")


class Brain:
    def __init__(self, provider: str, base_url: str, model: str, key: str = "", send=_http):
        self.provider, self.base_url, self.model, self.key, self._send = provider, base_url, model, key, send

    @property
    def ready(self) -> bool:
        return self.provider != "off" and bool(self.model) and (bool(self.key) or not BY_ID.get(self.provider, ("",) * 4)[2])

    def complete(self, user: str, system: str = SYSTEM, timeout: float = 60) -> str:
        if self.provider == "off":
            raise AIError("AI is off. Turn it on in Settings > AI (free options run on your PC).")
        if not self.model:
            raise AIError("Pick an AI model in Settings > AI.")
        url, headers, body = build_request(self.provider, self.base_url, self.model, self.key, system, user)
        return parse_response(self.provider, self._send(url, headers, body, timeout))


# ---------------------------------------------------------------- local model discovery

PREFERRED = ("llama3.2", "llama3.1", "qwen2.5", "qwen3", "gemma3", "gemma2", "mistral", "phi4", "phi3", "llama3")


def pick_model(names: list[str]) -> str:
    """Prefer small, capable instruct models; skip embedding models."""
    names = [n for n in names if "embed" not in n.lower()]
    for pref in PREFERRED:
        for n in names:
            if n.lower().startswith(pref):
                return n
    return names[0] if names else ""


def list_models(provider: str, base_url: str, key: str = "", send=_http) -> list[str]:
    base = base_url.rstrip("/")
    if provider == "ollama":
        data = send(f"{base}/api/tags", {}, None, 3)
        return [m["name"] for m in data.get("models", [])]
    if provider in OPENAI_STYLE:
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        data = send(f"{base}/models", headers, None, 5)
        return [m["id"] for m in data.get("data", [])]
    return []


def detect_local(send=_http) -> tuple[str, str, str] | None:
    """-> (provider, base_url, model) for a local AI server that's running, else None."""
    for provider in ("ollama", "lmstudio"):
        base = BY_ID[provider][1]
        try:
            model = pick_model(list_models(provider, base, send=send))
        except Exception:
            continue
        if model:
            return provider, base, model
    return None


# ---------------------------------------------------------------- what text an AI action works on (pure)

def choose_source(op: str, selected: str, last_typed: str, last_is_fresh: bool):
    """-> (text for the AI, how to put the answer back) where "how" is one of
    "replace_selection", "replace_last", "insert", or an error message for the user."""
    if selected:
        return selected, ("replace_selection" if op == "edit" else "insert_after_selection")
    if op == "edit":
        if last_typed and last_is_fresh:
            return last_typed, "replace_last"
        return None, "Select the text first, then say it again."
    return None, "insert"


def resolve_config(provider: str, base_url: str, model: str):
    """Fill in defaults for a provider id. -> (provider, base_url, model)."""
    if provider not in BY_ID:
        return "off", "", ""
    _, default_base, _, default_model = BY_ID[provider]
    return provider, (base_url or default_base), (model or default_model)
