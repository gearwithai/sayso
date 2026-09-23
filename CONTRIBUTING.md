# Contributing to Sayso

Thanks for helping! Sayso should stay **simple to use, private, and free**.

## Getting started
1. Install Python 3.11 on Windows.
2. `run_dev.bat` runs Sayso from source with a console for logs.
3. `python -m pytest` runs the tests. They use fake audio and a fake speech model, so they work anywhere.

## Good first contributions
- **Command packs.** Add a `packs/<name>.json` with useful voice commands for an app (VS Code, Excel, Figma, …).
- **Wake-word spellings.** If Whisper hears "Sayso" as something new, add a test in `tests/test_wake.py`.
- **Spoken punctuation** for more languages in `sayso/text.py`.
- **Bugs.** Open an issue with your `sayso.log` (Settings → Logs).

## Bigger ideas
macOS/Linux support (the Windows-only parts are `actions_win.py`, `apps.py`, `winutil.py`), GPU acceleration,
a trained wake-word model, streaming transcription.

## Rules of the road
- Keep the voice pipeline on-device. No feature may upload audio or typed text.
- Add a test for logic you change (`commands.py`, `text.py`, `wake.py`, `custom.py`, `engine.py`).
- Plain words in the UI: "Turn off for this app", not "Disable per-process injection".
