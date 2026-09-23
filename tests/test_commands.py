import pytest

from sayso.commands import Action, parse


@pytest.mark.parametrize("heard,expected", [
    ("", Action("nothing")),
    ("  .  ", Action("nothing")),
    ("Send.", Action("send")),
    ("send it!", Action("send")),
    ("Press enter.", Action("send")),
    ("New line.", Action("newline")),
    ("Scratch that.", Action("undo")),
    ("Stop listening.", Action("stop")),
    ("Open Chrome.", Action("switch", "chrome")),
    ("Switch to VS Code", Action("switch", "vs code")),
    ("open terminal", Action("switch", "terminal")),
    ("open figma", Action("switch", "figma")),
    ("Refactor the auth flow and run the tests. Send.", Action("type_send", "Refactor the auth flow and run the tests")),
    ("fix the bug, send", Action("type_send", "fix the bug")),
    ("Is it done? Send.", Action("type_send", "Is it done?")),
    ("Hello there.", Action("type", "Hello there.")),
    ("How are you?", Action("type", "How are you?")),
    ("Please resend the invoice", Action("type", "Please resend the invoice")),  # 'send' inside a word
    ("I will send", Action("type_send", "I will")),  # known trade-off: trailing 'send' always sends
])
def test_parse(heard, expected):
    assert parse(heard) == expected


def test_dictation_mode_never_runs_commands():
    assert parse("open Chrome", allow_commands=False) == Action("type", "open Chrome")
    assert parse("fix it. Send.", allow_commands=False) == Action("type", "fix it. Send.")


def test_custom_send_word():
    assert parse("ship it. Go.", send_word="go") == Action("type_send", "ship it")
    assert parse("Go", send_word="go") == Action("send")
    assert parse("Send", send_word="go") == Action("type", "Send")


SNIPS = {"email": "sunny@example.com", "address": "1 Main St", "sign off": "Thanks,\nSunny"}


@pytest.mark.parametrize("heard,expected", [
    ("Insert my email.", Action("snippet", "sunny@example.com")),
    ("insert email", Action("snippet", "sunny@example.com")),
    ("Paste my address", Action("snippet", "1 Main St")),
    ("insert sign-off", Action("snippet", "Thanks,\nSunny")),
    ("insert my phone", Action("type", "insert my phone")),
    ("Insert a table here.", Action("type", "Insert a table here.")),
])
def test_snippets(heard, expected):
    assert parse(heard, snippets=SNIPS) == expected


def test_insert_is_plain_text_without_snippets():
    assert parse("insert coin").kind == "type"


def test_custom_commands_match_exact_phrase():
    custom = ["new tab", "Open my CRM", "zoom in"]
    assert parse("New tab.", custom=custom) == Action("custom", "new tab")
    assert parse("open my CRM", custom=custom) == Action("custom", "Open my CRM")   # beats built-in "open"
    assert parse("open a new tab please", custom=custom).kind == "switch"
