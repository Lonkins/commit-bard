"""The headline: --sample / --list-styles work with zero setup."""

from commit_bard import cli, compose, git_io, provider


def test_sample_haiku_prints_verse(clean_env, capsys):
    rc = cli.main(["--sample", "--style", "haiku"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip(), "expected a verse on stdout"
    assert "mock mode" in captured.err, "expected the mock notice on stderr"


def test_list_styles_lists_builtins(capsys):
    rc = cli.main(["--list-styles"])
    captured = capsys.readouterr()
    assert rc == 0
    for name in ("haiku", "shanty", "limerick", "epic", "pirate", "noir"):
        assert name in captured.out


def test_unknown_style_returns_usage_error(clean_env, capsys):
    rc = cli.main(["--sample", "--style", "does-not-exist"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Unknown style" in captured.err


def test_sample_palette_prints_multiple(clean_env, capsys):
    rc = cli.main(["--sample", "3"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.count("──") >= 3, "expected three style headers"
    # The mock notice must stay on stderr even in palette mode.
    assert "mock mode" in captured.err
    assert "mock mode" not in captured.out


def test_random_style_still_succeeds(clean_env, capsys):
    rc = cli.main(["--sample", "--random-style"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip()


def test_stdout_is_pipe_clean(clean_env, capsys):
    # The mock notice must go to stderr, never stdout (so piping stays clean).
    cli.main(["--sample", "--style", "noir"])
    captured = capsys.readouterr()
    assert "mock mode" not in captured.out


def test_sample_zero_prints_single_verse(clean_env, capsys):
    # --sample 0 is a degenerate count; it falls through to a single verse.
    rc = cli.main(["--sample", "0", "--style", "haiku"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip()


# --- git-backed (non-sample) paths, with git stubbed out ------------------


def test_not_in_repo_returns_runtime_error(clean_env, capsys, monkeypatch):
    monkeypatch.setattr(git_io, "in_git_repo", lambda: False)
    rc = cli.main(["--style", "haiku"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Not inside a git repository" in captured.err
    assert captured.out == ""


def test_no_staged_changes_returns_runtime_error(clean_env, capsys, monkeypatch):
    monkeypatch.setattr(git_io, "in_git_repo", lambda: True)
    monkeypatch.setattr(git_io, "staged_diff", lambda: "")
    rc = cli.main(["--style", "haiku"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "No staged changes" in captured.err
    assert captured.out == ""


def test_real_staged_diff_happy_path(clean_env, capsys, monkeypatch):
    monkeypatch.setattr(git_io, "in_git_repo", lambda: True)
    monkeypatch.setattr(git_io, "staged_diff", lambda: "diff --git a b\n+x")
    rc = cli.main(["--style", "haiku"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip()


# --- provider failure path -------------------------------------------------


def test_provider_error_returns_runtime_error(clean_env, capsys, monkeypatch):
    def boom(*args, **kwargs):
        raise provider.ProviderError("boom")

    monkeypatch.setattr(compose, "compose", boom)
    rc = cli.main(["--sample", "--style", "haiku"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Provider error" in captured.err
    assert captured.out == ""


def test_palette_provider_error_returns_runtime_error(clean_env, capsys, monkeypatch):
    def boom(*args, **kwargs):
        raise provider.ProviderError("boom")

    monkeypatch.setattr(compose, "compose", boom)
    rc = cli.main(["--sample", "2"])
    assert rc == 1
