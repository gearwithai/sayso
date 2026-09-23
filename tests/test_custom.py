import json

import pytest

from sayso import custom
from sayso.custom import EXAMPLE, load_from, parse_keys


@pytest.mark.parametrize("spec,expected", [
    ("ctrl+t", (["ctrl"], "t")),
    ("Ctrl + Shift + T", (["ctrl", "shift"], "t")),
    ("win+d", (["win"], "d")),
    ("f5", ([], "f5")),
    ("alt+tab", (["alt"], "tab")),
    ("control+enter", (["ctrl"], "enter")),
    ("nexttrack", ([], "nexttrack")),
])
def test_parse_keys(spec, expected):
    assert parse_keys(spec) == expected


@pytest.mark.parametrize("bad", ["", "ctrl+banana", "t+ctrl", "hyper+x"])
def test_parse_keys_rejects(bad):
    with pytest.raises(ValueError):
        parse_keys(bad)


def test_example_file_is_valid():
    good, problems = load_from(EXAMPLE)
    assert problems == [] and "new tab" in good


def test_problems_are_reported_not_fatal():
    good, problems = load_from({"commands": [
        {"say": "ok", "keys": "ctrl+s"},
        {"say": "", "keys": "ctrl+s"},
        {"say": "two things", "keys": "ctrl+s", "url": "https://x"},
        {"say": "bad key", "keys": "ctrl+nope"},
        {"say": "multi", "keys": ["ctrl+a", "delete"]},
    ]})
    assert set(good) == {"ok", "multi"}
    assert len(problems) == 3


def test_reloads_when_file_changes(tmp_path, monkeypatch):
    path = tmp_path / "commands.json"
    monkeypatch.setattr(custom, "PATH", path)
    c = custom.CustomCommands()
    assert "new tab" in c.get()                     # example written on first run
    path.write_text(json.dumps({"commands": [{"say": "hello", "type": "hi"}]}))
    import os
    os.utime(path, (1, 1))                          # force a different mtime
    assert list(c.get()) == ["hello"]
    path.write_text("{not json")
    os.utime(path, (2, 2))
    assert c.get() == {} and "valid JSON" in c.problems[0]
