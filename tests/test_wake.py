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
    "Say something nice",
    "Say hi to Mike",
    "Stay safe out there",
    "Sadly so",
    "Save the file",
    "Sorry, I missed that",
    "So what do you think",
])
def test_not_wake(heard):
    assert match(heard)[0] is False


def test_custom_wake_word():
    assert match("Computer, open Chrome", wake="Computer") == (True, "open Chrome")
    assert match("Sayso open Chrome", wake="Computer")[0] is False


from sayso.wake import name_advice


def test_name_advice():
    assert name_advice("Jarvis") == (True, "")
    assert name_advice("Sayso") == (True, "")
    assert name_advice("Hey")[0] is False
    assert name_advice("ok")[0] is False
    assert name_advice("Max")[0] is True and "Short" in name_advice("Max")[1]


def test_custom_names_are_heard():
    assert match("Jarvis, open Chrome.", wake="Jarvis") == (True, "open Chrome.")
    assert match("Nova. Hello world.", wake="Nova") == (True, "Hello world.")
    assert match("Friday, send", wake="Friday") == (True, "send")
    assert match("Jarvis", wake="Jarvis") == (True, "")
    assert match("Just a second", wake="Jarvis")[0] is False
    assert match("Nothing to see", wake="Nova")[0] is False
