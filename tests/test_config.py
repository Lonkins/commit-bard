"""Config resolution: defaults and the environment-override layer.

File-based TOML layers are inert on Python <3.11 (no ``tomllib``) and are made
hermetic for >=3.11 by the autouse ``hermetic_config`` fixture, so these tests
exercise the active Phase-1 mechanism: defaults overlaid by environment.
"""

from commit_bard import config


def test_defaults(clean_env):
    cfg = config.load()
    assert cfg.style == "haiku"
    assert cfg.mode == "dual"
    assert cfg.max_diff_chars == 6000
    assert cfg.random_style is False
    assert cfg.hook_skip_env == "BARD_SKIP"
    assert cfg.hook_on_error == "plain"


def test_env_overrides_style_and_mode(clean_env):
    clean_env.setenv("COMMIT_BARD_STYLE", "noir")
    clean_env.setenv("COMMIT_BARD_MODE", "verse")
    cfg = config.load()
    assert cfg.style == "noir"
    assert cfg.mode == "verse"


def test_env_max_diff_chars_parsed_as_int(clean_env):
    clean_env.setenv("COMMIT_BARD_MAX_DIFF_CHARS", "1234")
    assert config.load().max_diff_chars == 1234


def test_env_max_diff_chars_invalid_keeps_default(clean_env):
    clean_env.setenv("COMMIT_BARD_MAX_DIFF_CHARS", "not-an-int")
    assert config.load().max_diff_chars == 6000


def test_env_random_style_truthy_and_falsey(clean_env):
    clean_env.setenv("COMMIT_BARD_RANDOM_STYLE", "yes")
    assert config.load().random_style is True
    clean_env.setenv("COMMIT_BARD_RANDOM_STYLE", "0")
    assert config.load().random_style is False


def test_history_defaults_off_and_env_toggles(clean_env):
    assert config.load().history is False
    clean_env.setenv("COMMIT_BARD_HISTORY", "true")
    assert config.load().history is True


def test_env_provider_model_base_url(clean_env):
    clean_env.setenv("COMMIT_BARD_PROVIDER", "ollama")
    clean_env.setenv("COMMIT_BARD_MODEL", "my-model")
    clean_env.setenv("COMMIT_BARD_BASE_URL", "http://host:1234/v1")
    cfg = config.load()
    assert cfg.provider == "ollama"
    assert cfg.model == "my-model"
    assert cfg.base_url == "http://host:1234/v1"
