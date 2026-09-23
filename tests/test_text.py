import pytest

from sayso.text import clean


@pytest.mark.parametrize("heard,typed", [
    ("um, so I think we should, uh, ship it.", "So I think we should, ship it."),
    ("Hmm let me check", "Let me check"),
    ("hello comma how are you question mark", "Hello, how are you?"),
    ("Dear team, new paragraph thanks for coming", "Dear team,\n\nThanks for coming"),
    ("first item new line second item", "First item\nSecond item"),
    ("this took a period of time", "This took a period of time"),
    ("send the invoice period", "Send the invoice."),
    ("wow exclamation mark", "Wow!"),
    ("He said open quote hi close quote", 'He said "hi"'),
    ("the umbrella is here", "The umbrella is here"),          # 'um' inside a word stays
    ("I'm here", "I'm here"),
    ("", ""),
])
def test_cleanup(heard, typed):
    assert clean(heard) == typed


def test_cleanup_off_keeps_words():
    assert clean("um hello comma world", cleanup=False) == "um hello comma world"


def test_replacements():
    words = {"gear with ai": "GearWithAI", "go high level": "GoHighLevel"}
    assert clean("I use go high level at gear with AI.", words) == "I use GoHighLevel at GearWithAI."
    assert clean("gear with ai rocks", words) == "GearWithAI rocks"


def test_longest_replacement_wins():
    words = {"sayso": "Sayso", "sayso pro": "Sayso Pro"}
    assert clean("try sayso pro today", words) == "Try Sayso Pro today"


def test_replacement_not_inside_words():
    assert clean("the cat in the category", {"cat": "dog"}) == "The dog in the category"


from sayso.text import continue_sentence, style_for


def test_terminal_style():
    assert clean("Git status.", style="terminal") == "git status"
    assert clean("npm run dev", style="terminal") == "npm run dev"
    assert clean("CD documents.", style="terminal") == "CD documents"   # all-caps word left alone


def test_chat_style_drops_final_full_stop_only():
    assert clean("see you soon.", style="chat") == "See you soon"
    assert clean("are you coming?", style="chat") == "Are you coming?"
    assert clean("well...", style="chat") == "Well..."


def test_style_for_apps():
    assert style_for("WindowsTerminal.exe") == "terminal"
    assert style_for("slack.exe") == "chat"
    assert style_for("chrome.exe") == "normal"
    assert style_for("") == "normal"


@pytest.mark.parametrize("prev,new,out", [
    ("I think", "The roof is fine.", "the roof is fine."),
    ("I think.", "The roof is fine.", "The roof is fine."),
    ("Call Mike", "And tell him Thursday.", "and tell him Thursday."),
    ("Meet", "Mike at noon.", "Mike at noon."),          # names keep their capital
    (None, "The roof.", "The roof."),
    ("Hi,\n", "Thanks.", "Thanks."),
])
def test_continue_sentence(prev, new, out):
    assert continue_sentence(new, prev) == out
