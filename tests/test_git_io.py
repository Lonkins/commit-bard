"""git_io: repo detection and staged-diff reading, without a real repo."""

import pytest

from commit_bard import git_io


class _CP:
    """A stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_in_git_repo_true(monkeypatch):
    monkeypatch.setattr(git_io, "_run_git", lambda args: _CP(0, "true\n"))
    assert git_io.in_git_repo() is True


def test_in_git_repo_false_on_nonzero(monkeypatch):
    monkeypatch.setattr(git_io, "_run_git", lambda args: _CP(128, "", "fatal"))
    assert git_io.in_git_repo() is False


def test_run_git_maps_missing_git_to_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(git_io.subprocess, "run", boom)
    result = git_io._run_git(["rev-parse"])
    assert result.returncode != 0  # synthetic failure, no exception
    assert git_io.in_git_repo() is False


def test_run_git_maps_timeout_to_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise git_io.subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(git_io.subprocess, "run", boom)
    assert git_io._run_git(["diff"]).returncode != 0  # a stalled git never hangs us
    with pytest.raises(RuntimeError):
        git_io.staged_diff()  # surfaces as a normal failure the hook will swallow


def test_staged_diff_returns_stdout(monkeypatch):
    monkeypatch.setattr(git_io, "_run_git", lambda args: _CP(0, "DIFF-BODY"))
    assert git_io.staged_diff() == "DIFF-BODY"


def test_staged_diff_raises_on_failure(monkeypatch):
    monkeypatch.setattr(git_io, "_run_git", lambda args: _CP(1, "", "it broke"))
    with pytest.raises(RuntimeError):
        git_io.staged_diff()


def test_staged_stat_returns_empty_on_failure(monkeypatch):
    monkeypatch.setattr(git_io, "_run_git", lambda args: _CP(1, "", ""))
    assert git_io.staged_stat() == ""


def test_staged_stat_returns_stdout(monkeypatch):
    monkeypatch.setattr(git_io, "_run_git", lambda args: _CP(0, " file | 2 +-"))
    assert "file" in git_io.staged_stat()
