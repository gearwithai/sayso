# Sayso — notes for AI assistants and contributors

Sayso is a free, open-source, hands-free voice typing app for Windows. Say "Sayso", then talk, and it types into whatever app is in front. Speech-to-text runs on the user's PC (faster-whisper). Owner: GearWithAI (Sunny). MIT licensed.

## Goals (keep these in mind for every change)
- Free for everyone, no account needed. The aim is reach and reputation, not revenue.
- One-time setup, then it runs quietly from the tray and starts with Windows.
- Private by default: voice never leaves the PC. AI actions use a local model (Ollama / LM Studio) unless the user adds their own cloud key.
- Improve and extend; don't rewrite from scratch.
- Windows 10/11 only.

## Layout
| Path | What |
|---|---|
| `sayso/engine.py` | Listening loop: wake word, hands-free, hold-to-talk, dictation mode |
| `sayso/wake.py` | Fuzzy wake-word match |
| `sayso/commands.py` | Transcript -> `Action` (pure, tested) |
| `sayso/ai.py` | AI voice actions: intents, providers, local model discovery (pure parts tested) |
| `sayso/text.py` | Cleanup: fillers, spoken punctuation, replacements, app styles, sentence continuation |
| `sayso/custom.py` | `%APPDATA%\Sayso\commands.json` loader |
| `sayso/apps.py` | Installed apps, per-app on/off, open/switch by name |
| `sayso/actions_win.py` | Windows side effects: paste, keys, selection, focus |
| `sayso/app.py` | Wires it together: tray, settings, history, AI executor, update check |
| `sayso/ui.py` | customtkinter window, setup wizard, status bubble |
| `sayso/config.py` | Settings dataclass (JSON in `%APPDATA%\Sayso`) |
| `sayso/winutil.py` | Single instance, autostart, beeps, DPAPI key encryption |
| `docs/index.html` | Download page (GitHub Pages). Sign-in is parked behind `REQUIRE_SIGNIN = false` |
| `installer/`, `sayso.spec` | Inno Setup + PyInstaller |
| `.github/workflows/build.yml` | Tests, builds `SaysoSetup.exe`, attaches it to releases |

## Rules
- Keep OS calls out of `commands.py`, `text.py`, `wake.py`, `ai.py` pure functions — they are unit-tested on Linux.
- Every new behaviour gets a test (`python -m pytest -q`; no mic or Windows needed).
- Nothing may steal keyboard focus from the user's app (the status bubble uses WS_EX_NOACTIVATE).
- Never store secrets in plain text: API keys go through `winutil.protect()` (DPAPI).
- `.bat` and `.iss` files must keep CRLF line endings.
- UI copy: short, plain words, no jargon.

## Testing
- `python -m pytest -q` - unit tests, run anywhere.
- CI then tests on real Windows: installs the built `SaysoSetup.exe` silently, runs `Sayso.exe --selftest` (libraries, model download, clipboard, DPAPI, window), and runs `tests/e2e_windows.py`: phrases spoken by the Windows voice go through the real app and must appear in a real Notepad (wake word, false triggers ignored, AI edit via a fake local AI server, dictation, hold-to-talk, send, clipboard images preserved). Finally it upgrades over a running copy. A release only gets its installer if all of that passes.

## Releasing
1. Bump the version in `sayso/__init__.py`, `installer/version_info.txt` and the default in `installer/sayso.iss`.
2. Push to `main` and check the Actions build is green.
3. Publish a GitHub release tagged `vX.Y.Z`; Actions attaches `SaysoSetup.exe`. The page's download link (`releases/latest/download/SaysoSetup.exe`) picks it up automatically.

## Services
- GitHub Pages: download page. GitHub Releases: installer hosting.
- Supabase project `laeitoulfslncjyolkpg`: `downloads` table + `sayso_download_count()` RPC (used only if sign-in is turned back on). Google/GitHub OAuth is not configured. The old `sayso-api` edge function is unused and can be deleted.

## Status (v0.5.1)
Shipped: wake word, hold-to-talk, commands, snippets, custom commands, per-app on/off, history, AI voice actions, dictation mode, app-aware formatting, status bubble, GPU with CPU fallback.
Not yet verified by a human on real Windows hardware. Ideas next: streaming AI answers, a trained "Hey Sayso" wake word, command packs, code signing.
