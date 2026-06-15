"""Config file loading and the defaults -> user -> repo -> env precedence."""

from commit_bard import config


def test_load_toml_maps_tables_to_fields(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[bard]\n"
        'style = "noir"\n'
        'mode = "verse"\n'
        "max_diff_chars = 1234\n"
        "[provider]\n"
        'provider = "ollama"\n'
        "[hook]\n"
        "timeout_s = 5\n"
    )
    overrides = config._load_toml(path)
    assert overrides["style"] == "noir"
    assert overrides["mode"] == "verse"
    assert overrides["max_diff_chars"] == 1234
    assert overrides["provider"] == "ollama"
    assert overrides["hook_timeout_s"] == 5


def test_missing_file_yields_no_overrides(tmp_path):
    assert config._load_toml(tmp_path / "nope.toml") == {}


def test_repo_overrides_user_and_env_overrides_both(clean_env, tmp_path, monkeypatch):
    user = tmp_path / "user.toml"
    user.write_text('[bard]\nstyle = "epic"\nmode = "verse"\n')
    repo = tmp_path / "repo.toml"
    repo.write_text('[bard]\nstyle = "pirate"\n')
    # Override the hermetic stubs to point at our temp files.
    monkeypatch.setattr(config, "_user_config_path", lambda: user)
    monkeypatch.setattr(config, "_repo_config_path", lambda: repo)

    cfg = config.load()
    assert cfg.style == "pirate"  # repo beats user
    assert cfg.mode == "verse"  # inherited from user (repo didn't set it)

    clean_env.setenv("COMMIT_BARD_STYLE", "haiku")
    assert config.load().style == "haiku"  # env beats files


def test_repo_config_cannot_redirect_provider_routing(clean_env, tmp_path, monkeypatch):
    # SECURITY: a checked-in repo file may theme the verse but must NOT set
    # provider/model/base_url (which could exfiltrate the API key + diff).
    repo = tmp_path / "repo.toml"
    repo.write_text(
        "[provider]\n"
        'provider = "anthropic"\n'
        'base_url = "https://evil.example"\n'
        'model = "x"\n'
        "[bard]\n"
        'style = "noir"\n'
    )
    monkeypatch.setattr(config, "_repo_config_path", lambda: repo)
    monkeypatch.setattr(config, "_user_config_path", lambda: tmp_path / "absent.toml")
    cfg = config.load()
    assert cfg.style == "noir"  # safe theming honored
    assert cfg.base_url == ""  # provider routing ignored from repo file
    assert cfg.provider == ""
    assert cfg.model == ""


def test_user_config_may_set_base_url(clean_env, tmp_path, monkeypatch):
    user = tmp_path / "user.toml"
    user.write_text('[provider]\nbase_url = "https://my-gateway"\n')
    monkeypatch.setattr(config, "_user_config_path", lambda: user)
    assert config.load().base_url == "https://my-gateway"  # user file is trusted


def test_api_keys_are_never_read_from_toml(clean_env, tmp_path, monkeypatch):
    user = tmp_path / "user.toml"
    user.write_text(
        '[provider]\napi_key = "sk-leak"\nkey = "sk-leak2"\ntoken = "sk-leak3"\n'
    )
    monkeypatch.setattr(config, "_user_config_path", lambda: user)
    cfg = config.load()
    assert not hasattr(cfg, "api_key")
    assert "sk-leak" not in repr(cfg)  # no secret made it into the config


def test_bad_int_in_config_keeps_default(clean_env, tmp_path, monkeypatch):
    user = tmp_path / "user.toml"
    user.write_text('[bard]\nmax_diff_chars = "lots"\n')
    monkeypatch.setattr(config, "_user_config_path", lambda: user)
    assert config.load().max_diff_chars == 6000  # bad value dropped, no crash


def test_malformed_config_degrades_to_defaults(clean_env, tmp_path, monkeypatch):
    user = tmp_path / "user.toml"
    user.write_text("[bad section\nstyle = \n  = = =\n")  # invalid TOML
    monkeypatch.setattr(config, "_user_config_path", lambda: user)
    cfg = config.load()  # must not raise
    assert cfg.style == "haiku"  # defaults stand
