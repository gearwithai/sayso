"""run_ai decides what text the AI sees and where the answer goes - checked here with fakes (no Windows)."""
import time

from sayso import ai
from sayso.app import App
from sayso.commands import Action


class FakeActions:
    def __init__(self, selection=""):
        self.selection, self.log = selection, []

    def copy_selection(self):
        return self.selection

    def select_back(self, n):
        self.log.append(("select_back", n))

    def collapse_selection(self):
        self.log.append(("collapse",))

    def paste(self, text):
        self.log.append(("paste", text))


def make_app(selection="", hwnds=(7, 7), answer="Better."):
    app = object.__new__(App)
    app.ai, app.actions = ai, FakeActions(selection)
    from sayso.text import style_for
    app.style_for = style_for
    seen = []
    app.brain = ai.Brain("ollama", "http://x", "m", send=lambda u, h, b, t: (seen.append(b), {"message": {"content": answer}})[1])
    order = list(hwnds)
    app._foreground = lambda: ("notepad.exe", order.pop(0) if len(order) > 1 else order[0])
    app._last_typed, app._last_pasted, app._last_hwnd, app._last_time = "", "", 0, 0.0
    app.recorded = []
    app.record = app.recorded.append
    app.ui = lambda fn: fn()
    app.window = type("W", (), {"clipboard_set": lambda self, t: app.recorded.append(("clip", t))})()
    return app, seen


def test_edit_selection_replaces_it():
    app, seen = make_app(selection="hey whats up")
    msg = app.run_ai(Action("ai_edit", "make this more professional"))
    assert app.actions.log == [("paste", "Better.")]
    assert "hey whats up" in seen[0]["messages"][1]["content"]
    assert msg.startswith("AI:")


def test_edit_last_typed_selects_it_back_first():
    app, _ = make_app()
    app._last_pasted, app._last_hwnd, app._last_time = "i think so ", 7, time.time()
    app.run_ai(Action("ai_edit", "make that formal"))
    assert app.actions.log == [("select_back", len("i think so ")), ("paste", "Better.")]


def test_edit_with_nothing_asks_for_a_selection():
    app, seen = make_app()
    assert "Select" in app.run_ai(Action("ai_edit", "make that formal"))
    assert seen == [] and app.actions.log == []


def test_write_with_context_keeps_their_message():
    app, _ = make_app(selection="Can you come Friday?")
    app.run_ai(Action("ai_write", "reply saying yes"))
    assert app.actions.log == [("collapse",), ("paste", "Better.")]


def test_switched_window_goes_to_clipboard():
    app, _ = make_app(selection="text", hwnds=(7, 9))
    msg = app.run_ai(Action("ai_edit", "fix the grammar"))
    assert "clipboard" in msg.lower() and ("clip", "Better.") in app.recorded
    assert app.actions.log == []


def test_ai_not_ready():
    app, _ = make_app()
    app.brain = ai.Brain("off", "", "")
    assert "Settings" in app.run_ai(Action("ai_write", "write a poem"))


def test_terminal_never_gets_ctrl_c():
    app, _ = make_app(selection="should not be read")
    app._foreground = lambda: ("WindowsTerminal.exe", 7)
    calls = []
    app.actions.copy_selection = lambda: calls.append(1) or "x"
    assert "Select" in app.run_ai(Action("ai_edit", "make that formal"))
    assert calls == []


def test_editor_line_copy_is_not_a_selection():
    """VS Code copies the whole line (with a newline) when nothing is selected."""
    app, _ = make_app(selection="    return x\n")
    app._last_pasted, app._last_hwnd, app._last_time = "i think so ", 7, time.time()
    app.run_ai(Action("ai_edit", "make that formal"))
    assert app.actions.log[0] == ("select_back", len("i think so "))
