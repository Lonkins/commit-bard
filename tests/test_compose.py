"""Prompt building and reply post-processing."""

from commit_bard import compose, styles


def test_postprocess_strips_code_fences():
    assert compose.postprocess("```\nhello\nworld\n```") == "hello\nworld"


def test_postprocess_strips_fences_with_language():
    assert compose.postprocess("```text\nhi\n```") == "hi"


def test_postprocess_strips_wrapping_quotes():
    assert compose.postprocess('"a tidy haiku"') == "a tidy haiku"


def test_postprocess_strips_curly_quotes():
    assert compose.postprocess("“curly”") == "curly"


def test_postprocess_collapses_blank_runs():
    assert compose.postprocess("a\n\n\n\nb") == "a\n\nb"


def test_postprocess_trims_trailing_whitespace():
    assert compose.postprocess("a   \nb\t") == "a\nb"


def test_postprocess_handles_empty():
    assert compose.postprocess("   ") == ""


def test_build_user_prompt_mentions_style_and_diff():
    prompt = compose.build_user_prompt(styles.get_style("haiku"), "THE-DIFF")
    assert "style: haiku" in prompt
    assert "THE-DIFF" in prompt


def test_postprocess_strips_fence_with_same_line_close():
    # The bug the review caught: closing ``` on the same line as the content.
    assert compose.postprocess("```\ncommit message```") == "commit message"


def test_postprocess_strips_lang_fence_with_same_line_close():
    assert compose.postprocess("```text\nhi```") == "hi"


def test_postprocess_unbalanced_quote_is_preserved():
    assert compose.postprocess('"only-open') == '"only-open'


def test_postprocess_single_char_does_not_crash():
    assert compose.postprocess("x") == "x"


def test_postprocess_unterminated_fence_is_preserved():
    assert compose.postprocess("```py\nno close fence") == "```py\nno close fence"


def test_postprocess_fence_then_inner_quote():
    assert compose.postprocess('```\n"quoted inside"\n```') == "quoted inside"


def test_compose_end_to_end_with_mock(clean_env):
    out = compose.compose(styles.get_style("limerick"), "diff text")
    assert out.strip()
