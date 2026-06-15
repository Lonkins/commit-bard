"""Phase 2 CLI surface: --mode/--dual, install/uninstall, and --hook routing."""

import subprocess

import pytest

from commit_bard import cli, git_io, mock_corpus, styles


def test_dual_flag_yields_subject_then_verse(clean_env, capsys):
    rc = cli.main(["--sample", "--style", "haiku", "--dual"])
    out = capsys.readouterr().out
    assert rc == 0
    assert ":" in out.splitlines()[0]  # conventional subject first


def test_mode_verse_yields_just_verse(clean_env, capsys):
    rc = cli.main(["--sample", "--style", "haiku", "--mode", "verse"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out in mock_corpus.CORPUS["haiku"]  # bare verse, no subject line


def test_mode_plain_is_single_line(clean_env, capsys):
    rc = cli.main(["--sample", "--mode", "plain"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert "\n" not in out and ":" in out


def test_invalid_mode_rejected_by_argparse(clean_env):
    with pytest.raises(SystemExit):
        cli.main(["--sample", "--mode", "bogus"])


def test_invalid_config_mode_returns_usage_error(clean_env, capsys):
    clean_env.setenv("COMMIT_BARD_MODE", "bogus")
    rc = cli.main(["--sample", "--style", "haiku"])
    assert rc == 2
    assert "Unknown mode" in capsys.readouterr().err


def test_install_and_uninstall_hook_commands(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["install-hook"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Installed" in out
    assert (tmp_path / ".git" / "hooks" / "prepare-commit-msg").exists()

    rc2 = cli.main(["uninstall-hook"])
    assert rc2 == 0
    assert not (tmp_path / ".git" / "hooks" / "prepare-commit-msg").exists()


def test_install_hook_outside_repo_returns_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # not a git repo
    rc = cli.main(["install-hook"])
    assert rc == 1
    assert "Error" in capsys.readouterr().err


def test_cli_flags_beat_env_and_config(clean_env, capsys):
    # Closes the precedence loop: --style/--mode flags win over env vars.
    clean_env.setenv("COMMIT_BARD_STYLE", "epic")
    clean_env.setenv("COMMIT_BARD_MODE", "plain")
    rc = cli.main(["--sample", "--style", "noir", "--mode", "verse"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out in mock_corpus.CORPUS["noir"]  # flag style+mode won over env


def test_hook_flag_routes_and_always_returns_zero(clean_env, tmp_path, monkeypatch):
    monkeypatch.setattr(git_io, "staged_diff", lambda: styles.SAMPLE_DIFF)
    msg = tmp_path / "MSG"
    msg.write_text("# template comment\n")
    rc = cli.main(["--hook", str(msg)])
    assert rc == 0
    assert msg.read_text().strip()
