# Sayso

**Type anywhere with your voice. Free for Windows.**
Say "Sayso", then talk, and your words appear in whatever app is in front. Speech is processed on your own PC.

**Download:** https://gearwithai.github.io/sayso/ (or [the latest release](https://github.com/gearwithai/sayso/releases/latest))

## Using it
- **"Sayso, hello world"**: types "hello world".
- **"Sayso, fix the login bug. Send."**: types it and presses Enter.
- **"Sayso"** on its own → beep → say what to type or a command.
- After "Sayso": **send**, **new line**, **scratch that** (undo), **open Chrome** / **switch to VS Code**, **stop listening**.
- **Hold Right Ctrl** and talk: types plain text when you let go.

The first launch walks through a one-time setup: pick the mic, choose which apps Sayso may type into, try it.
After that it starts with Windows and lives by the clock; click the tray icon to open the window
(Home · Apps · Settings · Commands). Everything saves as you change it.

## How it works
```
mic → speech detected → Whisper (on this PC) transcribes the first 2.5 s
    → starts with "Sayso"? → command or text → typed into the app in front (if that app is on)
```
- `sayso/engine.py`: listening loop (wake word, hold-to-talk)
- `sayso/wake.py`: fuzzy match of the wake word ("Say so", "Say-so", ...)
- `sayso/commands.py`: transcript → action
- `sayso/apps.py`: installed apps from the Start menu, per-app on/off, open apps by name
- `sayso/actions_win.py`: paste, keys, switch windows
- `sayso/ui.py`: the window (customtkinter)
- `sayso/app.py`: tray icon, settings, update check

Settings, the speech model and logs live in `%APPDATA%\Sayso`. The app installs per-user to `%LOCALAPPDATA%\Programs\Sayso`.

## Releasing a new version
1. Bump `__version__` in `sayso/__init__.py`.
2. On GitHub: Releases → Draft a new release → tag `v0.x.y` → Publish.
3. Actions builds the installer and attaches `SaysoSetup.exe` to the release. The download page always points at the latest one.
Installed copies see the new version and offer the update from the tray menu.

## Developing
- `run_dev.bat`: run from source (Python 3.11).
- `build.bat`: build the app and installer locally (installer needs Inno Setup 6).
- `python -m pytest`: tests (no mic or Windows needed).
