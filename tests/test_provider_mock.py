"""The provider spine: auto-detect, env precedence, and the mock backend."""

from commit_bard import mock_corpus, provider, styles


def test_current_provider_defaults_to_mock(clean_env):
    assert provider.current_provider() == "mock"


def test_autodetect_anthropic_from_key(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert provider.current_provider() == "anthropic"


def test_autodetect_openai_from_key(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-test")
    assert provider.current_provider() == "openai-compatible"


def test_explicit_provider_overrides_autodetect(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")
    clean_env.setenv("COMMIT_BARD_PROVIDER", "mock")
    assert provider.current_provider() == "mock"


def test_resolve_uses_default_model_and_base(clean_env):
    cfg = provider.resolve(provider="anthropic")
    assert cfg.model == provider.DEFAULT_MODELS["anthropic"]
    assert cfg.base_url == provider.DEFAULT_BASE_URLS["anthropic"].rstrip("/")


def test_resolve_model_override_wins(clean_env):
    clean_env.setenv("COMMIT_BARD_MODEL", "env-model")
    # explicit arg beats env
    cfg = provider.resolve(provider="anthropic", model="arg-model")
    assert cfg.model == "arg-model"
    # env beats default
    cfg2 = provider.resolve(provider="anthropic")
    assert cfg2.model == "env-model"


def test_unknown_provider_raises(clean_env):
    try:
        provider.resolve(provider="banana")
    except provider.ProviderError:
        return
    raise AssertionError("expected ProviderError for unknown provider")


def test_mock_reply_nonempty_and_on_theme_per_style():
    for name in styles.style_names():
        user = f"Write it as ... (style: {name})\n\nDIFF:\nx"
        out = mock_corpus.reply("system", user, seed=0)
        assert isinstance(out, str) and out.strip()
        # On-theme means it's a genuine curated verse for that style.
        assert out in mock_corpus.CORPUS[name]


def test_mock_reply_deterministic_with_seed():
    user = "render this (style: haiku)"
    assert mock_corpus.reply("s", user, seed=7) == mock_corpus.reply("s", user, seed=7)


def test_detect_style_prefers_tag():
    assert mock_corpus.detect_style("blah (style: pirate) blah") == "pirate"


def test_detect_style_falls_back_to_default():
    assert mock_corpus.detect_style("no style mentioned here") == styles.DEFAULT_STYLE


def test_chat_mock_never_hits_network(clean_env):
    out = provider.chat("system", "make it (style: shanty)\nDIFF: x")
    assert out.strip()


def test_chat_mock_returns_a_real_corpus_verse(clean_env):
    out = provider.chat("system", "make it (style: epic)\nDIFF: x")
    assert out in mock_corpus.CORPUS["epic"]


def test_seed_actually_drives_selection():
    # Across several seeds a multi-verse style must yield more than one verse,
    # proving the seed selects rather than always returning the same index.
    user = "render (style: haiku)"
    outputs = {mock_corpus.reply("s", user, seed=i) for i in range(10)}
    assert len(outputs) > 1


# --- API key precedence (spec §4.2) ---------------------------------------


def test_api_key_generic_takes_precedence(clean_env):
    clean_env.setenv("COMMIT_BARD_API_KEY", "generic")
    clean_env.setenv("ANTHROPIC_API_KEY", "anthro")
    assert provider.resolve(provider="anthropic").api_key == "generic"


def test_api_key_anthropic_fallback(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "anthro")
    assert provider.resolve(provider="anthropic").api_key == "anthro"


def test_api_key_openai_fallback_for_openai_and_ollama(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "oai")
    assert provider.resolve(provider="openai-compatible").api_key == "oai"
    # ollama honors OPENAI_API_KEY too (gateways may require one).
    assert provider.resolve(provider="ollama").api_key == "oai"


def test_api_key_empty_for_ollama_without_keys(clean_env):
    assert provider.resolve(provider="ollama").api_key == ""
