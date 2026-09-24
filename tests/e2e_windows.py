"""End-to-end test on real Windows (run by CI on a Windows machine; not part of the normal pytest run).

    python tests/e2e_windows.py --make-wavs DIR     speak the test phrases with the Windows voice
    python tests/e2e_windows.py --run DIR           drive the real app with them

The real App runs: speech (Windows' own voice, not a person) -> the real Whisper model -> wake word
-> commands -> text cleanup -> clipboard paste -> keystrokes into a real Notepad window. Only the
microphone is replaced: the recorded phrases are fed in where mic audio would arrive.
An AI server is faked locally so "make that more formal" can be checked without an API key.
"""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PHRASES = {
    # file name: what the Windows voice says ("Say-so" is how the wake word is spoken)
    "01_hello": "Say-so, hello world.",
    "02_not_for_us": "Say something nice about the weather today.",
    "03_meeting": "Say-so, the meeting is at five.",
    "04_formal": "Say-so, make that more formal.",
    "05_dictation_on": "Say-so, start dictation.",
    "06_dictating": "This sentence has no wake word at all.",
    "07_dictation_off": "Stop dictation.",
    "08_hold": "This was typed with hold to talk.",
    "09_send": "Say-so, send.",
    "10_switch": "Say-so, switch to Notepad.",
    "11_after_switch": "Say-so, typed right after switching.",
    "12_jarvis_test": "Jarvis, hello.",
    "13_jarvis_type": "Jarvis, typed with a new name.",
    "14_old_name": "Say-so, the old name should do nothing.",
}
AI_ANSWER = "The meeting is scheduled for 5 PM."


def make_wavs(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["Add-Type -AssemblyName System.Speech",
             "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
             "$s.Rate = -1",
             "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
             "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)"]
    for name, text in PHRASES.items():
        lines += [f"$s.SetOutputToWaveFile('{folder / (name + '.wav')}', $f)", f"$s.Speak(\"{text}\")"]
    lines.append("$s.SetOutputToNull()")
    subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(lines)], check=True)
    print("made", len(list(folder.glob("*.wav"))), "phrases")


# ---------------------------------------------------------------- Notepad helpers
user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.GetShellWindow.restype = wintypes.HWND
WM_SETTEXT, WM_GETTEXT, WM_GETTEXTLENGTH = 0x000C, 0x000D, 0x000E


class Notepad:
    def __init__(self):
        self.proc = subprocess.Popen(["notepad.exe"])
        for _ in range(100):
            self.hwnd = user32.FindWindowW("Notepad", None)
            if self.hwnd:
                break
            time.sleep(0.1)
        assert self.hwnd, "Notepad didn't open"
        self.edit = user32.FindWindowExW(self.hwnd, None, "Edit", None) or \
            user32.FindWindowExW(self.hwnd, None, "RichEditD2DPT", None)
        assert self.edit, "Notepad's text box not found"

    def focus(self):
        from sayso.actions_win import _focus
        _focus(self.hwnd)
        time.sleep(0.3)

    def text(self) -> str:
        n = user32.SendMessageW(self.edit, WM_GETTEXTLENGTH, 0, 0)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.SendMessageW(self.edit, WM_GETTEXT, n + 1, ctypes.addressof(buf))
        return buf.value

    def clear(self):
        buf = ctypes.create_unicode_buffer("")
        user32.SendMessageW(self.edit, WM_SETTEXT, 0, ctypes.addressof(buf))

    def close(self):
        self.proc.kill()


# ---------------------------------------------------------------- fake AI server (OpenAI-style)
class FakeAI(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeAI.seen.append(body["messages"][-1]["content"])
        data = json.dumps({"choices": [{"message": {"content": AI_ANSWER}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def run(folder: Path) -> int:
    profile = Path(tempfile.mkdtemp())
    os.environ["APPDATA"] = str(profile)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    server = HTTPServer(("127.0.0.1", 0), FakeAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    import numpy as np
    from sayso import winclip
    from sayso.config import Config
    from sayso.engine import CHUNK
    Config(first_run_done=True, beeps=False, ai_provider="lmstudio", ai_model="fake-model",
           ai_base_url=f"http://127.0.0.1:{server.server_port}/v1", show_bubble=True).save()
    from sayso.app import App, setup_logging
    setup_logging()
    app = App()
    app.engine._open_mic = lambda rescan=False: None   # the recorded phrases stand in for the mic
    results, failures = [], []

    def check(name, cond, detail):
        results.append((name, bool(cond), detail))
        if not cond:
            failures.append(name)
        print(("PASS " if cond else "FAIL ") + name + " | " + str(detail)[:300], flush=True)

    def audio(name):
        with wave.open(str(folder / f"{name}.wav")) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return [a[i:i + CHUNK] for i in range(0, len(a) - CHUNK, CHUNK)]

    def say(name, gap=1.6):
        for c in audio(name) + [np.zeros(CHUNK, np.int16)] * int(gap * 16000 / CHUNK):
            app.engine.audio.put(c)
            time.sleep(0.02)

    def settle(secs=20):
        """Wait until the engine has finished with everything it heard."""
        end = time.time() + secs
        time.sleep(0.5)
        while time.time() < end:
            if app.engine.audio.empty() and app.engine.state in ("ready", "dictating", "paused"):
                time.sleep(1.0)
                if app.engine.audio.empty() and app.engine.state in ("ready", "dictating", "paused"):
                    return
            time.sleep(0.2)

    def script():
        try:
            end = time.time() + 600
            while app.engine.state != "ready" and time.time() < end:   # first run downloads the model
                time.sleep(0.5)
            check("engine ready", app.engine.state == "ready", f"{app.engine.state} {app.last_msg}")
            app.setup_ai()
            check("AI found", app.brain.ready, app.ai_status)

            pad = Notepad()
            pad.focus()
            # a picture on the clipboard must survive dictation
            dib = (40).to_bytes(4, "little") + (1).to_bytes(4, "little") + (1).to_bytes(4, "little") + \
                (1).to_bytes(2, "little") + (32).to_bytes(2, "little") + bytes(20) + b"\x00\x80\xff\x00"
            with_clip = winclip._open()
            if with_clip:
                winclip.user32.EmptyClipboard()
                winclip._put(winclip.CF_DIB, dib)
                winclip.user32.CloseClipboard()

            say("01_hello"); settle()
            t = pad.text()
            check("wake word + typing", "hello world" in t.lower(), repr(t))
            check("picture still on clipboard", winclip.has_format(winclip.CF_DIB), "CF_DIB present")

            pad.clear(); pad.focus()
            say("02_not_for_us"); settle()
            check("ignores speech not starting with Sayso", pad.text() == "", repr(pad.text()))

            pad.clear(); pad.focus()
            say("03_meeting"); settle()
            before = pad.text()
            check("second phrase typed", "meeting" in before.lower(), repr(before))
            say("04_formal"); settle(40)
            after = pad.text()
            check("AI rewrote what was just typed", after.strip() == AI_ANSWER, repr(after))
            check("AI was given the typed text", FakeAI.seen and "meeting" in FakeAI.seen[-1].lower(),
                  FakeAI.seen[-1:] if FakeAI.seen else "no request")

            pad.clear(); pad.focus()
            say("05_dictation_on"); settle()
            check("dictation mode on", app.engine.dictating, app.engine.state)
            say("06_dictating"); settle()
            say("07_dictation_off"); settle()
            t = pad.text()
            check("dictation types without wake word", "no wake word" in t.lower(), repr(t))
            check("dictation mode off again", not app.engine.dictating, app.engine.state)

            pad.clear(); pad.focus()
            app.engine.ptt_press()
            time.sleep(0.5)
            say("08_hold", gap=0.3)
            app.engine.ptt_release()
            settle()
            t = pad.text()
            check("hold to talk", "hold to talk" in t.lower(), repr(t))

            say("09_send"); settle()
            t = pad.text()
            check("'Sayso, send' presses Enter", "\r\n" in t or "\n" in t, repr(t))

            # switching apps by voice, then dictating straight away (the Alt-key/menu-bar bug)
            pad.clear()
            user32.SetForegroundWindow(user32.GetShellWindow())
            time.sleep(0.5)
            say("10_switch"); settle()
            check("'switch to Notepad' brings it to the front", user32.GetForegroundWindow() == pad.hwnd,
                  app.last_msg)
            say("11_after_switch"); settle()
            t = pad.text()
            check("typing works right after switching", "after switching" in t.lower(), repr(t))

            # renaming: "call it anything, say it once, ready to drive"
            app.ui(lambda: app.update_cfg(wake_word="Jarvis"))
            time.sleep(1.5); settle()
            heard = []
            app.start_test(heard.append)
            pad.clear(); pad.focus()
            say("12_jarvis_test"); settle()
            app.stop_test()
            check("test mode hears the new name", bool(heard), [(a.kind, a.text) for a in heard])
            check("test mode types nothing", pad.text() == "", repr(pad.text()))
            say("13_jarvis_type"); settle()
            t = pad.text()
            check("new name types", "new name" in t.lower(), repr(t))
            say("14_old_name"); settle()
            check("old name no longer wakes it", "old name" not in pad.text().lower(), repr(pad.text()))

            check("history recorded", len(app.history) >= 3, len(app.history))
            pad.close()
        except Exception as e:
            import traceback
            traceback.print_exc()
            failures.append(f"crashed: {e}")
        finally:
            app.ui(app.quit)

    app.engine.start()
    threading.Thread(target=script, daemon=True).start()
    app.window.withdraw()
    app.window.after(50, app._pump)
    app.window.after(200, app.window.bubble.build)
    app.window.mainloop()

    print("\n==== Sayso end-to-end:", len(results) - len(failures), "of", len(results), "checks passed ====")
    if failures:
        print("FAILED:", failures)
        log = profile / "Sayso" / "sayso.log"
        if log.exists():
            print("---- sayso.log (last 80 lines) ----")
            print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]))
    return 1 if failures else 0


if __name__ == "__main__":
    mode, folder = sys.argv[1], Path(sys.argv[2])
    if mode == "--make-wavs":
        make_wavs(folder)
    else:
        sys.exit(run(folder))
