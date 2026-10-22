"""Groq model configuration shared by the GCP agent services."""

import os

from agents.extensions.models.litellm_model import LitellmModel


def create_groq_model() -> LitellmModel:
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
        raise ValueError("GROQ_MODEL must use the groq/ LiteLLM prefix")
    return LitellmModel(model=model_name)
