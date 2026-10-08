import pytest

from srt_translate.config import load_config


pytestmark = pytest.mark.usefixtures("user_config_file")


def test_packaged_defaults_without_user_configuration(user_config_file):
    assert load_config().model_dump() == {
        "base_url": "http://127.0.0.1:8317/v1",
        "api_key": "123456",
        "model": "gemini-3.8-flash-high",
        "max_retries": 2,
    }
    assert not user_config_file.exists()


def test_partial_layers_and_reloading(tmp_path, user_config_file):
    user_config_file.write_text('[openai]\napi_key = "user-key"\nmodel = "user-model"\n', encoding="utf-8")
    explicit = tmp_path / "explicit.toml"
    explicit.write_text('[openai]\nmodel = "explicit-model"\n', encoding="utf-8")
    assert load_config(explicit).model_dump() == {
        "base_url": "http://127.0.0.1:8317/v1",
        "api_key": "user-key",
        "model": "explicit-model",
        "max_retries": 2,
    }
    user_config_file.write_text('[openai]\napi_key = "changed-key"\n', encoding="utf-8")
    assert load_config(explicit).api_key == "changed-key"
    assert load_config().model == "gemini-3.8-flash-high"


def test_explicit_configuration_without_user_file(tmp_path):
    explicit = tmp_path / "explicit.toml"
    explicit.write_text('[openai]\nmax_retries = 0\n', encoding="utf-8")
    settings = load_config(explicit)
    assert settings.max_retries == 0
    assert settings.api_key == "123456"


@pytest.mark.parametrize("contents", ["", "[openai]\n"])
def test_empty_overrides_keep_defaults(tmp_path, user_config_file, contents):
    defaults = load_config()
    user_config_file.write_text(contents, encoding="utf-8")
    explicit = tmp_path / "empty.toml"
    explicit.write_text(contents, encoding="utf-8")
    assert load_config(explicit) == defaults


@pytest.mark.parametrize("layer", ["user", "explicit"])
@pytest.mark.parametrize("contents,field", [
    ('[openai\n', None),
    ('[other]\nmodel = "test"\n', "other"),
    ('openai = "test"\n', "openai"),
    ('[openai]\nmodle = "test"\n', "modle"),
    ('[openai]\nbase_url = 123\n', "base_url"),
    ('[openai]\napi_key = 123456\n', "api_key"),
    ('[openai]\nmodel = false\n', "model"),
    ('[openai]\nmodel = ""\n', "model"),
    ('[openai]\nmax_retries = -1\n', "max_retries"),
    ('[openai]\nmax_retries = "2"\n', "max_retries"),
    ('[openai]\nmax_retries = 2.0\n', "max_retries"),
    ('[openai]\nmax_retries = true\n', "max_retries"),
])
def test_invalid_configuration_identifies_file_and_field(tmp_path, user_config_file, layer, contents, field):
    path = user_config_file if layer == "user" else tmp_path / "explicit.toml"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        load_config(None if layer == "user" else path)
    assert str(path) in str(caught.value)
    if field is not None:
        assert field in str(caught.value)


def test_explicit_override_does_not_hide_invalid_user_configuration(tmp_path, user_config_file):
    user_config_file.write_text('[openai]\nmodel = 42\n', encoding="utf-8")
    explicit = tmp_path / "explicit.toml"
    explicit.write_text('[openai]\nmodel = "valid-model"\n', encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        load_config(explicit)
    assert str(user_config_file) in str(caught.value)


def test_missing_explicit_file_is_an_error(tmp_path):
    path = tmp_path / "missing.toml"
    with pytest.raises(ValueError) as caught:
        load_config(path)
    assert str(path) in str(caught.value)
    assert "does not exist" in str(caught.value)


def test_directory_is_not_treated_as_missing_user_configuration(user_config_file):
    user_config_file.mkdir()
    with pytest.raises(ValueError) as caught:
        load_config()
    assert str(user_config_file) in str(caught.value)


def test_validation_errors_do_not_echo_api_key(user_config_file):
    user_config_file.write_text('[openai]\napi_key = ["private-test-key"]\n', encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        load_config()
    assert "api_key" in str(caught.value)
    assert "private-test-key" not in str(caught.value)
