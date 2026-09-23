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
    ("Open Chrome.", Action("switch", "Chrome")),
    ("Switch to VS Code", Action("switch", "Visual Studio Code")),
    ("open terminal", Action("switch", "PowerShell")),
    ("open figma", Action("switch", "figma")),
    ("Refactor the auth flow and run the tests. Send.", Action("type_send", "Refactor the auth flow and run the tests")),
    ("fix the bug, send", Action("type_send", "fix the bug")),
    ("Hello there.", Action("type", "Hello there")),
    ("Please resend the invoice", Action("type", "Please resend the invoice")),  # 'send' inside a word
    ("I will send", Action("type_send", "I will")),  # known trade-off: trailing 'send' always sends
])
def test_parse(heard, expected):
    assert parse(heard) == expected


def test_dictation_mode_never_runs_commands():
    assert parse("open Chrome", allow_commands=False) == Action("type", "open Chrome")
    assert parse("fix it. Send.", allow_commands=False) == Action("type", "fix it. Send")


def test_custom_send_word():
    assert parse("ship it. Go.", send_word="go") == Action("type_send", "ship it")
    assert parse("Go", send_word="go") == Action("send")
    assert parse("Send", send_word="go") == Action("type", "Send")
