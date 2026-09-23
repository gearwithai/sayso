import pytest

from sayso.wake import match


@pytest.mark.parametrize("heard,rest", [
    ("Sayso.", ""),
    ("Sayso, open Chrome.", "open Chrome."),
    ("Say so, fix the tests. Send.", "fix the tests. Send."),
    ("Say, so. Open Cursor", "Open Cursor"),
    ("Say-so new line", "new line"),
    ("Hey Sayso, scratch that", "scratch that"),
    ("Okay, Sayso send", "send"),
    ("Seso open terminal", "open terminal"),
    ("SAYSO!", ""),
])
def test_wake_heard(heard, rest):
    assert match(heard) == (True, rest)


@pytest.mark.parametrize("heard", [
    "",
    "Hello there",
    "I'd say so too",
    "Okay let's go",
    "Sales report is due",
    "Some other thing",
])
def test_not_wake(heard):
    assert match(heard)[0] is False


def test_custom_wake_word():
    assert match("Computer, open Chrome", wake="Computer") == (True, "open Chrome")
    assert match("Sayso open Chrome", wake="Computer")[0] is False
