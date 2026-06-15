"""The prepare-commit-msg hook: runtime never blocks, install/uninstall, and a
real end-to-end commit."""

import os
import subprocess
import sys
from dataclasses import replace

from commit_bard import compose, config, git_io, hook, provider, styles


def _raise_provider_error(*args, **kwargs):
    raise provider.ProviderError("boom")


# --- run_hook: never raises, always returns 0 ------------------------------


def test_run_hook_writes_message_above_template(clean_env, tmp_path, monkeypatch):
    monkeypatch.setattr(git_io, "staged_diff", lambda: styles.SAMPLE_DIFF)
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("\n# Please enter the commit message for your changes.\n")

    assert hook.run_hook(str(msg)) == 0
    content = msg.read_text()
    assert content.strip()
    assert "# Please enter the commit message" in content  # template preserved
    assert not content.lstrip().startswith("#")  # our message is on top


def test_run_hook_no_staged_diff_leaves_file_untouched(clean_env, tmp_path, monkeypatch):
    monkeypatch.setattr(git_io, "staged_diff", lambda: "")
    msg = tmp_path / "m"
    msg.write_text("ORIGINAL")
    assert hook.run_hook(str(msg)) == 0
    assert msg.read_text() == "ORIGINAL"


def test_run_hook_on_error_plain_writes_fallback(clean_env, tmp_path, monkeypatch):
    monkeypatch.setattr(git_io, "staged_diff", lambda: styles.SAMPLE_DIFF)
    monkeypatch.setattr(compose, "compose_detailed", _raise_provider_error)
    msg = tmp_path / "m"
    msg.write_text("")
    assert hook.run_hook(str(msg)) == 0
    assert msg.read_text().strip()  # fallback plain subject written


def test_run_hook_on_error_skip_leaves_file(clean_env, tmp_path, monkeypatch):
    monkeypatch.setattr(git_io, "staged_diff", lambda: styles.SAMPLE_DIFF)
    monkeypatch.setattr(compose, "compose_detailed", _raise_provider_error)
    monkeypatch.setattr(config, "load", lambda: replace(config.Config(), hook_on_error="skip"))
    msg = tmp_path / "m"
    msg.write_text("ORIGINAL")
    assert hook.run_hook(str(msg)) == 0
    assert msg.read_text() == "ORIGINAL"


def test_run_hook_swallows_unexpected_errors(clean_env, tmp_path, monkeypatch):
    def explode():
        raise RuntimeError("git is on fire")

    monkeypatch.setattr(git_io, "staged_diff", explode)
    msg = tmp_path / "m"
    msg.write_text("ORIG")
    assert hook.run_hook(str(msg)) == 0  # never raises, never blocks


# --- install / uninstall ---------------------------------------------------


def test_install_then_uninstall(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    target, _ = hook.install_hook()
    assert target.exists()
    assert os.access(target, os.X_OK)
    assert hook._MARKER in target.read_text()

    hook.uninstall_hook()
    assert not target.exists()


def test_install_backs_up_foreign_hook(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "prepare-commit-msg").write_text("#!/bin/sh\necho preexisting\n")

    hook.install_hook()
    backup = hooks / "prepare-commit-msg.bard.bak"
    assert backup.exists()
    assert "preexisting" in backup.read_text()
    # uninstall restores the foreign hook
    hook.uninstall_hook()
    assert "preexisting" in (hooks / "prepare-commit-msg").read_text()


# --- end-to-end: an installed hook never blocks a real commit --------------


def test_installed_hook_never_blocks_real_commit(clean_env, tmp_path, monkeypatch):
    repo = tmp_path

    # Hermetic: disable the developer's global/system git config (commit.template,
    # core.hooksPath, init.templateDir) so the test can't be steered by it.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    def run(*args):
        return subprocess.run(list(args), cwd=repo, check=True, capture_output=True, text=True)

    run("git", "init", "-q")
    run("git", "config", "user.email", "tester@example.com")
    run("git", "config", "user.name", "Tester")
    run("git", "config", "core.editor", "true")  # no-op editor accepts prefilled msg
    monkeypatch.chdir(repo)

    hook.install_hook()
    (repo / "a.txt").write_text("hello\n")
    run("git", "add", "a.txt")

    # Bare commit (no global template -> source is empty) -> hook versifies;
    # editor "true" accepts the prefilled message.
    result = subprocess.run(["git", "commit"], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    message = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert message.strip()  # a message landed
    assert ":" in message.splitlines()[0]  # conventional subject (dual mode)


# --- installed shim skip branches (run the real shell script directly) -----


def _install_in_tmp_repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    target, _ = hook.install_hook()
    return target


def test_shim_skips_when_skip_env_set(tmp_path, monkeypatch):
    target = _install_in_tmp_repo(tmp_path, monkeypatch)
    msg = tmp_path / "MSG"
    msg.write_text("ORIGINAL\n")
    env = {**os.environ, "BARD_SKIP": "1"}
    subprocess.run(["bash", str(target), str(msg)], check=True, env=env)
    assert msg.read_text() == "ORIGINAL\n"  # escape hatch -> untouched


def test_shim_skips_message_source(tmp_path, monkeypatch):
    target = _install_in_tmp_repo(tmp_path, monkeypatch)
    msg = tmp_path / "MSG"
    msg.write_text("ORIGINAL\n")
    env = {k: v for k, v in os.environ.items() if k != "BARD_SKIP"}
    subprocess.run(["bash", str(target), str(msg), "message"], check=True, env=env)
    assert msg.read_text() == "ORIGINAL\n"  # -m/-F source left alone


# --- _shim_text: safe substitution -----------------------------------------


def test_shim_text_single_quotes_interpreter(monkeypatch):
    monkeypatch.setattr(sys, "executable", "/weird/$DANGER/`cmd`/python")
    text = hook._shim_text("BARD_SKIP")
    assert "'/weird/$DANGER/`cmd`/python'" in text  # single-quoted; no expansion
    assert hook._PYTHON_TOKEN not in text


def test_shim_text_wires_configured_skip_env():
    text = hook._shim_text("MY_SKIP")
    assert "${MY_SKIP:-}" in text
    assert hook._SKIP_ENV_TOKEN not in text


def test_shim_text_sanitizes_invalid_skip_env():
    text = hook._shim_text("BAD; rm -rf /")  # not a valid shell identifier
    assert "${BARD_SKIP:-}" in text  # falls back to the safe default


# --- _select_style: random_style honored -----------------------------------


def test_select_style_honors_random(monkeypatch):
    monkeypatch.setattr("random.choice", lambda seq: "pirate")
    assert hook._select_style(replace(config.Config(), random_style=True)).name == "pirate"


def test_select_style_uses_configured_style_when_not_random():
    cfg = replace(config.Config(), random_style=False, style="noir")
    assert hook._select_style(cfg).name == "noir"
