"""Entry point: tray icon + engine + window, wired together."""
import json
import logging
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
               "beeps", "max_secs"}


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

        self.pystray, self.winutil, self.mic_icon, self.apps_mod, self.STATUS = pystray, winutil, mic_icon, apps, STATUS
        self.cfg = Config.load()
        if not self.cfg.first_run_done:
            self._set_autostart(True)  # on by default, so there's nothing to set up again
        else:
            self.cfg.launch_at_startup = winutil.autostart_enabled()
        self.apps = apps.load_cached()
        self.scanning = False
        self.state, self.last_msg, self.update_url = "loading", "", None
        self._ui: "queue.Queue" = queue.Queue()

        self.engine = Engine(self.cfg, lambda a: actions_win.perform(a, self.apps),
                             on_state=lambda s, m: self.ui(lambda: self.on_state(s, m)),
                             beep=winutil.beep, allowed=self.allowed, on_typed=self.on_typed)
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

    # ---------- engine hooks ----------
    def allowed(self, action):
        """Keeps Sayso quiet in apps the user turned off."""
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

    def on_typed(self, n):
        def save():
            self.cfg.words_typed += n
            self.cfg.save()
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
        if state == "error" and msg:
            self.notify(msg)

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
        self.icon.stop()
        self.window.quit()

    def run(self):
        threading.Thread(target=self.icon.run, daemon=True, name="tray").start()
        self.engine.start()
        self.ptt.start()
        self.rescan_apps()
        threading.Thread(target=self.check_for_update, daemon=True, name="update").start()
        if self.cfg.first_run_done:
            self.window.withdraw()   # already set up: live quietly in the tray
        else:
            self.window.show()
        self.window.after(50, self._pump)
        self.window.mainloop()


def main():
    setup_logging()
    log.info("%s %s starting", APP_NAME, __version__)
    from sayso import winutil
    if winutil.already_running():
        winutil.message(APP_NAME, f"{APP_NAME} is already running - click the microphone icon by the clock.")
        return
    App().run()
