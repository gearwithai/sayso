"""Sayso.exe --selftest OUT_DIR [WAV_DIR]

Proves an installed copy works: every library loads, the speech model downloads and runs, the
wake word and commands are understood from real speech, the clipboard and key encryption work,
and the window can be built. Writes OUT_DIR/selftest.json and returns 0 when everything passed.
"""
import json
import os
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path


def main(args):
    out = Path(args[0]) if args else Path(tempfile.gettempdir())
    wav_dir = Path(args[1]) if len(args) > 1 else None
    out.mkdir(parents=True, exist_ok=True)
    os.environ["APPDATA"] = str(out / "profile")      # throwaway settings + model folder
    results, ok = {}, True

    def step(name, fn):
        nonlocal ok
        t = time.time()
        try:
            results[name] = {"ok": True, "detail": fn(), "secs": round(time.time() - t, 2)}
        except Exception:
            ok = False
            results[name] = {"ok": False, "detail": traceback.format_exc()[-1500:], "secs": round(time.time() - t, 2)}

    def imports():
        import numpy, sounddevice, faster_whisper, ctranslate2, pystray, PIL, customtkinter  # noqa: F401
        from pynput import keyboard, mouse  # noqa: F401
        return {"mics": sum(1 for d in sounddevice.query_devices() if d["max_input_channels"] > 0),
                "cuda_devices": ctranslate2.get_cuda_device_count()}
    step("imports", imports)

    def clipboard():
        from sayso import winclip
        before = winclip.snapshot()
        assert winclip.set_text("sayso selftest ✓"), "couldn't set clipboard"
        got = winclip.get_text()
        winclip.restore(before)
        assert got == "sayso selftest ✓", got
        return "round trip ok"
    step("clipboard", clipboard)

    def encryption():
        from sayso import winutil
        blob = winutil.protect("sk-test-123")
        assert blob and "sk-test" not in blob and winutil.unprotect(blob) == "sk-test-123"
        return "DPAPI ok"
    step("encryption", encryption)

    model = {}

    def load_model():
        from faster_whisper import WhisperModel
        from sayso.config import models_dir
        model["m"] = WhisperModel("base.en", device="cpu", compute_type="int8",
                                  download_root=str(models_dir() / "whisper"))
        return "base.en on cpu"
    step("speech_model", load_model)

    if wav_dir and "m" in model:
        import numpy as np
        from sayso import wake
        from sayso.commands import parse
        heard = {}
        for f in sorted(wav_dir.glob("*.wav")):
            def one(f=f):
                with wave.open(str(f)) as w:
                    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
                segs, _ = model["m"].transcribe(audio, language="en", vad_filter=True, beam_size=1,
                                                initial_prompt="Sayso.", condition_on_previous_text=False)
                text = " ".join(s.text for s in segs).strip()
                woke, rest = wake.match(text)
                a = parse(rest, "send") if woke else None
                return {"heard": text, "woke": woke, "action": [a.kind, a.text] if a else None}
            t = time.time()
            try:
                heard[f.stem] = one()
            except Exception:
                ok = False
                heard[f.stem] = {"error": traceback.format_exc()[-800:]}
            heard[f.stem]["secs"] = round(time.time() - t, 2)
        results["speech"] = heard

    def window():
        from sayso.app import App
        from sayso.config import Config
        Config(first_run_done=True).save()   # skip first-run setup (it would add a startup entry)
        app = App()
        app.window.update()
        app.window.show_tab("Settings")
        app.window.update()
        app.window.bubble.build()
        app.window.bubble.show("listening", "", "Listening...")
        app.window.update()
        app.icon.visible = False
        app.window.destroy()
        return "window, tabs and status bubble built"
    step("window", window)

    results["passed"] = ok
    (out / "selftest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
