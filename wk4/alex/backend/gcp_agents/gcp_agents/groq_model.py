"""Groq model configuration shared by the GCP agent services."""

import os

from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

GROQ_API_BASE_URL = "https://api.groq.com/openai/v1"


def create_groq_model() -> OpenAIChatCompletionsModel:
    api_key = os.environ.get("GROQ_API_KEY")
    model_name = os.environ.get("GROQ_MODEL")
    missing = [
        name
        for name, value in (("GROQ_API_KEY", api_key), ("GROQ_MODEL", model_name))
        if not value
    ]
    if missing:
        raise ValueError("Missing Groq configuration: " + ", ".join(missing))
    if not model_name.startswith("groq/"):
        raise ValueError("GROQ_MODEL must use the groq/ model prefix")

    client = AsyncOpenAI(api_key=api_key, base_url=GROQ_API_BASE_URL)
    return OpenAIChatCompletionsModel(
        model=model_name.removeprefix("groq/"),
        openai_client=client,
    )
