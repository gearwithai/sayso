"""Entry point: tray icon + engine + window, wired together."""
import json
import logging
import re
import time
import queue
import sys
import threading
import urllib.request
import webbrowser
from dataclasses import replace
from logging.handlers import RotatingFileHandler

from sayso import APP_NAME, __version__
from sayso.config import Config, data_dir

log = logging.getLogger("sayso")

REPO = "gearwithai/sayso"
DOWNLOAD_PAGE = "https://gearwithai.github.io/sayso/"
ENGINE_KEYS = {"hands_free", "wake_word", "stt_model", "mic_device", "silence_level", "silence_secs", "send_word",
               "beeps", "max_secs", "language", "use_cuda", "mic_name"}
AI_KEYS = {"ai_provider", "ai_model", "ai_base_url", "ai_key"}
CONTINUE_SECS = 45        # carry a sentence on if you speak again in the same window within this time
EDIT_LAST_SECS = 300      # "make that more formal" works on what Sayso last typed for this long
HISTORY_MAX = 50


def setup_logging():
    h = RotatingFileHandler(data_dir() / "sayso.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h])
    if sys.stderr:  # running from a terminal
        logging.getLogger().addHandler(logging.StreamHandler())
    sys.excepthook = lambda *a: log.critical("crash", exc_info=a)


def version_tuple(v: str):
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


class App:
    def __init__(self):
        import pystray
        from sayso import actions_win, apps, winutil
        from sayso.engine import Engine
        from sayso.hotkey import PushToTalk
        from sayso.icons import mic_icon
        from sayso.ui import MainWindow, STATUS
        from sayso.commands import Action, parse
        from sayso.custom import CustomCommands
        from sayso.text import clean, continue_sentence, style_for
        self.style_for = style_for
        from sayso import ai

        self.pystray, self.winutil, self.mic_icon, self.apps_mod, self.STATUS = pystray, winutil, mic_icon, apps, STATUS
        self.ai, self.actions = ai, actions_win
        self.brain = ai.Brain("off", "", "")
        self.ai_status = "AI is off"
        self.cfg = Config.load()
        if not self.cfg.first_run_done:
            self._set_autostart(True)  # on by default, so there's nothing to set up again
        else:
            self.cfg.launch_at_startup = winutil.autostart_enabled()
        self.apps = apps.load_cached()
        self.scanning = False
        self.state, self.last_msg, self.update_url = "loading", "", None
        self._ui: "queue.Queue" = queue.Queue()
        self.custom = CustomCommands()
        self.history = self._load_history()

        def parser(text, allow_commands):
            return parse(text, self.cfg.send_word, allow_commands=allow_commands,
                         snippets=self.cfg.snippets, custom=list(self.custom.get()), ai_ready=self.brain.ready)

        def perform(a):
            if a.kind in ("type", "type_send"):
                exe, hwnd = self._foreground()
                style = style_for(exe) if self.cfg.smart_format else "normal"
                text = clean(a.text, self.cfg.replacements, self.cfg.cleanup, style)
                # did the sentence really end? (chat style hides the final full stop)
                ended = bool(re.search(r"[.?!:]\s*$", clean(a.text, None, self.cfg.cleanup)))
                if (self.cfg.smart_continue and style != "terminal" and hwnd == self._last_hwnd
                        and time.time() - self._last_time < CONTINUE_SECS and not self._last_ended):
                    text = continue_sentence(text, self._last_typed)
                a = Action(a.kind, text)
                msg = actions_win.perform(a, self.apps, self.custom.get())
                self._remember(text + (" " if a.kind == "type" else ""), hwnd, sent=a.kind == "type_send")
                self._last_ended = ended
                return msg
            if a.kind in ("ai_edit", "ai_write"):
                return self.run_ai(a)
            if a.kind == "ui":
                self.ui(lambda: self.window.show_tab(a.text))
                return f"Opened {a.text}"
            if a.kind in ("send", "newline"):
                self._last_time = 0     # a new message starts fresh
            return actions_win.perform(a, self.apps, self.custom.get())

        self._last_typed, self._last_hwnd, self._last_time, self._last_pasted = "", 0, 0.0, ""
        self._last_ended = True
        self.engine = Engine(self.cfg, perform,
                             on_state=lambda s, m: self.ui(lambda: self.on_state(s, m)),
                             beep=winutil.beep, allowed=self.allowed, on_typed=self.on_typed, parser=parser)
        self.ptt = PushToTalk(self.engine)
        self.ptt.set_key(self.cfg.ptt_key)
        self.window = MainWindow(self)

        M = pystray.MenuItem
        self.icon = pystray.Icon(
            APP_NAME, mic_icon("loading"), APP_NAME,
            menu=pystray.Menu(
                M(f"Open {APP_NAME}", lambda: self.ui(self.window.show), default=True),
                M(lambda _: self.status_text(), None, enabled=False),
                pystray.Menu.SEPARATOR,
                M("Pause", lambda: self.ui(lambda: self.set_paused(not self.engine.paused)),
                  checked=lambda _: self.engine.paused),
                M("Update available - download", lambda: webbrowser.open(self.update_url or DOWNLOAD_PAGE),
                  visible=lambda _: bool(self.update_url)),
                pystray.Menu.SEPARATOR,
                M(f"Quit {APP_NAME}", lambda: self.ui(self.quit)),
            ))

    # ---------- threading: tkinter only on the main thread ----------
    def ui(self, fn):
        self._ui.put(fn)

    def _pump(self):
        while True:
            try:
                fn = self._ui.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log.exception("ui task failed")
        self.window.after(50, self._pump)

    # ---------- typing memory (for "carry on the sentence" and "make that more formal") ----------
    def _foreground(self):
        try:
            exe, _, hwnd = self.apps_mod.foreground()
            return exe.replace("/", "\\").rsplit("\\", 1)[-1], int(hwnd or 0)
        except Exception:
            return "", 0

    def _remember(self, pasted: str, hwnd: int, sent: bool = False):
        self._last_typed = pasted.rstrip()
        self._last_pasted = "" if sent else pasted     # after Enter the text is gone from the box
        self._last_hwnd, self._last_time = hwnd, (0.0 if sent else time.time())

    # ---------- AI voice actions ----------
    def setup_ai(self):
        """Build the AI helper from settings. "auto" looks for Ollama / LM Studio running on this PC."""
        cfg = self.cfg
        if cfg.ai_provider == "auto":
            found = self.ai.detect_local()
            if found:
                p, base, model = found
                self.brain = self.ai.Brain(p, base, model)
                self.ai_status = f"Using {self.ai.BY_ID[p][0].split(' (')[0]} on this PC ({model})"
            else:
                self.brain = self.ai.Brain("off", "", "")
                self.ai_status = "No AI found on this PC. Install Ollama (free) or add an API key."
        else:
            p, base, model = self.ai.resolve_config(cfg.ai_provider, cfg.ai_base_url, cfg.ai_model)
            key = ""
            if cfg.ai_key:
                try:
                    key = self.winutil.unprotect(cfg.ai_key)
                except Exception:
                    log.exception("couldn't read the saved API key")
            self.brain = self.ai.Brain(p, base, model, key)
            if p == "off":
                self.ai_status = "AI is off"
            elif not self.brain.ready:
                self.ai_status = "Needs an API key" if self.ai.BY_ID[p][2] and not key else "Pick a model"
            else:
                self.ai_status = f"Ready: {model}"
        log.info("AI: %s", self.ai_status)
        self.ui(lambda: self.window.ai_changed())

    def set_ai_key(self, plain: str):
        """Keys are encrypted with Windows (DPAPI) before they touch the settings file."""
        try:
            enc = self.winutil.protect(plain.strip()) if plain.strip() else ""
        except Exception:
            log.exception("couldn't encrypt the API key")
            return False
        self.update_cfg(ai_key=enc)
        return True

    def test_ai(self, done):
        """Round-trip a tiny prompt; done(ok, message) is called on the UI thread."""
        def work():
            try:
                out = self.brain.complete("Instruction: reply with the single word: ready", timeout=30)
                ok, msg = True, f"Works! The AI said: {out[:40]}"
            except self.ai.AIError as e:
                ok, msg = False, str(e)
            except Exception as e:
                ok, msg = False, f"Something went wrong: {e}"
            self.ui(lambda: done(ok, msg))
        threading.Thread(target=work, daemon=True, name="ai-test").start()

    def run_ai(self, a):
        """Runs on the engine thread: grab the text, ask the AI, put the answer where the cursor is."""
        op = "edit" if a.kind == "ai_edit" else "write"
        if not self.brain.ready:
            return "AI isn't set up - open Settings > AI (Ollama is free and private)."
        exe, hwnd = self._foreground()
        # in a terminal Ctrl+C would stop the running program, so never copy there
        selected = "" if self.style_for(exe) == "terminal" else self.actions.copy_selection()
        if selected.endswith("\n") and selected.count("\n") == 1:
            selected = ""   # code editors copy the whole line when nothing is selected
        selected = selected.strip()
        fresh = bool(self._last_pasted) and hwnd == self._last_hwnd and time.time() - self._last_time < EDIT_LAST_SECS
        source, how = self.ai.choose_source(op, selected, self._last_pasted.rstrip(), fresh)
        if how not in ("replace_selection", "replace_last", "insert", "insert_after_selection"):
            return how
        try:
            out = self.brain.complete(self.ai.build_prompt(self.ai.Intent(op, a.text), source))
        except self.ai.AIError as e:
            return str(e)
        if not out:
            return "The AI didn't send anything back."
        if self._foreground()[1] != hwnd:
            # you moved on while the AI was thinking - don't type into the wrong window
            self.ui(lambda: self.window.clipboard_set(out))
            self.record(out)
            return "The AI answer is on your clipboard (you switched windows) - press Ctrl+V."
        if how == "replace_last":
            self.actions.select_back(len(self._last_pasted))
        elif how == "insert_after_selection":
            self.actions.collapse_selection()
        self.actions.paste(out)
        self._remember(out, hwnd)
        self.record(out)
        return f"AI: {out[:60]}"

    # ---------- engine hooks ----------
    def allowed(self, action):
        """Keeps Sayso quiet in apps the user turned off."""
        if action.kind in ("ui", "stop", "dictate_on", "dictate_off", "nothing"):
            return None
        if action.kind != "switch":
            try:
                if self.actions.foreground_is_admin():
                    return "Can't type into apps running as administrator - Windows blocks it"
            except Exception:
                pass
        disabled = set(self.cfg.disabled_apps)
        if not disabled:
            return None
        if action.kind == "switch":
            app = self.apps_mod.find_app(self.apps, action.text)
            return f"Sayso is turned off for {app.name}" if app and app.id in disabled else None
        try:
            exe, title, _ = self.apps_mod.foreground()
        except Exception:
            return None
        app = self.apps_mod.match_foreground(self.apps, exe, title)
        if app and app.id in disabled:
            return f"Sayso is turned off in {app.name} - turn it on in the Apps tab"
        return None

    # ---------- history (kept only on this PC) ----------
    @staticmethod
    def _history_path():
        return data_dir() / "history.json"

    def _load_history(self):
        try:
            return json.loads(self._history_path().read_text(encoding="utf-8"))[-HISTORY_MAX:]
        except Exception:
            return []

    def clear_history(self):
        self.history = []
        self._history_path().write_text("[]", encoding="utf-8")
        self.window.refresh_home()

    def on_typed(self, action):
        self.record(self._last_typed if action.kind in ("type", "type_send") else action.text)

    def record(self, text):
        n = len(text.split())

        def save():
            self.cfg.words_typed += n
            self.cfg.save()
            self.history = (self.history + [{"t": time.strftime("%H:%M"), "text": text}])[-HISTORY_MAX:]
            try:
                self._history_path().write_text(json.dumps(self.history), encoding="utf-8")
            except Exception:
                log.exception("history save failed")
            self.window.refresh_home()
        self.ui(save)

    def status_text(self):
        return self.STATUS.get(self.state, (self.state,))[0].format(wake=self.cfg.wake_word)

    def on_state(self, state, msg):
        self.state = state
        if msg:
            self.last_msg = msg
        self.icon.icon = self.mic_icon(state)
        self.icon.title = f"{APP_NAME} - {self.status_text()}" + (f"\n{msg[:60]}" if msg else "")
        self.icon.update_menu()
        self.window.update_state(state, msg)
        if self.cfg.show_bubble:
            self.window.bubble.show(state, msg, self.status_text())
        if state == "error" and msg and msg != getattr(self, "_last_error", ""):
            self.notify(msg)   # once per problem, not on every retry
        self._last_error = msg if state == "error" else ""

    def notify(self, msg):
        try:
            self.icon.notify(msg, APP_NAME)
        except Exception:
            pass

    # ---------- used by the window ----------
    def set_paused(self, paused: bool):
        self.engine.set_paused(paused)
        self.icon.update_menu()

    def _set_autostart(self, on: bool):
        try:
            self.winutil.set_autostart(on)
        except Exception:
            log.exception("autostart change failed")

    def update_cfg(self, **changes):
        self.cfg = replace(self.cfg, **changes)
        self.cfg.save()
        if "launch_at_startup" in changes:
            self._set_autostart(self.cfg.launch_at_startup)
        if "ptt_key" in changes:
            self.ptt.set_key(self.cfg.ptt_key)
        if AI_KEYS & changes.keys():
            threading.Thread(target=self.setup_ai, daemon=True, name="ai-setup").start()
        if ENGINE_KEYS & changes.keys():
            self.engine.apply_config(self.cfg)
        else:
            self.engine.cfg = self.cfg
        log.info("settings changed: %s", changes)

    def set_app_enabled(self, app_id: str, on: bool):
        disabled = [a for a in self.cfg.disabled_apps if a != app_id]
        if not on:
            disabled.append(app_id)
        self.update_cfg(disabled_apps=disabled)

    def set_all_apps_enabled(self, on: bool):
        self.update_cfg(disabled_apps=[] if on else [a.id for a in self.apps])

    def rescan_apps(self):
        if self.scanning:
            return
        self.scanning = True
        self.window.apps_changed()

        def work():
            found = self.apps_mod.scan()

            def done():
                self.scanning = False
                if found:
                    self.apps = found
                self.window.apps_changed()
            self.ui(done)
        threading.Thread(target=work, daemon=True, name="app-scan").start()

    def check_for_update(self):
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                         headers={"Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                latest = json.loads(r.read()).get("tag_name", "")
            if latest and version_tuple(latest) > version_tuple(__version__):
                self.update_url = DOWNLOAD_PAGE
                self.ui(lambda: (self.icon.update_menu(), self.notify(f"Sayso {latest} is available.")))
        except Exception as e:
            log.info("update check skipped: %s", e)

    def quit(self):
        self.engine.stop()
        try:
            self.icon.visible = False   # removes the tray icon straight away (no ghost icon)
        except Exception:
            pass
        try:
            self.icon.stop()
        except Exception:
            pass
        self.window.quit()

    def run(self):
        threading.Thread(target=self.icon.run, daemon=True, name="tray").start()
        self.engine.start()
        self.ptt.start()
        self.rescan_apps()
        threading.Thread(target=self.check_for_update, daemon=True, name="update").start()
        threading.Thread(target=self.setup_ai, daemon=True, name="ai-setup").start()
        if self.cfg.first_run_done:
            self.window.withdraw()   # already set up: live quietly in the tray
        else:
            self.window.show()
        self.window.after(50, self._pump)
        self.window.after(200, self.window.bubble.build)   # made up front so it never grabs focus later
        self.window.mainloop()


def main():
    setup_logging()
    log.info("%s %s starting", APP_NAME, __version__)
    from sayso import winutil
    if winutil.already_running():
        winutil.message(APP_NAME, f"{APP_NAME} is already running - click the microphone icon by the clock.")
        return
    App().run()
