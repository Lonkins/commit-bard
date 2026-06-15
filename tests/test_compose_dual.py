"""Dual/plain modes, sentinel parsing, and subject synthesis."""

from commit_bard import compose, mock_corpus, provider, styles


# --- sentinel parsing ------------------------------------------------------


def test_parse_dual_with_sentinel():
    subject, verse = compose._parse_dual("feat: x\n---\nverse a\nverse b")
    assert subject == "feat: x"
    assert verse == "verse a\nverse b"


def test_parse_dual_without_sentinel_returns_none_subject():
    subject, verse = compose._parse_dual("just a verse\nno sentinel here")
    assert subject is None
    assert verse == "just a verse\nno sentinel here"


def test_assemble_dual_indents_verse_as_block():
    out = compose._assemble_dual("feat: x", "line1\nline2")
    assert out == "feat: x\n\n  line1\n  line2"


# --- subject synthesis (offline / fallback) --------------------------------


def test_synthesize_subject_tests_only_is_test():
    diff = "diff --git a/tests/test_x.py b/tests/test_x.py\n@@ -1 +1 @@\n-a\n+b\n"
    assert compose.synthesize_subject(diff).startswith("test")


def test_synthesize_subject_docs_only_is_docs():
    diff = "diff --git a/README.md b/README.md\n@@ -1 +1 @@\n-a\n+b\n"
    assert compose.synthesize_subject(diff).startswith("docs")


def test_synthesize_subject_new_source_is_feat():
    diff = (
        "diff --git a/src/commit_bard/new.py b/src/commit_bard/new.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/src/commit_bard/new.py\n"
        "@@ -0,0 +1 @@\n+x\n"
    )
    assert compose.synthesize_subject(diff).startswith("feat")


def test_synthesize_subject_no_diff_is_chore():
    assert compose.synthesize_subject("not a diff").startswith("chore")


def test_enforce_subject_len_caps_at_72():
    out = compose._enforce_subject_len("feat: " + "word " * 40)
    assert len(out) <= 72


# --- mock-mode end-to-end --------------------------------------------------


def test_dual_mock_produces_subject_and_indented_verse(clean_env):
    out = compose.compose(styles.get_style("haiku"), styles.SAMPLE_DIFF, mode="dual")
    lines = out.splitlines()
    assert ":" in lines[0]  # conventional subject
    assert lines[1] == ""  # blank separator
    body = [ln for ln in lines[2:] if ln.strip()]
    assert body and all(ln.startswith("  ") for ln in body)  # verse indented


def test_plain_mock_is_single_conventional_line(clean_env):
    out = compose.compose(styles.get_style("haiku"), styles.SAMPLE_DIFF, mode="plain")
    assert "\n" not in out.strip()
    assert ":" in out


def test_verse_mode_returns_corpus_verse(clean_env):
    out = compose.compose(styles.get_style("haiku"), styles.SAMPLE_DIFF, mode="verse")
    assert out in mock_corpus.CORPUS["haiku"]


def test_dual_subject_counts_all_files_despite_truncation(clean_env):
    # Subject synthesis must see the FULL diff, not the truncated one.
    files = []
    for i in range(12):
        body = "\n".join(f"+line {j}" for j in range(60))
        files.append(
            f"diff --git a/src/m{i}.py b/src/m{i}.py\nnew file mode 100644\n"
            f"--- /dev/null\n+++ b/src/m{i}.py\n@@ -0,0 +1,60 @@\n{body}\n"
        )
    big = "".join(files)
    out = compose.compose(styles.get_style("haiku"), big, mode="dual", max_diff_chars=500)
    assert "12 files" in out.splitlines()[0]  # counted from the full diff


# --- real-provider dual (urlopen not touched; provider.chat stubbed) -------


def test_dual_real_parses_subject_and_verse(clean_env, monkeypatch):
    cfg = provider.ProviderConfig("anthropic", "m", "https://x", "k")
    monkeypatch.setattr(provider, "chat", lambda *a, **k: "feat(x): do thing\n---\nverse a\nverse b")
    out = compose.compose(styles.get_style("haiku"), styles.SAMPLE_DIFF, mode="dual", config=cfg)
    assert out.startswith("feat(x): do thing")
    assert "  verse a" in out


def test_dual_real_parse_failure_synthesizes_subject(clean_env, monkeypatch):
    cfg = provider.ProviderConfig("openai-compatible", "m", "https://x/v1", "k")
    monkeypatch.setattr(provider, "chat", lambda *a, **k: "a verse with no sentinel")
    out = compose.compose(styles.get_style("haiku"), styles.SAMPLE_DIFF, mode="dual", config=cfg)
    assert ":" in out.splitlines()[0]  # synthesized conventional subject
    assert "a verse with no sentinel" in out


def test_dual_real_empty_verse_triggers_second_pass(clean_env, monkeypatch):
    # Sentinel present but empty body -> dual must not collapse to subject-only.
    cfg = provider.ProviderConfig("anthropic", "m", "https://x", "k")

    def fake_chat(system, user, **kwargs):
        if "Return EXACTLY two parts" in user:  # the dual prompt
            return "feat(x): do thing\n---\n"  # empty verse body
        return "second pass verse"  # the follow-up verse prompt

    monkeypatch.setattr(provider, "chat", fake_chat)
    out = compose.compose(styles.get_style("haiku"), styles.SAMPLE_DIFF, mode="dual", config=cfg)
    assert out.startswith("feat(x): do thing")
    assert "second pass verse" in out
