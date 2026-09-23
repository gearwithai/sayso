# Sayso

Hands-free voice typing for Windows. Say **"Sayso"**, then what you want typed, and it appears in whatever app is in front.
Your voice is processed on your own PC. Only the word count for the free trial goes to the cloud.

## Using it
- **"Sayso, hello world"**: types "hello world".
- **"Sayso, fix the login bug. Send."**: types it and presses Enter.
- **"Sayso"** on its own → beep → say your text or a command.
- Commands after "Sayso": **send**, **new line**, **scratch that** (undo), **open Chrome** / **switch to VS Code**, **stop listening**.
- **Hold Right Ctrl** and talk: types plain text when you let go (no wake word needed).
- The wake word can be changed in Settings (any word works).

Tray icon: purple = waiting, red = listening, amber = typing, gray = paused, blue = loading.

## How it's built
```
Sayso.exe (on the user's PC)                Cloud
┌──────────────────────────────┐            ┌───────────────────────────────┐
│ mic → Whisper (local) →      │  words     │ Supabase edge function        │
│ "Sayso …" → type into app    │  count ──▶ │ sayso-api: trial, license keys│
└──────────────────────────────┘            │ Postgres: devices, licenses   │
                                            └───────────────────────────────┘
GitHub: code + Actions builds the installer on every push, Releases host the download.
```

| Part | Where |
|---|---|
| Source code | this repo |
| Installer builds | GitHub Actions → `.github/workflows/build.yml` |
| Download | GitHub Releases (tag `v0.2.0` → `SaysoSetup-0.2.0.exe`) |
| Trial + licenses | Supabase project **Sayso** (`laeitoulfslncjyolkpg`), function `sayso-api`, SQL in `supabase/` |
| On the user's PC | app in `%LOCALAPPDATA%\Programs\Sayso`, settings/models/log in `%APPDATA%\Sayso` |

## Issuing a license key (until payments are wired up)
In Supabase → SQL editor:
```sql
insert into licenses (key, email, seats, source) values ('SAYSO-XXXX-XXXX-XXXX', 'customer@email.com', 3, 'manual');
```
The customer pastes the key into Settings → Account → Activate.

## Developing
- `run_dev.bat`: run from source (needs Python 3.11).
- `build.bat`: build `Sayso.exe` locally (and the installer if Inno Setup 6 is installed).
- `python -m pytest`: tests (no mic or Windows needed).

| File | What it does |
|---|---|
| `sayso/engine.py` | Mic → detect speech → wake word check → transcribe → act |
| `sayso/wake.py` | Fuzzy match of the wake word at the start of what was said |
| `sayso/commands.py` | Turns a transcript into an action ("send", "open X", …) |
| `sayso/actions_win.py` | Paste, keys, window switching |
| `sayso/license.py` | Trial / license client, offline-friendly |
| `sayso/app.py` | Tray icon and wiring |
| `sayso/settings_ui.py` | Settings + welcome window |

## Not built yet
Payments (Stripe checkout → license key email), auto-update, code signing, website, Mac.
