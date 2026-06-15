"""Repo 'wrapped': poem extraction, scoring, rendering, and the CLI command."""

import subprocess

from commit_bard import cli, compose, git_io, history, wrapped


def _commit(hash="abc123def0", subject="feat: x", body="", date="2026-06-15T10:00:00+00:00", author="Lonkins"):
    return git_io.Commit(hash=hash, date=date, author=author, subject=subject, body=body)


# --- extraction & scoring --------------------------------------------------


def test_extract_verse_from_dual_body():
    body = "some context line\n\n  line one\n  line two\n"
    assert wrapped._extract_verse(body) == "line one\nline two"


def test_extract_verse_none_when_no_indented_block():
    assert wrapped._extract_verse("a normal body\nwith no indent") is None


def test_extract_verse_ignores_bullet_continuations():
    body = (
        "- a bullet with a long line that\n  wraps with indentation\n"
        "- another bullet\n\n"
        "  real verse line one\n  real verse line two"
    )
    assert wrapped._extract_verse(body) == "real verse line one\nreal verse line two"


def test_extract_verse_none_for_bullet_only_body():
    assert wrapped._extract_verse("- one\n  cont\n- two\n  cont two") is None


def test_extract_verse_takes_last_block():
    body = "  early block\n\nplain text\n\n  the real verse\n  second line"
    assert wrapped._extract_verse(body) == "the real verse\nsecond line"


def test_extract_verse_keeps_internal_blank_lines():
    body = "  one\n  two\n\n  three\n  four"
    assert wrapped._extract_verse(body) == "one\ntwo\n\nthree\nfour"


def test_extract_verse_skips_leading_blank_runs():
    body = "prose line\n\n\n  real one\n  real two"
    assert wrapped._extract_verse(body) == "real one\nreal two"


def test_multi_stanza_verse_round_trips_through_wrapped():
    # The HIGH bug: dual mode separates stanzas with blank lines; wrapped must
    # read them all back, not just the last stanza.
    verse = "Stanza one line a\nStanza one line b\n\nStanza two line a\nStanza two line b"
    body = compose._assemble_dual("feat: x", verse).split("\n\n", 1)[1]
    assert wrapped._extract_verse(body) == verse


def test_score_empty_verse_is_zero():
    assert wrapped._score("") == 0.0
    assert wrapped._score("   ") == 0.0


def test_score_deterministic_and_rewards_richness():
    verse = "line one\nline two\nline three"
    assert wrapped._score(verse) == wrapped._score(verse)
    assert wrapped._score(verse) > wrapped._score("x")


def test_collect_filters_non_poems_and_sorts_best_first():
    rich = _commit(hash="aaa", subject="feat: rich", body="  alpha beta gamma\n  delta epsilon zeta\n  eta theta iota")
    thin = _commit(hash="bbb", subject="fix: thin", body="  wip")
    plain = _commit(hash="ccc", subject="chore: plain", body="no verse here at all")
    poems = wrapped.collect([thin, plain, rich])
    assert [p.short_hash for p in poems] == ["aaa", "bbb"]  # plain dropped, rich first
    assert poems[0].score >= poems[1].score


# --- rendering -------------------------------------------------------------


def test_render_markdown_contains_subject_verse_and_hash():
    md = wrapped.render_markdown(wrapped.collect([_commit(hash="aaa1234567", subject="feat: rich", body="  alpha\n  beta")]))
    assert "feat: rich" in md
    assert "> alpha" in md
    assert "aaa123456" in md  # 9-char short hash


def test_render_markdown_empty_state():
    assert "No commit poems" in wrapped.render_markdown([])


def test_render_html_escapes_and_fully_renders():
    out = wrapped.render_html(wrapped.collect([_commit(subject="feat: <x>", body="  a & b\n  c")]))
    assert "<!doctype html>" in out
    assert "&lt;x&gt;" in out  # subject escaped
    assert "a &amp; b" in out  # verse escaped
    assert "__BODY__" not in out and "__COUNT__" not in out  # template rendered


def test_render_html_empty_state():
    out = wrapped.render_html([])
    assert "No commit poems" in out
    assert "__COUNT__" not in out


def test_render_html_escapes_author():
    out = wrapped.render_html(wrapped.collect([_commit(author="<script>evil</script>", body="  v1\n  v2")]))
    assert "<script>evil" not in out
    assert "&lt;script&gt;evil" in out


def test_render_markdown_escapes_html_in_commit_content():
    out = wrapped.render_markdown(wrapped.collect([_commit(subject="feat: <img src=x>", body="  a <b> c")]))
    assert "<img src=x>" not in out
    assert "&lt;img" in out


def test_wrapped_end_to_end_both_formats(monkeypatch):
    commits = [_commit(hash="h1", subject="feat: a", body="  verse alpha\n  verse beta")]
    monkeypatch.setattr(git_io, "git_log", lambda *a, **k: commits)
    assert "feat: a" in wrapped.wrapped(top=5, fmt="md")
    assert "<article" in wrapped.wrapped(top=5, fmt="html")


def test_wrapped_top_truncates(monkeypatch):
    commits = [
        _commit(hash=f"h{i}", subject=f"feat: {i}", body=f"  verse {i} alpha\n  verse {i} beta")
        for i in range(5)
    ]
    monkeypatch.setattr(git_io, "git_log", lambda *a, **k: commits)
    assert wrapped.wrapped(top=2, fmt="md").count("## ") == 2


def test_wrapped_top_zero_is_empty(monkeypatch):
    monkeypatch.setattr(git_io, "git_log", lambda *a, **k: [_commit(body="  v1\n  v2")])
    assert "No commit poems" in wrapped.wrapped(top=0, fmt="md")


def test_wrapped_prefers_history_when_present(monkeypatch):
    entries = [
        {
            "subject": "feat: hist",
            "verse": "history verse a\nhistory verse b",
            "ts": "2026-06-15T00:00:00+00:00",
            "author": "Lonkins",
            "commit": None,
        }
    ]
    monkeypatch.setattr(history, "load", lambda: entries)

    def no_git_log(*args, **kwargs):
        raise AssertionError("git_log must not be called when history is present")

    monkeypatch.setattr(git_io, "git_log", no_git_log)
    out = wrapped.wrapped(fmt="md")
    assert "feat: hist" in out and "history verse a" in out


def test_wrapped_since_forces_git_log_over_history(monkeypatch):
    monkeypatch.setattr(history, "load", lambda: [{"subject": "x", "verse": "y"}])
    monkeypatch.setattr(
        git_io, "git_log", lambda *a, **k: [_commit(subject="feat: fromlog", body="  log verse")]
    )
    out = wrapped.wrapped(rev_range="v1..HEAD", fmt="md")
    assert "feat: fromlog" in out  # --since bypasses the flat history log


# --- git_io.git_log --------------------------------------------------------


def test_git_log_parses_records(monkeypatch):
    rec = "h1\x1f2026-06-15T10:00:00+00:00\x1fLonkins\x1ffeat: a\x1f  verse line\x1e\n"
    cp = subprocess.CompletedProcess(["log"], 0, stdout=rec, stderr="")
    monkeypatch.setattr(git_io, "_run_git", lambda *a, **k: cp)
    commits = git_io.git_log()
    assert len(commits) == 1
    assert commits[0].hash == "h1"
    assert commits[0].subject == "feat: a"
    assert commits[0].body == "  verse line"  # indentation preserved


def test_git_log_empty_on_git_failure(monkeypatch):
    cp = subprocess.CompletedProcess(["log"], 128, stdout="", stderr="fatal")
    monkeypatch.setattr(git_io, "_run_git", lambda *a, **k: cp)
    assert git_io.git_log() == []


def test_git_log_parses_multiple_and_skips_malformed(monkeypatch):
    good1 = "h1\x1fD1\x1fA1\x1fs1\x1f  v1\n  v2\x1e\n"
    malformed = "only-one-field\x1e\n"
    good2 = "h2\x1fD2\x1fA2\x1fs2\x1f  w1\x1e\n"
    cp = subprocess.CompletedProcess(["log"], 0, stdout=good1 + malformed + good2, stderr="")
    monkeypatch.setattr(git_io, "_run_git", lambda *a, **k: cp)
    commits = git_io.git_log()
    assert [c.hash for c in commits] == ["h1", "h2"]  # malformed record skipped
    assert commits[0].body == "  v1\n  v2"  # multiline body preserved


def test_git_log_keeps_separator_char_in_body(monkeypatch):
    # A stray field-separator inside the body must not truncate it (maxsplit=4).
    body_with_sep = "  line one\x1fstill body"
    rec = f"h1\x1fD\x1fA\x1fsubj\x1f{body_with_sep}\x1e\n"
    cp = subprocess.CompletedProcess(["log"], 0, stdout=rec, stderr="")
    monkeypatch.setattr(git_io, "_run_git", lambda *a, **k: cp)
    assert git_io.git_log()[0].body == body_with_sep


# --- CLI -------------------------------------------------------------------


def test_cli_wrapped_renders(clean_env, monkeypatch, capsys):
    commits = [_commit(hash="h1", subject="feat: a", body="  verse alpha\n  verse beta")]
    monkeypatch.setattr(git_io, "in_git_repo", lambda: True)
    monkeypatch.setattr(git_io, "git_log", lambda *a, **k: commits)
    rc = cli.main(["wrapped", "--format", "md"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "feat: a" in captured.out


def test_cli_wrapped_outside_repo_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(git_io, "in_git_repo", lambda: False)
    rc = cli.main(["wrapped"])
    assert rc == 1
    assert "Not inside a git repository" in capsys.readouterr().err


def test_cli_wrapped_empty_history_exits_zero(clean_env, monkeypatch, capsys):
    monkeypatch.setattr(git_io, "in_git_repo", lambda: True)
    monkeypatch.setattr(git_io, "git_log", lambda *a, **k: [])
    rc = cli.main(["wrapped"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "No commit poems" in captured.out


def test_cli_wrapped_since_translates_to_rev_range(clean_env, monkeypatch):
    captured = {}

    def fake_log(rev_range=None, **kwargs):
        captured["rev"] = rev_range
        return []

    monkeypatch.setattr(git_io, "in_git_repo", lambda: True)
    monkeypatch.setattr(git_io, "git_log", fake_log)
    cli.main(["wrapped", "--since", "v1.0"])
    assert captured["rev"] == "v1.0..HEAD"
