"""The listening loop. Runs on its own thread.

Hands-free:  speech detected -> transcribe the first ~2.5 s -> starts with "Sayso"? -> act on the rest
             (or, if only "Sayso" was said, beep and listen for the command).
Hold-to-talk: record while the key is held -> type the text (no commands).
"""
import logging
import queue
import threading
import time
from typing import Callable

import numpy as np

from sayso import wake
from sayso.commands import Action, parse
from sayso.config import Config, models_dir

log = logging.getLogger("sayso.engine")

RATE = 16000
CHUNK = 1280                 # 80 ms
PTT_MIN_SECS = 0.35          # shorter key taps are ignored
GATE_SECS = 2.5              # how much of an utterance we transcribe to look for the wake word
PREROLL_CHUNKS = 3           # keep 240 ms before speech starts so the first sound isn't clipped
MIN_UTTERANCE_SECS = 0.3

LOADING, READY, LISTENING, THINKING, PAUSED, ERROR = (
    "loading", "ready", "listening", "thinking", "paused", "error")


def rms(chunk: np.ndarray) -> float:
    x = chunk.astype(np.float32) / 32768
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def count_words(action: Action) -> int:
    return len(action.text.split()) if action.kind in ("type", "type_send") else 0


class Engine(threading.Thread):
    def __init__(self, cfg: Config, perform: Callable[[Action], str],
                 on_state: Callable[[str, str], None], beep: Callable[[bool], None],
                 allowed: Callable[[], str | None] = lambda: None,
                 on_typed: Callable[[int], None] = lambda n: None):
        super().__init__(daemon=True, name="sayso-engine")
        self.cfg = cfg
        self.perform = perform
        self.on_state = on_state
        self.beep = beep
        self.allowed = allowed          # returns a reason string when typing is blocked (e.g. trial used up)
        self.on_typed = on_typed        # word counter for usage
        self.audio: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=600)
        self.level = 0.0
        self.state = LOADING
        self.paused = False
        self._stop = threading.Event()
        self._reload = threading.Event()
        self._ptt_down_at: float | None = None
        self._ptt_cancelled = False
        self._stream = None
        self._stt = None
        self._loaded_model = None
        self._preroll: list[np.ndarray] = []
        self._ptt_prefix: list[np.ndarray] = []

    # ---------- public, thread-safe ----------
    def set_paused(self, paused: bool):
        self.paused = paused
        self._set_state(PAUSED if paused else READY)

    def apply_config(self, cfg: Config):
        self.cfg = cfg
        self._reload.set()

    def stop(self):
        self._stop.set()

    def ptt_press(self):
        if self._ptt_down_at is None:
            self._ptt_down_at = time.time()
            self._ptt_cancelled = False

    def ptt_release(self):
        self._ptt_down_at = None

    def ptt_cancel(self):
        if self._ptt_down_at is not None:
            self._ptt_cancelled = True

    # ---------- setup ----------
    def _set_state(self, state: str, msg: str = ""):
        self.state = state
        try:
            self.on_state(state, msg)
        except Exception:
            log.exception("state callback failed")

    def _idle_state(self):
        return PAUSED if self.paused else READY

    def _on_audio(self, indata, frames, t, status):
        chunk = indata[:, 0].copy()
        self.level = rms(chunk)
        try:
            self.audio.put_nowait(chunk)
        except queue.Full:
            try:
                self.audio.get_nowait()
                self.audio.put_nowait(chunk)
            except queue.Empty:
                pass

    def _open_mic(self):
        import sounddevice as sd
        if self._stream:
            self._stream.close()
        self._stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK,
                                      device=self.cfg.mic_device, callback=self._on_audio)
        self._stream.start()

    def _load_models(self):
        if self._loaded_model == self.cfg.stt_model:
            return
        self._set_state(LOADING, "Downloading speech model (first run only)...")
        from faster_whisper import WhisperModel
        self._stt = WhisperModel(self.cfg.stt_model, device="cpu", compute_type="int8",
                                 download_root=str(models_dir() / "whisper"))
        self._loaded_model = self.cfg.stt_model

    # ---------- audio helpers ----------
    def _next(self, timeout=0.1):
        try:
            return self.audio.get(timeout=timeout)
        except queue.Empty:
            return None

    def _drain(self):
        while True:
            try:
                self.audio.get_nowait()
            except queue.Empty:
                return

    def _loud(self, chunk) -> bool:
        return rms(chunk) >= self.cfg.silence_level

    def _collect_utterance(self, first: list[np.ndarray], wait_for_speech: float = 0.0):
        """Reads chunks until a pause of silence_secs. `first` = chunks already captured.
        If wait_for_speech > 0, gives up (returns None) when nobody starts talking in time."""
        cfg = self.cfg
        frames = list(first)
        heard = any(self._loud(c) for c in frames)
        silent, start = 0.0, time.time()
        while time.time() - start < cfg.max_secs and not self._stop.is_set():
            chunk = self._next(0.5)
            if chunk is None:
                continue
            frames.append(chunk)
            if self._loud(chunk):
                heard, silent = True, 0.0
            else:
                silent += CHUNK / RATE
            if heard and silent >= cfg.silence_secs:
                break
            if not heard and wait_for_speech and time.time() - start > wait_for_speech:
                return None
            if self._ptt_down_at is not None:  # hold-to-talk interrupts: hand the audio over
                self._ptt_prefix = frames[-4:]
                return None
        return np.concatenate(frames) if frames else None

    def _record_while_held(self):
        frames, start = self._ptt_prefix, time.time()
        self._ptt_prefix = []
        while self._ptt_down_at is not None and not self._stop.is_set():
            chunk = self._next(0.2)
            if chunk is not None:
                frames.append(chunk)
            if time.time() - start > self.cfg.max_secs:
                break
        for _ in range(2):  # the last ~160 ms, so the final word isn't clipped
            chunk = self._next(0.1)
            if chunk is not None:
                frames.append(chunk)
        return np.concatenate(frames) if frames else None

    def _transcribe(self, audio_i16: np.ndarray, prompt: str | None = None) -> str:
        audio = audio_i16.astype(np.float32) / 32768
        segments, _ = self._stt.transcribe(audio, language="en", vad_filter=True, beam_size=1,
                                           initial_prompt=prompt, condition_on_previous_text=False)
        return " ".join(s.text for s in segments).strip()

    # ---------- acting ----------
    def _act(self, text: str, allow_commands: bool):
        action = parse(text, self.cfg.send_word, allow_commands=allow_commands)
        log.info("heard %r -> %s", text, action)
        if action.kind == "stop":
            self.set_paused(True)
            return
        if action.kind == "nothing":
            self._set_state(self._idle_state(), "Didn't catch that")
            return
        words = count_words(action)
        if words:
            blocked = self.allowed()
            if blocked:
                self._set_state(self._idle_state(), blocked)
                return
        msg = self.perform(action)
        if words:
            self.on_typed(words)
        self._set_state(self._idle_state(), msg)

    def _hands_free(self, first_chunk):
        """Called when speech starts. Decides whether it was meant for us."""
        cfg = self.cfg
        utt = self._collect_utterance(self._preroll + [first_chunk])
        self._preroll = []
        if utt is None or len(utt) < MIN_UTTERANCE_SECS * RATE:
            return
        prompt = f"{cfg.wake_word}."
        gate_len = int(GATE_SECS * RATE)
        gate_text = self._transcribe(utt[:gate_len], prompt)
        woke, rest = wake.match(gate_text, cfg.wake_word)
        if not woke:
            log.debug("ignored: %r", gate_text)
            return

        if not rest and len(utt) <= gate_len:
            # Just "Sayso" - beep and wait for the command.
            self._set_state(LISTENING)
            if cfg.beeps:
                self.beep(True)
            self._drain()
            cmd = self._collect_utterance([], wait_for_speech=4.0)
            if cmd is None:
                self._set_state(self._idle_state(), "Didn't hear anything")
                return
            self._set_state(THINKING)
            self._act(self._transcribe(cmd), allow_commands=True)
            return

        # "Sayso, <command>" in one go
        self._set_state(THINKING)
        full = gate_text if len(utt) <= gate_len else self._transcribe(utt, prompt)
        woke, rest = wake.match(full, cfg.wake_word)
        self._act(rest if woke else full, allow_commands=True)

    def _push_to_talk(self):
        self._set_state(LISTENING)
        if self.cfg.beeps:
            self.beep(True)
        audio = self._record_while_held()
        if self._ptt_cancelled or audio is None:
            self._set_state(self._idle_state())
            return
        self._set_state(THINKING)
        self._act(self._transcribe(audio), allow_commands=False)

    # ---------- main loop ----------
    def run(self):
        try:
            self._load_models()
            self._open_mic()
        except Exception as e:
            log.exception("startup failed")
            self._set_state(ERROR, f"Couldn't start: {e}")
            return
        self._set_state(self._idle_state(), "Ready")

        while not self._stop.is_set():
            if self._reload.is_set():
                self._reload.clear()
                try:
                    self._load_models()
                    self._open_mic()
                    self._set_state(self._idle_state(), "Settings applied")
                except Exception as e:
                    log.exception("reload failed")
                    self._set_state(ERROR, f"Settings problem: {e}")
                    time.sleep(1)
                continue

            try:
                if self._ptt_down_at is not None:
                    if self._ptt_cancelled:
                        self._drain()
                        self._ptt_prefix = []
                    elif time.time() - self._ptt_down_at >= PTT_MIN_SECS:
                        self._push_to_talk()
                        self._drain()
                        continue
                    time.sleep(0.02)  # leave audio queued so the first words aren't lost
                    continue

                chunk = self._next(0.1)
                if chunk is None:
                    continue
                if self.paused or not self.cfg.hands_free:
                    continue
                if not self._loud(chunk):
                    self._preroll = (self._preroll + [chunk])[-PREROLL_CHUNKS:]
                    continue
                if self._ptt_down_at is not None:
                    self._ptt_prefix = [chunk]
                    continue
                self._hands_free(chunk)
                if self._ptt_down_at is None:
                    self._drain()
            except Exception:
                log.exception("loop error")
                self._set_state(self._idle_state(), "Something went wrong - see log")
                self._drain()

        if self._stream:
            self._stream.close()
