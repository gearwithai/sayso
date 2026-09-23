"""Hold-to-talk key, watched with a global keyboard hook."""
from pynput import keyboard

ALIASES = {
    "ctrl_r": {"ctrl_r"},
    "alt_r": {"alt_r", "alt_gr"},  # Windows reports Right Alt as AltGr on some layouts
    "shift_r": {"shift_r"},
    "f9": {"f9"},
}


def _name(key) -> str:
    if isinstance(key, keyboard.Key):
        return key.name
    return getattr(key, "char", "") or ""


class PushToTalk:
    def __init__(self, engine):
        self.engine = engine
        self.names: set[str] = set()
        self.held = False
        self._listener = None

    def set_key(self, key_name: str):
        self.names = ALIASES.get(key_name, {key_name} if key_name else set())

    def start(self):
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self._listener.daemon = True
        self._listener.start()

    def _press(self, key):
        n = _name(key)
        if n in self.names:
            if not self.held:
                self.held = True
                self.engine.ptt_press()
        elif self.held:
            self.engine.ptt_cancel()

    def _release(self, key):
        if _name(key) in self.names and self.held:
            self.held = False
            self.engine.ptt_release()
