"""Load OpenAI-compatible API settings from layered TOML files."""

from importlib.resources import files
from pathlib import Path
import tomllib

from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict, Field


class OpenAIConfig(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", hide_input_in_errors=True,
    )

    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_retries: int = Field(ge=0)


def load_config(config_file: Path | None = None) -> OpenAIConfig:
    sources = [
        (files("srt_translate").joinpath("config.default.toml"), True),
        (user_config_path("srt-translate", appauthor=False) / "config.toml", False),
    ]
    if config_file is not None:
        sources.append((config_file.resolve(), True))

    values = {}
    for path, required in sources:
        try:
            with path.open("rb") as stream:
                layer = tomllib.load(stream)
            unknown = layer.keys() - {"openai"}
            if unknown:
                raise ValueError(f"unknown configuration section(s): {', '.join(sorted(unknown))}")
            overrides = layer.get("openai", {})
            if not isinstance(overrides, dict):
                raise ValueError("openai must be a TOML table")
            settings = OpenAIConfig.model_validate(values | overrides)
            values = settings.model_dump()
        except FileNotFoundError as exc:
            if not required:
                continue
            raise ValueError(f"{path}: configuration file does not exist") from exc
        except (OSError, ValueError) as exc:
            raise ValueError(f"{path}: {exc}") from exc
    return settings
