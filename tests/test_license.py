import pytest

from sayso import license as lic_mod
from sayso.license import ApiError, License


class FakeServer:
    """In-memory copy of the sayso-api edge function's behaviour."""
    def __init__(self):
        self.devices, self.calls, self.offline = {}, [], False

    def __call__(self, body, token=None):
        self.calls.append((body["action"], token))
        if self.offline:
            raise ConnectionError("no internet")
        a = body["action"]
        if a == "register":
            tok = f"tok{len(self.devices)}" + "x" * 40
            self.devices[tok] = {"plan": "trial", "allowed": True, "words_used": 0, "word_limit": 2000}
            return {"token": tok, **self.devices[tok]}
        if token not in self.devices:
            raise ApiError("reregister")
        d = self.devices[token]
        if a == "usage":
            d["words_used"] += body["words"]
            d["allowed"] = d["words_used"] < d["word_limit"]
        if a == "activate":
            if body["key"] != "GOOD-KEY":
                raise ApiError("That license key isn't valid or has expired.")
            d.update(plan="pro", allowed=True, word_limit=None, email="a@b.com")
        return dict(d)


@pytest.fixture(autouse=True)
def tmp_account(tmp_path, monkeypatch):
    monkeypatch.setattr(lic_mod, "ACCOUNT_PATH", tmp_path / "account.json")
    monkeypatch.setattr(lic_mod, "machine_id", lambda: "m1")


def test_trial_counts_down_and_blocks():
    srv = FakeServer()
    lic = License(post=srv)
    assert lic.blocked_reason() is None
    lic.add_words(1990)
    lic.sync()
    assert lic.words_left() == 10 and lic.unsynced == 0
    lic.add_words(10)
    assert lic.words_left() == 0
    assert "used up" in lic.blocked_reason()   # blocks even before syncing


def test_works_offline_and_syncs_later():
    srv = FakeServer()
    lic = License(post=srv)
    lic.sync()
    srv.offline = True
    lic.add_words(100)
    with pytest.raises(ConnectionError):
        lic.sync()
    assert lic.unsynced == 100 and lic.blocked_reason() is None
    srv.offline = False
    lic.sync()
    assert lic.unsynced == 0 and lic.status["words_used"] == 100


def test_state_survives_restart():
    srv = FakeServer()
    a = License(post=srv)
    a.add_words(42)
    b = License(post=srv)
    assert b.unsynced == 42


def test_activate_good_and_bad_key():
    srv = FakeServer()
    lic = License(post=srv)
    with pytest.raises(ApiError, match="isn't valid"):
        lic.activate("NOPE")
    lic.add_words(5000)
    assert lic.blocked_reason()
    lic.activate("GOOD-KEY")
    assert lic.is_pro and lic.blocked_reason() is None and "Pro" in lic.summary()


def test_reregisters_when_token_is_lost_on_server():
    srv = FakeServer()
    lic = License(post=srv)
    lic.sync()
    srv.devices.clear()
    lic.sync()
    assert [c[0] for c in srv.calls].count("register") == 2
