"""Entry point: tray icon + engine + settings, wired together."""
import logging
import os
import queue
import sys
import threading
import tkinter as tk
from logging.handlers import RotatingFileHandler

from sayso import APP_NAME, __version__
from sayso.config import Config, data_dir

log = logging.getLogger("sayso")

STATUS = {
    "loading": "Getting ready...",
    "ready": 'Say "{wake}" to start',
    "listening": "Listening...",
    "thinking": "Typing...",
    "paused": "Paused",
    "error": "Needs attention",
}


def setup_logging():
    h = RotatingFileHandler(data_dir() / "sayso.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h])
    if sys.stderr:  # running from a terminal
        logging.getLogger().addHandler(logging.StreamHandler())
    sys.excepthook = lambda *a: log.critical("crash", exc_info=a)


class App:
    def __init__(self):
        import pystray
        from sayso import actions_win, winutil
        from sayso.engine import Engine
        from sayso.hotkey import PushToTalk
        from sayso.icons import mic_icon
        from sayso.license import License

        self.pystray, self.winutil, self.mic_icon = pystray, winutil, mic_icon
        self.cfg = Config.load()
        self.cfg.launch_at_startup = winutil.autostart_enabled()  # the installer may have set it
        self.root = tk.Tk()
        self.root.withdraw()
        self._ui: "queue.Queue" = queue.Queue()
        self.state, self.last_msg = "loading", ""
        self.settings_open = None
        self._stop = threading.Event()

        self.license = License(on_change=lambda: self.ui(self.on_license_change))
        self.engine = Engine(self.cfg, actions_win.perform,
                             on_state=lambda s, m: self.ui(lambda: self.on_state(s, m)),
                             beep=winutil.beep,
                             allowed=self.license.blocked_reason,
                             on_typed=self.license.add_words)
        self.ptt = PushToTalk(self.engine)
        self.ptt.set_key(self.cfg.ptt_key)

        M = pystray.MenuItem
        self.icon = pystray.Icon(
            APP_NAME, mic_icon("loading"), f"{APP_NAME} - {STATUS['loading']}",
            menu=pystray.Menu(
                M(lambda _: self.status_text(), None, enabled=False),
                M(lambda _: self.license.summary(), None, enabled=False),
                M(lambda _: (self.last_msg[:60] or " "), None, enabled=False,
                  visible=lambda _: bool(self.last_msg)),
                pystray.Menu.SEPARATOR,
                M("Pause", lambda: self.ui(self.toggle_pause), checked=lambda _: self.engine.paused),
                M("Settings...", lambda: self.ui(self.open_settings), default=True),
                M("How to use", lambda: self.ui(lambda: self.open_settings(welcome=True))),
                M("Open log folder", lambda: os.startfile(data_dir())),
                pystray.Menu.SEPARATOR,
                M(f"Quit {APP_NAME}", lambda: self.ui(self.quit)),
            ))

    # Everything that touches tkinter must run on the main thread; other threads queue work here.
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
        self.root.after(50, self._pump)

    def status_text(self):
        return STATUS.get(self.state, self.state).format(wake=self.cfg.wake_word)

    def on_state(self, state, msg):
        self.state = state
        if msg:
            self.last_msg = msg
        self.icon.icon = self.mic_icon(state)
        self.icon.title = f"{APP_NAME} - {self.status_text()}" + (f"\n{msg[:60]}" if msg else "")
        self.icon.update_menu()
        if msg and (state == "error" or msg == self.license.blocked_reason()):
            self.icon.notify(msg, APP_NAME)
        if state in ("ready", "paused") and not self.cfg.first_run_done and not self.settings_open:
            self.open_settings(welcome=True)

    def toggle_pause(self):
        self.engine.set_paused(not self.engine.paused)

    def open_settings(self, welcome=False):
        from sayso.settings_ui import SettingsWindow
        if self.settings_open and self.settings_open.win.winfo_exists():
            self.settings_open.win.lift()
            return
        self.settings_open = SettingsWindow(self.root, self.cfg, self.engine, self.license,
                                            self.save_settings, welcome)

    def on_license_change(self):
        self.icon.update_menu()
        if self.settings_open:
            self.settings_open.refresh_account()

    def save_settings(self, new: Config):
        try:
            self.winutil.set_autostart(new.launch_at_startup)
        except Exception:
            log.exception("autostart change failed")
        new.save()
        self.cfg = new
        self.ptt.set_key(new.ptt_key)
        self.engine.apply_config(new)
        log.info("settings saved: %s", new)

    def quit(self):
        self._stop.set()
        if self.license.unsynced:
            try:
                self.license.sync()  # don't lose the last few words' count
            except Exception:
                pass
        self.engine.stop()
        self.icon.stop()
        self.root.quit()

    def run(self):
        threading.Thread(target=self.icon.run, daemon=True, name="tray").start()
        self.engine.start()
        self.ptt.start()
        threading.Thread(target=self.license.run_background_sync, args=(self._stop,),
                         daemon=True, name="license").start()
        self.root.after(50, self._pump)
        self.root.mainloop()


def main():
    setup_logging()
    log.info("%s %s starting", APP_NAME, __version__)
    from sayso import winutil
    if winutil.already_running():
        winutil.message(APP_NAME, f"{APP_NAME} is already running - look for the microphone icon by the clock.")
        return
    App().run()
