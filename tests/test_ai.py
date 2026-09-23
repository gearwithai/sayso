import pytest

from sayso.ai import AIError, Brain, Intent, build_prompt, build_request, detect_local, parse_intent, parse_response, pick_model, tidy


@pytest.mark.parametrize("said,op", [
    ("make this more professional", "edit"),
    ("make that shorter", "edit"),
    ("make it sound friendlier", "edit"),
    ("rewrite this as a polite email", "edit"),
    ("rephrase that", "edit"),
    ("fix the grammar", "edit"),
    ("fix my spelling", "edit"),
    ("proofread this", "edit"),
    ("translate this to spanish", "edit"),
    ("translate into hindi", "edit"),
    ("summarize this in two lines", "edit"),
    ("turn this into bullet points", "edit"),
    ("write a reply saying i will be there at 5", "write"),
    ("draft an email to mike about the roof inspection", "write"),
    ("reply saying thanks and see you tomorrow", "write"),
    ("ask ai what is a good name for a roofing company", "write"),
])
def test_intents(said, op):
    assert parse_intent(said).op == op


@pytest.mark.parametrize("said", [
    "hello there", "make sure you call me", "the translation was fine", "i will write tomorrow",
    "fix the fence on monday", "",
])
def test_normal_speech_is_not_an_ai_command(said):
    assert parse_intent(said) is None


def test_ask_ai_strips_prefix():
    assert parse_intent("ask claude whats 2 plus 2").instruction == "whats 2 plus 2"


def test_prompts():
    assert "Text:\nhello" in build_prompt(Intent("edit", "fix grammar"), "hello")
    assert "selected text" in build_prompt(Intent("write", "reply"), "their message")
    assert build_prompt(Intent("write", "a poem"), None) == "Instruction: a poem"


def test_request_shapes():
    url, h, b = build_request("ollama", "http://localhost:11434/", "llama3.2", "", "sys", "hi")
    assert url == "http://localhost:11434/api/chat" and b["stream"] is False and b["messages"][0]["role"] == "system"
    url, h, b = build_request("anthropic", "https://api.anthropic.com/v1", "claude-haiku-4-5", "k", "sys", "hi")
    assert url.endswith("/messages") and h["x-api-key"] == "k" and b["system"] == "sys"
    url, h, b = build_request("openai", "https://api.openai.com/v1", "gpt-4o-mini", "k", "sys", "hi")
    assert url.endswith("/chat/completions") and h["Authorization"] == "Bearer k"
    url, h, b = build_request("lmstudio", "http://localhost:1234/v1", "m", "", "sys", "hi")
    assert "Authorization" not in h
    with pytest.raises(AIError):
        build_request("off", "", "", "", "s", "u")


def test_response_parsing():
    assert parse_response("ollama", {"message": {"content": "Hi!"}}) == "Hi!"
    assert parse_response("anthropic", {"content": [{"type": "text", "text": "Hello"}]}) == "Hello"
    assert parse_response("groq", {"choices": [{"message": {"content": "Yo"}}]}) == "Yo"
    with pytest.raises(AIError):
        parse_response("openai", {"weird": True})


@pytest.mark.parametrize("raw,clean", [
    ('"Thanks for the update."', "Thanks for the update."),
    ("Sure! Here's the rewritten text:\n\nDear Mike, thanks.", "Dear Mike, thanks."),
    ("<think>hmm</think>\nHola, amigo.", "Hola, amigo."),
    ("Plain text", "Plain text"),
    ("Dear Mike:\n\nThe roof is done.", "Dear Mike:\n\nThe roof is done."),
    ("Revised version:\nHi Mike", "Hi Mike"),
])
def test_tidy(raw, clean):
    assert tidy(raw) == clean


def test_brain_end_to_end_with_fake_server():
    calls = []

    def send(url, headers, body, timeout):
        calls.append(url)
        return {"message": {"content": "Better text."}}
    b = Brain("ollama", "http://localhost:11434", "llama3.2", send=send)
    assert b.ready and b.complete("x") == "Better text."
    assert calls == ["http://localhost:11434/api/chat"]


def test_brain_off_and_missing_key():
    with pytest.raises(AIError, match="off"):
        Brain("off", "", "").complete("x")
    assert not Brain("openai", "https://api.openai.com/v1", "gpt-4o-mini", "").ready


def test_pick_model():
    assert pick_model(["nomic-embed-text", "mistral:7b", "llama3.2:3b"]) == "llama3.2:3b"
    assert pick_model(["weird-model"]) == "weird-model"
    assert pick_model(["nomic-embed-text"]) == ""


def test_detect_local_prefers_ollama_and_survives_nothing_running():
    def send(url, headers, body, timeout):
        if "11434" in url:
            return {"models": [{"name": "qwen2.5:7b"}]}
        raise OSError("refused")
    assert detect_local(send) == ("ollama", "http://localhost:11434", "qwen2.5:7b")

    def none(url, headers, body, timeout):
        raise OSError("refused")
    assert detect_local(none) is None


from sayso.ai import choose_source, resolve_config


def test_choose_source():
    assert choose_source("edit", "hello", "", False) == ("hello", "replace_selection")
    assert choose_source("edit", "", "I think so", True) == ("I think so", "replace_last")
    assert choose_source("edit", "", "I think so", False)[0] is None
    assert choose_source("write", "their email", "", False) == ("their email", "insert_after_selection")
    assert choose_source("write", "", "old", True) == (None, "insert")


def test_resolve_config():
    assert resolve_config("openai", "", "") == ("openai", "https://api.openai.com/v1", "gpt-4o-mini")
    assert resolve_config("ollama", "", "qwen2.5") == ("ollama", "http://localhost:11434", "qwen2.5")
    assert resolve_config("nonsense", "x", "y") == ("off", "", "")
