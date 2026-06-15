"""Style data integrity and corpus coverage."""

from commit_bard import mock_corpus, styles


def test_every_style_is_well_formed():
    for name, style in styles.STYLES.items():
        assert style.name == name
        assert style.instruction.strip()
        assert style.blurb.strip()


def test_default_style_exists():
    assert styles.DEFAULT_STYLE in styles.STYLES


def test_sample_diff_looks_like_a_diff():
    assert "diff --git" in styles.SAMPLE_DIFF
    assert "tokenizer" in styles.SAMPLE_DIFF


def test_every_style_has_at_least_one_corpus_verse():
    for name in styles.style_names():
        verses = mock_corpus.CORPUS.get(name)
        assert verses, f"no mock verses for style {name!r}"
        assert all(v.strip() for v in verses)


def test_style_names_preserve_curated_order():
    assert styles.style_names()[0] == "haiku"
    assert set(styles.style_names()) == set(styles.STYLES)


def test_first_corpus_entry_nods_at_the_sample_diff():
    # The sample diff is a tokenizer that skips comments; the first verse of
    # each style should reference that so `--sample` reads as apt.
    keywords = ("comment", "parser", "token")
    for name in styles.style_names():
        first = mock_corpus.CORPUS[name][0].lower()
        assert any(word in first for word in keywords), name
