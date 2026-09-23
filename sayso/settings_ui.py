"""Settings + welcome window (tkinter - ships with Python, nothing extra to install)."""
import os
import threading
import tkinter as tk
import webbrowser
from dataclasses import replace
from tkinter import ttk

from sayso import APP_NAME, __version__
from sayso.config import PTT_KEYS, STT_MODELS, Config, data_dir
from sayso.license import BUY_URL

PAD = {"padx": 14, "pady": 4}
MUTED = "#6b6b6b"


def _label_for(mapping: dict, value, default: str) -> str:
    return next((label for label, v in mapping.items() if v == value), default)


def _input_devices():
    try:
        import sounddevice as sd
        hostapis = sd.query_hostapis()
        # MME lists each mic once with its friendly name; skip duplicate WDM/WASAPI entries
        return [(d["name"], i) for i, d in enumerate(sd.query_devices())
                if d["max_input_channels"] > 0 and hostapis[d["hostapi"]]["name"] == "MME"]
    except Exception:
        return []


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: Config, engine, license, on_save, welcome: bool = False):
        self.root, self.cfg, self.engine, self.license, self.on_save = root, cfg, engine, license, on_save
        self.win = w = tk.Toplevel(root)
        w.title(f"{APP_NAME}")
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.after(400, lambda: w.attributes("-topmost", False))
        try:
            w.iconbitmap(default=os.path.join(os.path.dirname(__file__), "sayso.ico"))
        except Exception:
            pass

        body = ttk.Frame(w, padding=(0, 6, 0, 0))
        body.grid(row=0, column=0, sticky="nsew")
        r = 0

        if welcome:
            ttk.Label(body, text=f"Welcome to {APP_NAME}", font=("Segoe UI", 15, "bold")).grid(
                row=r, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 2)); r += 1
            ptt = _label_for(PTT_KEYS, cfg.ptt_key, "Right Ctrl")
            tips = (f'Click into any text box and say  "{cfg.wake_word}, hello world".\n'
                    f'End with "{cfg.send_word}" to press Enter.   "{cfg.wake_word}, open Chrome" switches apps.\n'
                    f"Or hold {ptt} and talk - it types when you let go.\n"
                    "Your voice never leaves this PC.")
            ttk.Label(body, text=tips, justify="left").grid(row=r, column=0, columnspan=2, sticky="w", **PAD); r += 1

        def section(text):
            nonlocal r
            ttk.Label(body, text=text, font=("Segoe UI", 10, "bold")).grid(
                row=r, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 2))
            r += 1

        def row(label, widget):
            nonlocal r
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", **PAD)
            widget.grid(row=r, column=1, sticky="w", **PAD)
            r += 1

        # ---- Account ----
        section("Account")
        self.account_lbl = ttk.Label(body, text=license.summary() if license else "")
        self.account_lbl.grid(row=r, column=0, columnspan=2, sticky="w", **PAD); r += 1
        acct = ttk.Frame(body)
        acct.grid(row=r, column=0, columnspan=2, sticky="w", **PAD); r += 1
        self.key = tk.StringVar()
        self.key_entry = ttk.Entry(acct, textvariable=self.key, width=26)
        self.activate_btn = ttk.Button(acct, text="Activate key", command=self.activate)
        self.buy_btn = ttk.Button(acct, text="Get Sayso Pro", command=lambda: webbrowser.open(BUY_URL))
        self.key_entry.pack(side="left")
        self.activate_btn.pack(side="left", padx=6)
        self.buy_btn.pack(side="left")
        self.acct_msg = ttk.Label(body, text="", foreground=MUTED)
        self.acct_msg.grid(row=r, column=0, columnspan=2, sticky="w", padx=14); r += 1
        if license and license.is_pro:
            self.key_entry.pack_forget()
            self.activate_btn.pack_forget()
            self.buy_btn.pack_forget()

        # ---- Microphone ----
        section("Microphone")
        self.devices = [("Windows default", None)] + _input_devices()
        self.mic = tk.StringVar(value=next((n for n, i in self.devices if i == cfg.mic_device), "Windows default"))
        ttk.Combobox(body, textvariable=self.mic, values=[n for n, _ in self.devices],
                     state="readonly", width=44).grid(row=r, column=0, columnspan=2, sticky="w", **PAD); r += 1
        meter = ttk.Frame(body)
        meter.grid(row=r, column=0, columnspan=2, sticky="w", **PAD); r += 1
        self.meter = ttk.Progressbar(meter, length=250, maximum=100)
        self.meter.pack(side="left")
        ttk.Label(meter, text="  talk - the bar should move", foreground=MUTED).pack(side="left")
        self.noise = tk.DoubleVar(value=cfg.silence_level)
        n = ttk.Frame(body)
        ttk.Label(n, text="picks up quiet voices", foreground=MUTED).pack(side="left")
        ttk.Scale(n, from_=0.005, to=0.05, variable=self.noise, length=120).pack(side="left", padx=4)
        ttk.Label(n, text="ignores noise", foreground=MUTED).pack(side="left")
        row("Noisy room?", n)

        # ---- Hands-free ----
        section("Hands-free")
        self.hands_free = tk.BooleanVar(value=cfg.hands_free)
        ttk.Checkbutton(body, text="Listen for the wake word", variable=self.hands_free).grid(
            row=r, column=0, columnspan=2, sticky="w", **PAD); r += 1
        self.wake = tk.StringVar(value=cfg.wake_word)
        row("Wake word", ttk.Entry(body, textvariable=self.wake, width=18))
        self.send_word = tk.StringVar(value=cfg.send_word)
        row("Word that presses Enter", ttk.Entry(body, textvariable=self.send_word, width=18))
        self.pause = tk.DoubleVar(value=cfg.silence_secs)
        p = ttk.Frame(body)
        self.pause_lbl = ttk.Label(p, width=5, text=f"{cfg.silence_secs:.1f}s")
        ttk.Scale(p, from_=0.6, to=2.5, variable=self.pause, length=150,
                  command=lambda _=None: self.pause_lbl.config(text=f"{self.pause.get():.1f}s")).pack(side="left")
        self.pause_lbl.pack(side="left", padx=4)
        row("Pause that ends a phrase", p)

        # ---- Hold-to-talk ----
        section("Hold-to-talk")
        self.ptt = tk.StringVar(value=_label_for(PTT_KEYS, cfg.ptt_key, "Right Ctrl"))
        row("Hold this key to dictate",
            ttk.Combobox(body, textvariable=self.ptt, values=list(PTT_KEYS), state="readonly", width=16))

        # ---- General ----
        section("General")
        self.model = tk.StringVar(value=_label_for(STT_MODELS, cfg.stt_model, "Balanced (base)"))
        row("Speed vs accuracy",
            ttk.Combobox(body, textvariable=self.model, values=list(STT_MODELS), state="readonly", width=16))
        self.beeps = tk.BooleanVar(value=cfg.beeps)
        ttk.Checkbutton(body, text="Beep when I start listening", variable=self.beeps).grid(
            row=r, column=0, columnspan=2, sticky="w", **PAD); r += 1
        self.autostart = tk.BooleanVar(value=cfg.launch_at_startup)
        ttk.Checkbutton(body, text=f"Start {APP_NAME} when Windows starts", variable=self.autostart).grid(
            row=r, column=0, columnspan=2, sticky="w", **PAD); r += 1

        # ---- Buttons ----
        b = ttk.Frame(w, padding=(14, 14))
        b.grid(row=1, column=0, sticky="we")
        ttk.Label(b, text=f"v{__version__}", foreground="#999").pack(side="left")
        ttk.Button(b, text="Save", command=self.save).pack(side="right")
        ttk.Button(b, text="Cancel", command=w.destroy).pack(side="right", padx=6)
        ttk.Button(b, text="Log folder", command=lambda: os.startfile(data_dir())).pack(side="right")

        w.bind("<Escape>", lambda e: w.destroy())
        w.bind("<Return>", lambda e: self.save() if e.widget is not self.key_entry else self.activate())
        self._tick()

    def _tick(self):
        if not self.win.winfo_exists():
            return
        lvl = getattr(self.engine, "level", 0.0) if self.engine else 0.0
        self.meter["value"] = min(100, lvl * 1000)
        self.win.after(60, self._tick)

    def refresh_account(self):
        if self.win.winfo_exists() and self.license:
            self.account_lbl.config(text=self.license.summary())

    def activate(self):
        key = self.key.get().strip()
        if not key:
            self.acct_msg.config(text="Paste the key from your purchase email first.")
            return
        self.activate_btn.config(state="disabled")
        self.acct_msg.config(text="Checking...")

        def work():
            try:
                msg = self.license.activate(key)
                ok = True
            except ConnectionError:
                msg, ok = "Can't reach the internet - try again in a moment.", False
            except Exception as e:
                msg, ok = str(e), False
            self.root.after(0, lambda: self._activated(msg, ok))
        threading.Thread(target=work, daemon=True).start()

    def _activated(self, msg, ok):
        if not self.win.winfo_exists():
            return
        self.activate_btn.config(state="normal")
        self.acct_msg.config(text=msg)
        self.refresh_account()
        if ok:
            self.key_entry.pack_forget()
            self.activate_btn.pack_forget()
            self.buy_btn.pack_forget()

    def save(self):
        wake = " ".join(self.wake.get().split()) or "Sayso"
        new = replace(
            self.cfg,
            mic_device=dict(self.devices).get(self.mic.get()),
            silence_level=round(self.noise.get(), 3),
            hands_free=self.hands_free.get(),
            wake_word=wake[:30],
            silence_secs=round(self.pause.get(), 1),
            send_word=(self.send_word.get().strip() or "send").lower(),
            ptt_key=PTT_KEYS.get(self.ptt.get(), "ctrl_r"),
            stt_model=STT_MODELS.get(self.model.get(), "base.en"),
            beeps=self.beeps.get(),
            launch_at_startup=self.autostart.get(),
            first_run_done=True,
        )
        self.on_save(new)
        self.win.destroy()
