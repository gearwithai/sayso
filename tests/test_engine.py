"""Runs the real engine loop with a fake speech model and fake audio - no mic or Windows needed."""
import threading
import time

import numpy as np

from sayso.config import Config
from sayso.engine import CHUNK, Engine

LOUD = (np.ones(CHUNK) * 3000).astype(np.int16)
QUIET = np.zeros(CHUNK, dtype=np.int16)
PAUSE = [QUIET] * 12   # ~1 s of silence ends a phrase (silence_secs=0.5 in tests)


class FakeSTT:
    """Returns scripted transcripts in order."""
    def __init__(self, texts):
        self.texts, self.calls = list(texts), []

    def transcribe(self, audio, **kw):
        self.calls.append((len(audio), kw.get("initial_prompt")))
        text = self.texts.pop(0) if self.texts else ""
        return [type("S", (), {"text": text})], None


def make_engine(texts, allowed=lambda a: None, **cfg):
    done = threading.Event()
    performed, states, typed = [], [], []

    def perform(a):
        performed.append(a)
        done.set()
        return "ok"

    e = Engine(Config(silence_secs=0.5, **cfg), perform, lambda s, m: states.append((s, m)),
               beep=lambda h: None, allowed=allowed, on_typed=lambda a: typed.append(len(a.text.split())))
    e._stt = FakeSTT(texts)
    e._load_models = lambda: None
    e._open_mic = lambda rescan=False: None
    return e, performed, states, typed, done


def feed(e, chunks, delay=0.0):
    for c in chunks:
        e.audio.put(c)
        if delay:
            time.sleep(delay)


def wait_idle(e, secs=3):
    end = time.time() + secs
    while time.time() < end and not e.audio.empty():
        time.sleep(0.05)
    time.sleep(0.3)


def test_one_breath_command():
    e, performed, _, typed, done = make_engine(["Sayso, run the tests. Send."])
    e.start()
    feed(e, [QUIET] * 3 + [LOUD] * 10 + PAUSE)
    assert done.wait(5)
    e.stop()
    assert performed[0].kind == "type_send" and performed[0].text == "run the tests"
    assert typed == [3]
    assert e._stt.calls[0][1] == "Sayso."  # wake word is used as a spelling hint


def test_wake_then_command():
    e, performed, states, _, done = make_engine(["Sayso.", "Open Chrome."])
    e.start()
    feed(e, [LOUD] * 6 + PAUSE)
    time.sleep(0.8)
    feed(e, [LOUD] * 8 + PAUSE)
    assert done.wait(5)
    e.stop()
    assert performed[0].kind == "switch" and performed[0].text == "chrome"
    assert ("listening", "") in states


def test_speech_without_wake_word_is_ignored():
    e, performed, _, _, done = make_engine(["So I was telling him about the game"])
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    assert not done.wait(1.5)
    e.stop()
    assert performed == [] and len(e._stt.calls) == 1


def test_while_testing_the_name_ignored_speech_is_reported():
    e, performed, _, _, done = make_engine(["Travis, hello"])
    missed = []
    e.on_ignored = missed.append
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    assert not done.wait(1.5)
    e.stop()
    assert performed == [] and missed == ["Travis, hello"]


def test_long_dictation_transcribes_full_audio():
    e, performed, _, _, done = make_engine(["Sayso, please note", "Sayso, please note the roof inspection is on Thursday"])
    e.start()
    feed(e, [LOUD] * 50 + PAUSE)  # 4 s of speech > 2.5 s gate
    assert done.wait(5)
    e.stop()
    assert performed[0] == type(performed[0])("type", "please note the roof inspection is on Thursday")
    gate_len, full_len = e._stt.calls[0][0], e._stt.calls[1][0]
    assert gate_len < full_len


def test_paused_ignores_everything_hands_free():
    e, performed, _, _, done = make_engine(["Sayso, hello"])
    e.paused = True
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    assert not done.wait(1)
    e.stop()
    assert e._stt.calls == []


def test_stop_listening_pauses():
    e, performed, states, _, _ = make_engine(["Sayso, stop listening."])
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    for _ in range(40):
        if e.paused:
            break
        time.sleep(0.1)
    e.stop()
    assert e.paused and performed == [] and states[-1][0] == "paused"


def test_blocked_app_stops_typing_but_not_switching():
    def allowed(a):
        return "Sayso is off in Notepad" if a.kind != "switch" else None
    e, performed, states, typed, done = make_engine(
        ["Sayso, hello world", "Sayso, open Chrome"], allowed=allowed)
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    wait_idle(e)
    feed(e, [LOUD] * 10 + PAUSE)
    assert done.wait(5)
    e.stop()
    assert [a.kind for a in performed] == ["switch"]
    assert any(m == "Sayso is off in Notepad" for _, m in states)
    assert typed == []


def test_push_to_talk_types_without_commands():
    e, performed, _, _, done = make_engine(["open Chrome"])
    e.start()
    time.sleep(0.2)
    e.ptt_press()
    feed(e, [LOUD] * 8)
    time.sleep(0.6)
    e.ptt_release()
    assert done.wait(5)
    e.stop()
    assert performed[0].kind == "type" and performed[0].text == "open Chrome"


def test_ptt_works_while_paused():
    e, performed, _, _, done = make_engine(["note to self"])
    e.paused = True
    e.start()
    e.ptt_press()
    feed(e, [LOUD] * 8)
    time.sleep(0.6)
    e.ptt_release()
    assert done.wait(5)
    e.stop()


def test_shortcut_while_holding_key_does_not_dictate():
    e, performed, _, _, done = make_engine(["oops"])
    e.start()
    e.ptt_press()
    e.ptt_cancel()  # e.g. Ctrl+C
    time.sleep(0.6)
    e.ptt_release()
    assert not done.wait(1)
    e.stop()


def test_dictation_mode_types_everything_until_stopped():
    e, performed, states, _, _ = make_engine(
        ["Sayso, start dictation.", "The roof is done.", "Open Chrome", "Stop dictation."])
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    wait_idle(e)
    assert e.dictating and states[-1][0] == "dictating"
    feed(e, [LOUD] * 10 + PAUSE)
    wait_idle(e)
    feed(e, [LOUD] * 10 + PAUSE)
    wait_idle(e)
    feed(e, [LOUD] * 10 + PAUSE)
    wait_idle(e)
    e.stop()
    assert [(a.kind, a.text) for a in performed] == [("type", "The roof is done."), ("type", "Open Chrome")]
    assert not e.dictating


def test_dictation_mode_still_takes_wake_word_commands():
    e, performed, _, _, _ = make_engine(["Sayso, start dictation.", "Sayso, open Chrome."])
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    wait_idle(e)
    feed(e, [LOUD] * 10 + PAUSE)
    wait_idle(e)
    e.stop()
    assert performed[0].kind == "switch"


def test_dictation_turns_itself_off_when_quiet(monkeypatch):
    import sayso.engine as eng
    monkeypatch.setattr(eng, "DICTATION_IDLE_SECS", 0.3)
    e, _, states, _, _ = make_engine(["Sayso, start dictation."])
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    time.sleep(1.5)
    e.stop()
    assert not e.dictating and "quiet" in states[-1][1]


def test_ai_actions_show_asking_ai():
    e, performed, states, _, done = make_engine(["Sayso, make this shorter."])
    e.start()
    feed(e, [LOUD] * 10 + PAUSE)
    assert done.wait(5)
    e.stop()
    assert performed[0].kind == "ai_edit" and ("thinking", "Asking AI...") in states


def test_startup_keeps_retrying_until_the_model_loads():
    e, performed, states, _, done = make_engine(["Sayso, hello."])
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("no internet")
    e._load_models = flaky
    e.retry_secs = 0.1
    e.start()
    end = time.time() + 5
    while time.time() < end and not any(s == "ready" for s, _ in states):
        time.sleep(0.05)
    feed(e, [LOUD] * 8 + PAUSE)
    assert done.wait(5)
    e.stop()
    assert len(attempts) == 3
    assert any(s == "error" and "internet" in m for s, m in states)
    assert performed[0].text == "hello."


def test_dictation_keeps_speech_said_while_typing():
    """Talking straight on in dictation mode must not lose the next phrase."""
    e, performed, _, _, _ = make_engine(["first part", "second part"])
    slow = e.perform

    def slow_perform(a):
        time.sleep(0.6)   # pasting takes a moment...
        return slow(a)
    e.perform = slow_perform
    e.dictating = True
    e.start()
    feed(e, [LOUD] * 6 + PAUSE)
    time.sleep(0.2)
    feed(e, [LOUD] * 6 + PAUSE)    # ...and the user keeps talking meanwhile
    end = time.time() + 6
    while time.time() < end and len(performed) < 2:
        time.sleep(0.05)
    e.stop()
    assert [a.text for a in performed] == ["first part", "second part"]
