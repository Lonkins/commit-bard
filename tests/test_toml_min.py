"""The tiny TOML-subset parser used on Python 3.9/3.10."""

from commit_bard import toml_min


def test_parses_sections_and_scalar_types():
    data = toml_min.loads(
        "# a comment\n"
        "[bard]\n"
        'style = "noir"\n'
        "max_diff_chars = 10\n"
        "flag = true\n"
        "other = false\n"
        "ratio = 1.5\n"
    )
    assert data["bard"]["style"] == "noir"
    assert data["bard"]["max_diff_chars"] == 10
    assert data["bard"]["flag"] is True
    assert data["bard"]["other"] is False
    assert data["bard"]["ratio"] == 1.5


def test_inline_comment_is_stripped():
    data = toml_min.loads('[a]\nk = "v"  # trailing comment\n')
    assert data["a"]["k"] == "v"


def test_hash_inside_quoted_string_is_kept():
    data = toml_min.loads('[a]\nurl = "http://x/y#frag"\n')
    assert data["a"]["url"] == "http://x/y#frag"


def test_blank_and_comment_lines_ignored():
    data = toml_min.loads("\n\n# just a comment\n[s]\nk = 1\n\n")
    assert data == {"s": {"k": 1}}


def test_load_from_binary_file(tmp_path):
    path = tmp_path / "c.toml"
    path.write_bytes(b"[x]\ny = 1\n")
    with path.open("rb") as handle:
        data = toml_min.load(handle)
    assert data["x"]["y"] == 1


def test_bare_word_treated_as_string():
    assert toml_min.loads("[a]\nk = bareword\n")["a"]["k"] == "bareword"


def test_empty_value_is_empty_string():
    assert toml_min.loads("[a]\nk =\n")["a"]["k"] == ""


def test_unclosed_quote_kept_best_effort():
    # Opening quote, no close: we keep the text rather than crash.
    assert "unclosed" in toml_min.loads('[a]\nk = "unclosed\n')["a"]["k"]


def test_line_without_equals_is_ignored():
    assert toml_min.loads("[a]\nnonsense line\nk = 1\n") == {"a": {"k": 1}}
