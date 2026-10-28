import json
import os
from pathlib import Path
from typing import NamedTuple

from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI


_CONFIG_PATH = Path(__file__).with_name("llm_config.json")


class LLMConfig(NamedTuple):
    provider: str
    base_url: str
    api_key_env: str
    api_key: str
    model: str


def get_llm_config(role: str = "agents") -> LLMConfig:
    """Resolve provider, credentials, and model from shared config and runtime env."""
    with _CONFIG_PATH.open(encoding="utf-8") as config_file:
        config = json.load(config_file)

    provider_name = os.environ.get("ALEX_LLM_PROVIDER", config["default_provider"])
    provider = config["providers"].get(provider_name)
    if provider is None:
        supported = ", ".join(sorted(config["providers"]))
        raise ValueError(
            f"Unsupported ALEX_LLM_PROVIDER {provider_name!r}; choose from {supported}"
        )

    api_key_env = provider["api_key_env"]
    if not isinstance(api_key_env, str) or not api_key_env:
        raise ValueError(f"Provider configuration for {provider_name!r} is invalid")

    model_name = os.environ.get("ALEX_LLM_MODEL") or config["models"].get(
        role, {}
    ).get(provider_name)
    api_key = os.environ.get(api_key_env)
    if not isinstance(model_name, str) or not model_name:
        raise ValueError("Missing LLM configuration: ALEX_LLM_MODEL")
    if not isinstance(api_key, str) or not api_key:
        raise ValueError(f"Missing LLM configuration: {api_key_env}")

    return LLMConfig(
        provider=provider_name,
        base_url=provider["base_url"],
        api_key_env=api_key_env,
        api_key=api_key,
        model=model_name,
    )


def create_llm_model(role: str = "agents") -> OpenAIChatCompletionsModel:
    """Create an Agents SDK model using the shared provider configuration."""
    config = get_llm_config(role)
    client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
    return OpenAIChatCompletionsModel(model=config.model, openai_client=client)


def create_huggingface_model(role: str = "agents") -> OpenAIChatCompletionsModel:
    """Backward-compatible alias for create_llm_model."""
    return create_llm_model(role)
