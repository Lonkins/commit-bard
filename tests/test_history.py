"""Optional local poem history (JSONL)."""

import pathlib

from commit_bard import history


def test_record_noop_when_disabled(monkeypatch, tmp_path):
    path = tmp_path / "history.jsonl"
    monkeypatch.setattr(history, "_history_path", lambda: path)
    history.record({"verse": "v"}, enabled=False)
    assert not path.exists()


def test_record_appends_jsonl_with_timestamp(monkeypatch, tmp_path):
    path = tmp_path / "history.jsonl"
    monkeypatch.setattr(history, "_history_path", lambda: path)
    history.record({"subject": "feat: x", "verse": "a\nb"}, enabled=True)
    history.record({"subject": "fix: y", "verse": "c"}, enabled=True)
    entries = history.load()
    assert [e["subject"] for e in entries] == ["feat: x", "fix: y"]
    assert entries[0]["verse"] == "a\nb"
    assert "ts" in entries[0]  # stamped


def test_load_empty_when_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "_history_path", lambda: tmp_path / "nope.jsonl")
    assert history.load() == []


def test_load_skips_malformed_lines(monkeypatch, tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text('{"verse": "ok"}\nnot json\n\n{"verse": "two"}\n')
    monkeypatch.setattr(history, "_history_path", lambda: path)
    assert [e["verse"] for e in history.load()] == ["ok", "two"]


def test_record_never_raises_when_no_path(monkeypatch):
    # _history_path returns None when not in a repo -> record is a silent no-op.
    monkeypatch.setattr(history, "_history_path", lambda: None)
    history.record({"verse": "v"}, enabled=True)  # must not raise
    assert history.load() == []


def test_record_swallows_write_errors(monkeypatch, tmp_path):
    # The load-bearing never-block invariant: a write failure must not raise.
    path = tmp_path / "sub" / "history.jsonl"
    monkeypatch.setattr(history, "_history_path", lambda: path)

    def boom(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pathlib.Path, "mkdir", boom)
    history.record({"verse": "v"}, enabled=True)  # swallowed, no exception
    assert not path.exists()
