"""Large-diff truncation: structural summary, packing, noise omission."""

from commit_bard import truncate


def _big_diff(n_files=6, lines_per=200):
    parts = []
    for i in range(n_files):
        body = "\n".join(f"+line {j}" for j in range(lines_per))
        parts.append(
            f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n"
            f"@@ -0,0 +1,{lines_per} @@\n{body}\n"
        )
    return "".join(parts)


def test_small_diff_passes_through_unchanged():
    diff = "diff --git a/x.py b/x.py\n@@ -1 +1 @@\n+a\n"
    assert truncate.truncate_diff(diff, 6000) == diff


def test_large_diff_is_summarized_and_bounded():
    big = _big_diff()
    assert len(big) > 2000
    out = truncate.truncate_diff(big, 2000)
    assert "changed files:" in out  # structural shape included
    assert "files shown" in out  # truncation marker
    assert len(out) <= 2000  # the real contract: never exceed the budget


def test_noise_files_summarized_not_inlined():
    lock_body = "+x\n" * 2000  # ~6 KB so we exceed the budget
    diff = (
        f"diff --git a/yarn.lock b/yarn.lock\n--- a/yarn.lock\n+++ b/yarn.lock\n"
        f"@@ -0,0 +1,2000 @@\n{lock_body}"
        "diff --git a/data.bin b/data.bin\n"
        "Binary files a/data.bin and b/data.bin differ\n"
        "diff --git a/real.py b/real.py\n--- a/real.py\n+++ b/real.py\n"
        "@@ -0,0 +1 @@\n+code\n"
    )
    out = truncate.truncate_diff(diff, 1500)
    assert "yarn.lock" in out  # listed in the stat block
    assert "data.bin" in out  # listed in the stat block
    assert "Binary files" not in out  # binary content not inlined
    assert "+code" in out  # the real file is inlined
    assert out.count("+x") == 0  # lockfile hunk omitted from the body


def test_noise_only_diff_does_not_leak_content():
    # A lockfile-only change must not re-leak its content via the hard-trim path.
    lock_body = "+dep@1.0\n" * 500
    diff = (
        "diff --git a/yarn.lock b/yarn.lock\n--- a/yarn.lock\n+++ b/yarn.lock\n"
        f"@@ -0,0 +1,500 @@\n{lock_body}"
    )
    out = truncate.truncate_diff(diff, 300)
    assert "yarn.lock" in out  # listed in the stat block
    assert "(omitted)" in out  # tagged as omitted
    assert "dep@1.0" not in out  # content never inlined
    assert len(out) <= 300


def test_unparseable_diff_is_hard_trimmed():
    blob = "x" * 10000  # no 'diff --git' boundaries
    out = truncate.truncate_diff(blob, 1000)
    assert len(out) <= 1000 + 50
    assert "truncated" in out
