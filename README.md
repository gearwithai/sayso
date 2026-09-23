<p align="center">
  <img src="docs/icon.svg" width="72" alt="">
</p>
<h1 align="center">Sayso</h1>
<p align="center"><b>Type anywhere with your voice. Free, private, open source.</b><br>
Say "Sayso", then talk. Your words appear in whatever app you're in.</p>
<p align="center">
  <a href="https://gearwithai.github.io/sayso/"><b>Download for Windows</b></a> ·
  <a href="#your-own-voice-commands">Build on top of it</a> ·
  <a href="https://github.com/gearwithai/sayso/issues">Report a problem</a>
</p>

---

## Why Sayso
- **Hands-free.** No key to hold. Say *"Sayso, reply that I'll be there at 5. Send."* and it's typed and sent.
- **Works in every app:** email, Slack, WhatsApp, Word, VS Code, Cursor, ChatGPT, Claude, your CRM.
- **Private.** Speech is turned into text on your own PC with [Whisper](https://github.com/openai/whisper). Nothing you say is uploaded.
- **Free.** No subscription, no word limits. MIT licensed.
- **Yours to extend.** Your own words, snippets and voice commands in a simple JSON file.

## What you can say
| Say | What happens |
|---|---|
| "Sayso, hello world" | types "Hello world" |
| "Sayso, fix the login bug. Send." | types it, presses Enter |
| "Sayso" … *beep* … "call me back tomorrow" | wake first, then talk |
| "Sayso, see you then comma bye period" | "See you then, bye." (also: question mark, new line, new paragraph) |
| "Sayso, open Chrome" | switches to or opens any installed app |
| "Sayso, insert my email" | types a saved snippet |
| "Sayso, new tab" | runs your own command (Ctrl+T) |
| "Sayso, scratch that" · "send" · "new line" | undo · Enter · new line |
| "Sayso, stop listening" | pauses |
| Hold **Right Ctrl** and talk | types when you let go, no wake word |

"um" and "uh" are dropped and sentences get capitals automatically (you can switch that off).
Pick **Any language** in Settings to dictate in 90+ languages.

## Install
1. Go to **https://gearwithai.github.io/sayso/**, sign in with Google or GitHub, download `SaysoSetup.exe`.
2. Run it. Windows may say *"Windows protected your PC"* because Sayso is new. Click **More info → Run anyway**.
3. The one-time setup checks your mic and lets you choose which apps Sayso may type into. Then it starts with Windows and waits by the clock.

Needs Windows 10 or 11 (64-bit). The first launch downloads the speech model (~150 MB) once.

## Your own words, snippets and commands
Open Sayso → **Words**:
- **Your words:** "gear with ai" → `GearWithAI`. Sayso also uses these to spell names right.
- **Snippets:** name `email` → `you@company.com`, then say *"Sayso, insert my email"*.

### Your own voice commands
Words → **Edit commands** opens `%APPDATA%\Sayso\commands.json`. Add a phrase and one action:

```json
{
  "commands": [
    { "say": "new tab",       "keys": "ctrl+t" },
    { "say": "clear line",    "keys": ["home", "shift+end", "delete"] },
    { "say": "sign off",      "type": "Thanks,\nSunny" },
    { "say": "open my crm",   "url":  "https://app.gohighlevel.com" },
    { "say": "start music",   "run":  "spotify" }
  ]
}
```

| Action | Does | Example |
|---|---|---|
| `keys` | presses a key combo, or a list of them | `"ctrl+shift+t"`, `"win+d"`, `"f5"`, `"nexttrack"` |
| `type` | types text (`\n` = new line) | `"Best regards"` |
| `url` | opens a web page | `"https://calendar.google.com"` |
| `run` | starts a program, file or folder | `"notepad"`, `"C:\\Reports"` |

Save the file and it works straight away. Say *"Sayso, new tab"*.
Share your best command packs in [Discussions](https://github.com/gearwithai/sayso/discussions) or send a PR adding one to `packs/`.

## Privacy
- Your voice and what you type never leave your PC. History is stored only on your PC (`%APPDATA%\Sayso`) and can be cleared from the Home tab.
- The download page asks you to sign in so we can count downloads; it stores your name and email. Nothing else.
- The app itself only contacts GitHub to check for updates.

## How it works
```
mic → speech detected → Whisper (on your PC) reads the first 2.5 s
    → starts with "Sayso"? → command, snippet or text → cleaned up → pasted into the app in front
```

| File | What it does |
|---|---|
| `sayso/engine.py` | Listening loop: wake word, hold-to-talk |
| `sayso/wake.py` | Fuzzy wake-word match ("Say so", "Say-so", …) |
| `sayso/commands.py` | Transcript → action |
| `sayso/text.py` | Drop fillers, spoken punctuation, your words, capitals |
| `sayso/custom.py` | `commands.json` loader and validator |
| `sayso/apps.py` | Installed apps, per-app on/off, open apps by name |
| `sayso/actions_win.py` | Paste, keys, windows |
| `sayso/ui.py` | The window (customtkinter) |
| `sayso/app.py` | Tray icon, settings, history, update check |

## Contributing
PRs welcome. Ideas: macOS/Linux support, GPU acceleration, more languages for commands, command packs, a trained "Hey Sayso" wake word. See [CONTRIBUTING.md](CONTRIBUTING.md).

- `run_dev.bat`: run from source (Python 3.11)
- `python -m pytest`: tests (no mic or Windows needed)
- Releases: bump `sayso/__init__.py`, publish a GitHub release, and Actions builds and attaches `SaysoSetup.exe`.

## License
MIT © GearWithAI. Built by [GearWithAI](https://gearwithai.com).
