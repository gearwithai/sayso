"""The small Sayso window: one-time setup, then Home / Apps / Settings / Commands.

Everything saves as you change it - there is no Save button.
Closing the window just hides it; Sayso keeps running in the tray.
"""
import os
from dataclasses import replace

import customtkinter as ctk

from sayso import APP_NAME, __version__
from sayso.ai import PROVIDERS, BY_ID
from sayso.config import LANGUAGES, PTT_KEYS, STT_MODELS, data_dir

ACCENT = ("#6E56CF", "#8B7BE0")
ACCENT_HOVER = ("#5B45B8", "#7A69D6")
MUTED = ("#6B6B76", "#A1A1AA")
CARD = ("#F4F3F8", "#24232B")
W, H = 460, 660

STATUS = {
    "loading": ("Getting ready...", "#5B8DEF"),
    "ready": ('Say "{wake}" to start', "#6E56CF"),
    "listening": ("Listening...", "#E5484D"),
    "thinking": ("Working...", "#F5A524"),
    "dictating": ("Dictation mode - just talk", "#30A46C"),
    "paused": ("Paused", "#9A9A9A"),
    "error": ("Needs attention", "#E5484D"),
}

COMMANDS = [
    ("Sayso, hello world", "types \"hello world\""),
    ("Sayso, fix the login bug. Send.", "types it, then presses Enter"),
    ("Sayso", "beep - then say what to type"),
    ("Sayso, start dictation", "type everything you say, no wake word (\"that's all\" to stop)"),
    ("Sayso, make that more professional", "AI rewrites the selected text (or what Sayso just typed)"),
    ("Sayso, translate this to Spanish", "AI translates the selection in place"),
    ("Sayso, write a reply saying I'll be there at 5", "AI writes it at the cursor (select their message for context)"),
    ("Sayso, fix the grammar", "AI proofreads the selection"),
    ("Sayso, send", "presses Enter"),
    ("Sayso, new line", "starts a new line"),
    ("Sayso, scratch that", "undoes the last thing"),
    ("Sayso, open Chrome", "switches to (or opens) an app"),
    ("Sayso, stop listening", "pauses until you turn it back on"),
    ("Sayso, insert my email", "types a saved snippet (Words tab)"),
    ("Sayso, new tab", "your own commands (Words tab)"),
    ("Sayso, see you then comma bye", "say punctuation: comma, question mark, new line"),
    ("Hold Right Ctrl and talk", "types when you let go - no wake word"),
    ("Sayso, what can I say", "opens this list"),
]


def font(size=13, weight="normal"):
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


def _label_for(mapping: dict, value, default: str) -> str:
    return next((label for label, v in mapping.items() if v == value), default)


def input_devices():
    try:
        import sounddevice as sd
        hostapis = sd.query_hostapis()
        # MME lists each mic once with its friendly name; skip duplicate WDM/WASAPI entries
        return [(d["name"], i) for i, d in enumerate(sd.query_devices())
                if d["max_input_channels"] > 0 and hostapis[d["hostapi"]]["name"] == "MME"]
    except Exception:
        return []


def open_mic_privacy():
    try:
        os.startfile("ms-settings:privacy-microphone")
    except Exception:
        pass


class MicMeter(ctk.CTkFrame):
    """Live mic level + a hint when Windows is blocking the mic."""

    def __init__(self, master, engine, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.engine = engine
        self.bar = ctk.CTkProgressBar(self, height=10, progress_color=ACCENT)
        self.bar.pack(fill="x")
        self.bar.set(0)
        self.hint = ctk.CTkLabel(self, text="Talk - the bar should move.", font=font(12), text_color=MUTED)
        self.hint.pack(anchor="w", pady=(4, 0))
        self.fix = ctk.CTkButton(self, text="Allow microphone in Windows", height=28, font=font(12),
                                 fg_color="transparent", border_width=1, border_color=ACCENT,
                                 text_color=ACCENT, hover_color=CARD, command=open_mic_privacy)
        self.silent_ticks = 0
        self._tick()

    def _tick(self):
        if not self.winfo_exists():
            return
        lvl = getattr(self.engine, "level", 0.0)
        self.bar.set(min(1.0, lvl * 10))
        # exact zeros for ~3 s usually means Windows privacy settings block desktop apps
        self.silent_ticks = self.silent_ticks + 1 if lvl == 0.0 else 0
        blocked = self.silent_ticks > 40 and getattr(self.engine, "state", "") not in ("loading",)
        if blocked and not self.fix.winfo_ismapped():
            self.hint.configure(text="No sound from the mic. Windows may be blocking it.")
            self.fix.pack(anchor="w", pady=(6, 0))
        elif not blocked and self.fix.winfo_ismapped():
            self.hint.configure(text="Talk - the bar should move.")
            self.fix.pack_forget()
        self.after(80, self._tick)


class AppList(ctk.CTkFrame):
    """Search + a switch per installed app."""

    def __init__(self, master, ctl, height=330, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.ctl = ctl
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        self.search = ctk.CTkEntry(top, placeholder_text="Search apps", height=32, font=font())
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind("<KeyRelease>", lambda _: self._filter())
        ctk.CTkButton(top, text="All on", width=64, height=32, font=font(12), fg_color=CARD,
                      text_color=("black", "white"), hover_color=ACCENT_HOVER,
                      command=lambda: self._set_all(True)).pack(side="left", padx=(6, 0))
        ctk.CTkButton(top, text="Refresh", width=70, height=32, font=font(12), fg_color=CARD,
                      text_color=("black", "white"), hover_color=ACCENT_HOVER,
                      command=self.ctl.rescan_apps).pack(side="left", padx=(6, 0))
        self.count = ctk.CTkLabel(self, text="", font=font(12), text_color=MUTED)
        self.count.pack(anchor="w", pady=(6, 2))
        self.box = ctk.CTkScrollableFrame(self, height=height, fg_color=CARD, corner_radius=10)
        self.box.pack(fill="both", expand=True)
        self.rows = []
        self.render()

    def render(self):
        for row, *_ in self.rows:
            row.destroy()
        self.rows = []
        apps = self.ctl.apps
        if not apps:
            self.count.configure(text="Finding your apps..." if self.ctl.scanning else "No apps found - try Refresh.")
            return
        disabled = set(self.ctl.cfg.disabled_apps)
        for app in apps:
            row = ctk.CTkFrame(self.box, fg_color="transparent")
            var = ctk.BooleanVar(value=app.id not in disabled)
            ctk.CTkLabel(row, text=app.name, font=font(13), anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkSwitch(row, text="", width=46, variable=var, progress_color=ACCENT,
                          command=lambda a=app, v=var: self.ctl.set_app_enabled(a.id, v.get())
                          ).pack(side="right")
            self.rows.append((row, app, var))
        self._filter()

    def _filter(self):
        q = self.search.get().lower().strip()
        shown = 0
        for row, app, _ in self.rows:
            if not q or q in app.name.lower():
                row.pack(fill="x", padx=6, pady=2)
                shown += 1
            else:
                row.pack_forget()
        on = sum(1 for _, _, v in self.rows if v.get())
        self.count.configure(text=f"{on} of {len(self.rows)} apps on" + (f"  -  showing {shown}" if q else ""))

    def _set_all(self, value: bool):
        for _, _, v in self.rows:
            v.set(value)
        self.ctl.set_all_apps_enabled(value)
        self._filter()


class WordsTab(ctk.CTkFrame):
    """Your words (said -> typed), snippets ("insert my email") and your own voice commands."""

    def __init__(self, master, ctl):
        super().__init__(master, fg_color="transparent")
        self.ctl = ctl
        s = ctk.CTkScrollableFrame(self, fg_color="transparent")
        s.pack(fill="both", expand=True)
        self.lists = {}
        self._section(s, "replacements", "Your words",
                      "Names and terms Sayso should spell your way.", "When I say", "Type")
        self._section(s, "snippets", "Snippets",
                      "Say \"Sayso, insert <name>\". Use \\n for a new line.", "Name", "Text")

        ctk.CTkLabel(s, text="Your own voice commands", font=font(14, "bold")).pack(anchor="w", pady=(16, 0))
        n = len(ctl.custom.get())
        probs = ctl.custom.problems
        ctk.CTkLabel(s, text=f"{n} commands loaded from commands.json" + (f"  -  {len(probs)} need fixing" if probs else "")
                     + "\nPress keys, type text, open a web page or start a program.",
                     font=font(12), text_color=MUTED, justify="left").pack(anchor="w", pady=(2, 6))
        b = ctk.CTkFrame(s, fg_color="transparent")
        b.pack(anchor="w")
        ctk.CTkButton(b, text="Edit commands", width=130, height=30, font=font(13), fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=ctl.custom.open_file).pack(side="left")
        ctk.CTkButton(b, text="How it works", width=110, height=30, font=font(13), fg_color=CARD,
                      text_color=("black", "white"), hover_color=ACCENT_HOVER,
                      command=lambda: __import__("webbrowser").open(
                          "https://github.com/gearwithai/sayso#your-own-voice-commands")).pack(side="left", padx=8)

    def _section(self, parent, key, title, hint, left, right):
        ctk.CTkLabel(parent, text=title, font=font(14, "bold")).pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(parent, text=hint, font=font(12), text_color=MUTED).pack(anchor="w", pady=(0, 4))
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=left, width=150, anchor="w", font=font(12), text_color=MUTED).pack(side="left")
        ctk.CTkLabel(head, text=right, anchor="w", font=font(12), text_color=MUTED).pack(side="left", padx=(8, 0))
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x")
        self.lists[key] = (box, [])
        for said, typed in getattr(self.ctl.cfg, key).items():
            self._row(key, said, typed.replace("\n", "\\n"))
        ctk.CTkButton(parent, text="+ Add", width=70, height=26, font=font(12), fg_color=CARD,
                      text_color=("black", "white"), hover_color=ACCENT_HOVER,
                      command=lambda: self._row(key, "", "", focus=True)).pack(anchor="w", pady=(4, 0))

    def _row(self, key, a, b, focus=False):
        box, rows = self.lists[key]
        r = ctk.CTkFrame(box, fg_color="transparent")
        r.pack(fill="x", pady=2)
        ea = ctk.CTkEntry(r, width=150, font=font(13))
        eb = ctk.CTkEntry(r, font=font(13))
        ea.insert(0, a)
        eb.insert(0, b)
        ea.pack(side="left")
        eb.pack(side="left", fill="x", expand=True, padx=(8, 6))
        item = (r, ea, eb)
        ctk.CTkButton(r, text="\u2715", width=28, height=28, font=font(12), fg_color="transparent",
                      text_color=MUTED, hover_color=CARD,
                      command=lambda: self._remove(key, item)).pack(side="right")
        for e in (ea, eb):
            e.bind("<FocusOut>", lambda _: self._save(key))
            e.bind("<Return>", lambda _: self._save(key))
        rows.append(item)
        if focus:
            ea.focus_set()

    def _remove(self, key, item):
        box, rows = self.lists[key]
        rows.remove(item)
        item[0].destroy()
        self._save(key)

    def _save(self, key):
        _, rows = self.lists[key]
        data = {}
        for _, ea, eb in rows:
            a, b = " ".join(ea.get().split()), eb.get().strip()
            if a and b:
                data[a.lower()] = b.replace("\\n", "\n")
        if data != getattr(self.ctl.cfg, key):
            self.ctl.update_cfg(**{key: data})


class Wizard(ctk.CTkFrame):
    """One-time setup: microphone -> apps -> try it."""

    def __init__(self, master, ctl, on_done):
        super().__init__(master, fg_color="transparent")
        self.ctl, self.on_done, self.step = ctl, on_done, 0
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=22, pady=(10, 0))
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=22, pady=16)
        self.dots = ctk.CTkLabel(nav, text="", font=font(14), text_color=MUTED)
        self.dots.pack(side="left")
        self.next = ctk.CTkButton(nav, text="Next", width=110, height=36, font=font(14, "bold"),
                                  fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.forward)
        self.next.pack(side="right")
        self.back = ctk.CTkButton(nav, text="Back", width=80, height=36, font=font(13),
                                  fg_color="transparent", text_color=MUTED, hover_color=CARD,
                                  command=self.backward)
        self.show()

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def show(self):
        self._clear()
        b, ctl = self.body, self.ctl
        self.dots.configure(text="  ".join("●" if i == self.step else "○" for i in range(3)))
        if self.step:
            self.back.pack(side="right", padx=8)
        else:
            self.back.pack_forget()

        if self.step == 0:
            ctk.CTkLabel(b, text="Welcome to Sayso", font=font(24, "bold")).pack(anchor="w")
            ctk.CTkLabel(b, text="Type anywhere with your voice. Say \"Sayso\", then what you want typed.\n"
                                 "Your voice is processed on this PC and never uploaded.",
                         font=font(13), text_color=MUTED, justify="left", wraplength=410).pack(anchor="w", pady=(4, 18))
            ctk.CTkLabel(b, text="1. Your microphone", font=font(15, "bold")).pack(anchor="w")
            devices = [("Windows default", None)] + input_devices()
            names = [n for n, _ in devices]
            cur = next((n for n, i in devices if i == ctl.cfg.mic_device), "Windows default")
            menu = ctk.CTkOptionMenu(b, values=names, font=font(13), fg_color=ACCENT, button_color=ACCENT,
                                     button_hover_color=ACCENT_HOVER, dynamic_resizing=False, width=400,
                                     command=lambda n: ctl.update_cfg(mic_device=dict(devices).get(n)))
            menu.set(cur)
            menu.pack(anchor="w", pady=(8, 10))
            MicMeter(b, ctl.engine).pack(fill="x")
            if ctl.engine.state == "loading":
                ctk.CTkLabel(b, text="Downloading the speech model (about 150 MB, first time only)...",
                             font=font(12), text_color=MUTED).pack(anchor="w", pady=(14, 0))
            self.next.configure(text="Next")

        elif self.step == 1:
            ctk.CTkLabel(b, text="2. Where should Sayso type?", font=font(15, "bold")).pack(anchor="w")
            ctk.CTkLabel(b, text="Everything is on. Turn off apps where you never want it to type.\n"
                                 "You can change this any time.",
                         font=font(12), text_color=MUTED, justify="left").pack(anchor="w", pady=(2, 10))
            AppList(b, ctl, height=330).pack(fill="both", expand=True)
            self.next.configure(text="Next")

        else:
            ctk.CTkLabel(b, text="3. Try it", font=font(15, "bold")).pack(anchor="w")
            ctk.CTkLabel(b, text="Open Notepad (or any chat box), click into it, and say:",
                         font=font(13), text_color=MUTED).pack(anchor="w", pady=(4, 10))
            for said, does in COMMANDS[:3]:
                card = ctk.CTkFrame(b, fg_color=CARD, corner_radius=10)
                card.pack(fill="x", pady=4)
                ctk.CTkLabel(card, text=f"“{said}”", font=font(14, "bold")).pack(anchor="w", padx=14, pady=(10, 0))
                ctk.CTkLabel(card, text=does, font=font(12), text_color=MUTED).pack(anchor="w", padx=14, pady=(0, 10))
            ctk.CTkLabel(b, text="Sayso lives by the clock (the microphone icon). Click it any time\n"
                                 "to open this window. It starts with Windows - no setup again.",
                         font=font(12), text_color=MUTED, justify="left").pack(anchor="w", pady=(14, 0))
            self.next.configure(text="Done")

    def forward(self):
        if self.step < 2:
            self.step += 1
            self.show()
        else:
            self.on_done()

    def backward(self):
        self.step = max(0, self.step - 1)
        self.show()


class Bubble:
    """A small pill above the taskbar that shows what Sayso is doing - so you never have to guess.
    It never takes focus (that would steal your typing), so on Windows it's shown with raw Win32 calls."""
    SHOW = {"listening", "thinking", "dictating", "error"}

    def __init__(self, root):
        self.root, self.win, self.hwnd, self._hide_job, self.visible = root, None, 0, None, False

    def build(self):
        if self.win is not None:
            return
        w = ctk.CTkToplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(fg_color="#1F1D26")
        f = ctk.CTkFrame(w, fg_color="#1F1D26", corner_radius=0)
        f.pack(fill="both", expand=True)
        self.dot = ctk.CTkLabel(f, text="\u25cf", font=font(14), text_color="#E5484D")
        self.dot.pack(side="left", padx=(14, 6), pady=8)
        self.text = ctk.CTkLabel(f, text="", font=font(13), text_color="#F4F3F8", wraplength=420, justify="left")
        self.text.pack(side="left", padx=(0, 16), pady=8)
        w.bind("<Button-1>", lambda _: self.hide())
        self.win = w
        if os.name == "nt":
            try:
                import ctypes
                u = ctypes.windll.user32
                w.geometry("+-3000+-3000")
                w.update_idletasks()
                w.update()
                self.hwnd = u.GetParent(w.winfo_id()) or w.winfo_id()
                ex = u.GetWindowLongW(self.hwnd, -20)
                # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW (no taskbar button) | WS_EX_TOPMOST
                u.SetWindowLongW(self.hwnd, -20, ex | 0x08000000 | 0x80 | 0x8)
                u.ShowWindow(self.hwnd, 0)
                try:
                    w.attributes("-alpha", 0.94)
                except Exception:
                    pass
            except Exception:
                self.hwnd = 0
        else:
            w.withdraw()

    def show(self, state: str, msg: str, status: str):
        try:
            self.build()
            if state not in self.SHOW and not (msg and self.visible):
                return self._later(0.1)
            color = STATUS.get(state, ("", "#6E56CF"))[1]
            line = status if state in ("listening", "dictating") or not msg else msg
            self.dot.configure(text_color=color)
            self.text.configure(text=line[:140])
            self.win.update_idletasks()
            w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
            sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
            x, y = (sw - w) // 2, sh - h - 90
            if self.hwnd:
                import ctypes
                # HWND_TOPMOST, SWP_NOACTIVATE | SWP_SHOWWINDOW
                ctypes.windll.user32.SetWindowPos(self.hwnd, -1, x, y, w, h, 0x10 | 0x40)
            else:
                self.win.geometry(f"{w}x{h}+{x}+{y}")
                self.win.deiconify()
            self.visible = True
            # stay up while it's working; fade out once there's nothing going on
            self._later(None if state in ("listening", "thinking", "dictating") else 2.8)
        except Exception:
            pass

    def _later(self, secs):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        if secs is not None:
            self._hide_job = self.root.after(int(secs * 1000), self.hide)

    def hide(self):
        self.visible = False
        if self.hwnd:
            import ctypes
            ctypes.windll.user32.ShowWindow(self.hwnd, 0)
        elif self.win is not None:
            self.win.withdraw()


class MainWindow(ctk.CTk):
    def __init__(self, ctl):
        ctk.set_appearance_mode("system")
        super().__init__()
        self.ctl = ctl
        self.title(APP_NAME)
        self.geometry(f"{W}x{H}")
        self.minsize(W, 560)
        try:
            self.iconbitmap(default=os.path.join(os.path.dirname(__file__), "sayso.ico"))
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self.hide)

        # ---- header: name, status, master switch ----
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(18, 6))
        left = ctk.CTkFrame(head, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text=APP_NAME, font=font(22, "bold")).pack(anchor="w")
        st = ctk.CTkFrame(left, fg_color="transparent")
        st.pack(anchor="w")
        self.dot = ctk.CTkLabel(st, text="●", font=font(14), text_color="#5B8DEF")
        self.dot.pack(side="left")
        self.status = ctk.CTkLabel(st, text="Getting ready...", font=font(13), text_color=MUTED)
        self.status.pack(side="left", padx=(4, 0))
        self.on_var = ctk.BooleanVar(value=not ctl.engine.paused)
        ctk.CTkSwitch(head, text="On", font=font(13), variable=self.on_var, progress_color=ACCENT,
                      switch_width=48, switch_height=24,
                      command=lambda: ctl.set_paused(not self.on_var.get())).pack(side="right")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True)
        self.app_list, self.tabs, self.ai_widgets = None, None, None
        self.bubble = Bubble(self)
        if ctl.cfg.first_run_done:
            self.build_tabs()
        else:
            Wizard(self.content, ctl, self.finish_setup).pack(fill="both", expand=True)

    # ---------- window ----------
    def show(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def hide(self):
        self.withdraw()

    def show_tab(self, name: str):
        self.show()
        if self.tabs is not None:
            try:
                self.tabs.set(name)
            except Exception:
                pass

    def clipboard_set(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)

    def finish_setup(self):
        self.ctl.update_cfg(first_run_done=True)
        for w in self.content.winfo_children():
            w.destroy()
        self.build_tabs()
        self.ctl.notify("Sayso is ready. Say \"Sayso\" in any app.")
        self.hide()

    # ---------- tabs ----------
    def build_tabs(self):
        tabs = ctk.CTkTabview(self.content, fg_color="transparent", segmented_button_selected_color=ACCENT,
                              segmented_button_selected_hover_color=ACCENT_HOVER)
        tabs.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.tabs = tabs
        for name in ("Home", "Apps", "Words", "Settings", "Commands"):
            tabs.add(name)
        self._home(tabs.tab("Home"))
        self.app_list = AppList(tabs.tab("Apps"), self.ctl, height=420)
        self.app_list.pack(fill="both", expand=True, padx=4, pady=4)
        WordsTab(tabs.tab("Words"), self.ctl).pack(fill="both", expand=True)
        self._settings(tabs.tab("Settings"))
        self._commands(tabs.tab("Commands"))

    def _home(self, t):
        card = ctk.CTkFrame(t, fg_color=CARD, corner_radius=12)
        card.pack(fill="x", padx=4, pady=(6, 10))
        self.big = ctk.CTkLabel(card, text="", font=font(18, "bold"))
        self.big.pack(anchor="w", padx=16, pady=(14, 0))
        self.last = ctk.CTkLabel(card, text="", font=font(12), text_color=MUTED, wraplength=380, justify="left")
        self.last.pack(anchor="w", padx=16, pady=(2, 14))
        ctk.CTkLabel(t, text="Microphone", font=font(13, "bold")).pack(anchor="w", padx=6)
        MicMeter(t, self.ctl.engine).pack(fill="x", padx=6, pady=(4, 12))
        self.words = ctk.CTkLabel(t, text="", font=font(13))
        self.words.pack(anchor="w", padx=6)
        head = ctk.CTkFrame(t, fg_color="transparent")
        head.pack(fill="x", padx=6, pady=(14, 4))
        self.hist_title = ctk.CTkLabel(head, text="", font=font(13, "bold"))
        self.hist_title.pack(side="left")
        self.hist_clear = ctk.CTkButton(head, text="Clear", width=54, height=24, font=font(12), fg_color=CARD,
                                        text_color=("black", "white"), hover_color=ACCENT_HOVER,
                                        command=self.ctl.clear_history)
        self.hist_box = ctk.CTkScrollableFrame(t, height=190, fg_color="transparent")
        self.hist_box.pack(fill="both", expand=True, padx=2)
        self.refresh_home()

    def _settings(self, t):
        ctl, cfg = self.ctl, self.ctl.cfg
        s = ctk.CTkScrollableFrame(t, fg_color="transparent")
        s.pack(fill="both", expand=True)

        def section(text):
            ctk.CTkLabel(s, text=text, font=font(14, "bold")).pack(anchor="w", pady=(12, 4))

        def row(label, widget_factory):
            r = ctk.CTkFrame(s, fg_color="transparent")
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=label, font=font(13)).pack(side="left")
            widget_factory(r).pack(side="right")

        def switch(label, key):
            var = ctk.BooleanVar(value=getattr(cfg, key))
            ctk.CTkSwitch(s, text=label, font=font(13), variable=var, progress_color=ACCENT,
                          command=lambda: ctl.update_cfg(**{key: var.get()})).pack(anchor="w", pady=4)

        def menu(r, mapping, current, key):
            m = ctk.CTkOptionMenu(r, values=list(mapping), width=170, font=font(13), fg_color=ACCENT,
                                  button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                                  command=lambda label: ctl.update_cfg(**{key: mapping[label]}))
            m.set(_label_for(mapping, current, list(mapping)[0]))
            return m

        def entry(r, key, width=170):
            var = ctk.StringVar(value=getattr(cfg, key))
            e = ctk.CTkEntry(r, textvariable=var, width=width, font=font(13))

            def commit(_=None):
                v = " ".join(var.get().split())
                if v and v != getattr(ctl.cfg, key):
                    ctl.update_cfg(**{key: v.lower() if key == "send_word" else v[:30]})
            e.bind("<FocusOut>", commit)
            e.bind("<Return>", commit)
            return e

        def slider(r, key, lo, hi, fmt):
            f = ctk.CTkFrame(r, fg_color="transparent")
            lbl = ctk.CTkLabel(f, text=fmt(getattr(cfg, key)), width=50, font=font(12), text_color=MUTED)
            sl = ctk.CTkSlider(f, from_=lo, to=hi, width=130, button_color=ACCENT, progress_color=ACCENT,
                               command=lambda v: lbl.configure(text=fmt(v)))
            sl.set(getattr(cfg, key))
            sl.bind("<ButtonRelease-1>", lambda _: ctl.update_cfg(**{key: round(sl.get(), 3)}))
            sl.pack(side="left")
            lbl.pack(side="left", padx=(6, 0))
            return f

        section("Microphone")
        devices = [("Windows default", None)] + input_devices()
        dev_map = {n: i for n, i in devices}
        row("Mic", lambda r: menu(r, dev_map, cfg.mic_device, "mic_device"))
        row("Noisy room", lambda r: slider(r, "silence_level", 0.005, 0.05,
                                           lambda v: "quiet" if v < 0.012 else ("normal" if v < 0.025 else "noisy")))
        ctk.CTkButton(s, text="Windows microphone privacy settings", height=28, font=font(12),
                      fg_color="transparent", border_width=1, border_color=ACCENT, text_color=ACCENT,
                      hover_color=CARD, command=open_mic_privacy).pack(anchor="w", pady=(4, 0))

        section("Voice")
        switch("Listen for the wake word (hands-free)", "hands_free")
        row("Wake word", lambda r: entry(r, "wake_word"))
        row("Word that presses Enter", lambda r: entry(r, "send_word"))
        row("Pause that ends a phrase", lambda r: slider(r, "silence_secs", 0.6, 2.5, lambda v: f"{v:.1f}s"))
        row("Hold to talk", lambda r: menu(r, PTT_KEYS, cfg.ptt_key, "ptt_key"))
        row("Speed vs accuracy", lambda r: menu(r, STT_MODELS, cfg.stt_model, "stt_model"))
        row("Language", lambda r: menu(r, LANGUAGES, cfg.language, "language"))
        switch("Tidy up text (drop \"um\", spoken punctuation, capitals)", "cleanup")

        section("Smart typing")
        switch("Match the app (terminals, chats, documents)", "smart_format")
        switch("Carry on a sentence when you pause mid-thought", "smart_continue")
        switch("Show a status bubble above the taskbar", "show_bubble")
        switch("Use my NVIDIA graphics card (faster)", "use_gpu")

        self._ai_section(s, section, row)

        section("General")
        switch("Beep when Sayso starts listening", "beeps")
        switch("Start Sayso when Windows starts", "launch_at_startup")
        theme = {"Match Windows": "system", "Light": "light", "Dark": "dark"}
        row("Look", lambda r: ctk.CTkOptionMenu(r, values=list(theme), width=170, font=font(13), fg_color=ACCENT,
                                                button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                                                command=lambda l: ctk.set_appearance_mode(theme[l])))

        foot = ctk.CTkFrame(s, fg_color="transparent")
        foot.pack(fill="x", pady=(18, 6))
        ctk.CTkLabel(foot, text=f"Sayso {__version__}  -  free and open source", font=font(12),
                     text_color=MUTED).pack(side="left")
        ctk.CTkButton(foot, text="Logs", width=60, height=26, font=font(12), fg_color=CARD,
                      text_color=("black", "white"), hover_color=ACCENT_HOVER,
                      command=lambda: os.startfile(data_dir())).pack(side="right")

    def _ai_section(self, s, section, row):
        ctl, cfg = self.ctl, self.ctl.cfg
        section("AI voice actions")
        ctk.CTkLabel(s, text="\"Sayso, make that more professional\", \"translate this to Spanish\",\n"
                             "\"write a reply saying...\". Free and private with Ollama on this PC,\n"
                             "or bring your own key. Your key is encrypted by Windows.",
                     font=font(12), text_color=MUTED, justify="left").pack(anchor="w")
        choices = {"Automatic (find AI on this PC)": "auto"}
        choices.update({label: pid for label, (pid, *_rest) in PROVIDERS.items()})
        widgets = {}

        def pick(label):
            pid = choices[label]
            if pid != ctl.cfg.ai_provider:
                ctl.update_cfg(ai_provider=pid, ai_model="", ai_base_url="")
            refresh()

        def refresh():
            pid = ctl.cfg.ai_provider
            info = BY_ID.get(pid)
            needs_key = bool(info and info[2])
            widgets["model"].delete(0, "end")
            widgets["model"].insert(0, ctl.cfg.ai_model or (info[3] if info else ""))
            widgets["url"].delete(0, "end")
            widgets["url"].insert(0, ctl.cfg.ai_base_url or (info[1] if info else ""))
            widgets["key"].configure(placeholder_text="saved - paste to replace" if ctl.cfg.ai_key else "paste your API key")
            for w in box.winfo_children():
                w.pack_forget()
            if pid not in ("auto", "off"):
                widgets["model_row"].pack(fill="x", pady=3)
                widgets["url_row"].pack(fill="x", pady=3)
            if needs_key:
                widgets["key_row"].pack(fill="x", pady=3)
            widgets["buttons"].pack(anchor="w", pady=(6, 0))
            widgets["status"].pack(anchor="w", pady=(4, 0))

        r = ctk.CTkFrame(s, fg_color="transparent")
        r.pack(fill="x", pady=(8, 3))
        ctk.CTkLabel(r, text="AI", font=font(13)).pack(side="left")
        m = ctk.CTkOptionMenu(r, values=list(choices), width=270, font=font(12), fg_color=ACCENT,
                              button_color=ACCENT, button_hover_color=ACCENT_HOVER, dynamic_resizing=False,
                              command=pick)
        m.set(_label_for(choices, cfg.ai_provider, list(choices)[0]))
        m.pack(side="right")
        box = ctk.CTkFrame(s, fg_color="transparent")
        box.pack(fill="x")

        def field(key, label, commit, show=None):
            fr = ctk.CTkFrame(box, fg_color="transparent")
            ctk.CTkLabel(fr, text=label, font=font(13)).pack(side="left")
            e = ctk.CTkEntry(fr, width=270, font=font(12), show=show)
            e.pack(side="right")
            e.bind("<FocusOut>", lambda _: commit(e.get().strip()))
            e.bind("<Return>", lambda _: commit(e.get().strip()))
            widgets[key], widgets[key + "_row"] = e, fr

        def set_if_changed(k, v):
            if v != getattr(ctl.cfg, k):
                ctl.update_cfg(**{k: v})

        def set_key(v):
            if v:
                ctl.set_ai_key(v)
                widgets["key"].delete(0, "end")
                widgets["key"].configure(placeholder_text="saved - paste to replace")

        field("model", "Model", lambda v: set_if_changed("ai_model", v))
        field("url", "Server", lambda v: set_if_changed("ai_base_url", v))
        field("key", "API key", set_key, show="\u2022")

        b = ctk.CTkFrame(box, fg_color="transparent")
        status = ctk.CTkLabel(box, text=ctl.ai_status, font=font(12), text_color=MUTED, wraplength=400, justify="left")

        def test():
            status.configure(text="Testing...")
            ctl.test_ai(lambda ok, msg: status.configure(text=msg, text_color=("#1E7F4F", "#4CC38A") if ok else "#E5484D"))
        ctk.CTkButton(b, text="Test", width=80, height=28, font=font(12), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=test).pack(side="left")
        ctk.CTkButton(b, text="Get Ollama (free)", width=130, height=28, font=font(12), fg_color=CARD,
                      text_color=("black", "white"), hover_color=ACCENT_HOVER,
                      command=lambda: __import__("webbrowser").open("https://ollama.com/download")).pack(side="left", padx=8)
        ctk.CTkButton(b, text="Look again", width=90, height=28, font=font(12), fg_color=CARD,
                      text_color=("black", "white"), hover_color=ACCENT_HOVER,
                      command=lambda: __import__("threading").Thread(target=ctl.setup_ai, daemon=True).start()
                      ).pack(side="left")
        widgets["buttons"], widgets["status"] = b, status
        self.ai_widgets = widgets
        refresh()

    def ai_changed(self):
        if self.ai_widgets:
            self.ai_widgets["status"].configure(text=self.ctl.ai_status, text_color=MUTED)

    def _commands(self, t):
        s = ctk.CTkScrollableFrame(t, fg_color="transparent")
        s.pack(fill="both", expand=True)
        for said, does in COMMANDS:
            card = ctk.CTkFrame(s, fg_color=CARD, corner_radius=10)
            card.pack(fill="x", pady=4, padx=2)
            ctk.CTkLabel(card, text=f"“{said}”", font=font(14, "bold")).pack(anchor="w", padx=14, pady=(9, 0))
            ctk.CTkLabel(card, text=does, font=font(12), text_color=MUTED).pack(anchor="w", padx=14, pady=(0, 9))
        ctk.CTkLabel(s, text="Change the wake word and the Enter word in Settings.",
                     font=font(12), text_color=MUTED).pack(anchor="w", pady=10)

    # ---------- live updates (called on the UI thread) ----------
    def update_state(self, state: str, msg: str):
        text, color = STATUS.get(state, (state, "#9A9A9A"))
        text = text.format(wake=self.ctl.cfg.wake_word)
        self.status.configure(text=text)
        self.dot.configure(text_color=color)
        self.on_var.set(not self.ctl.engine.paused)
        if hasattr(self, "big"):
            self.big.configure(text=text)
            if msg:
                self.last.configure(text=msg)
            self.refresh_home()

    def refresh_home(self):
        if not hasattr(self, "words"):
            return
        n = self.ctl.cfg.words_typed
        self.words.configure(text=f"{n:,} words typed with Sayso so far" if n else "Nothing typed yet")
        for w in self.hist_box.winfo_children():
            w.destroy()
        hist = list(reversed(self.ctl.history[-20:]))
        if hist:
            self.hist_title.configure(text="Recent  -  click to copy")
            self.hist_clear.pack(side="right")
            for h in hist:
                row = ctk.CTkButton(self.hist_box, text=f"{h['t']}   {h['text'][:70].replace(chr(10), ' ')}",
                                    anchor="w", height=28, font=font(12), fg_color="transparent",
                                    text_color=("black", "white"), hover_color=CARD,
                                    command=lambda x=h["text"]: self._copy(x))
                row.pack(fill="x")
        else:
            self.hist_title.configure(text="Try saying")
            self.hist_clear.pack_forget()
            for said, does in COMMANDS[:4]:
                row = ctk.CTkFrame(self.hist_box, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=f"\u201c{said}\u201d", font=font(13)).pack(side="left")
                ctk.CTkLabel(row, text=does, font=font(12), text_color=MUTED).pack(side="right")

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        if hasattr(self, "last"):
            self.last.configure(text="Copied to clipboard")

    def apps_changed(self):
        if self.app_list:
            self.app_list.render()
        # wizard page 2 may be showing its own list
        for w in self.content.winfo_children():
            if isinstance(w, Wizard) and w.step == 1:
                w.show()
