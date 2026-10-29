"""Generate text embeddings through the Nscale OpenAI-compatible API."""

import math
import os
from typing import List, Optional


class NscaleEmbeddingClient:
    """Generate and validate embeddings using Nscale serverless inference."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        output_dimensionality: Optional[int] = None,
        client=None,
    ):
        self.model = model or os.environ.get("EMBEDDING_MODEL")
        self.api_key = api_key or os.environ.get("NSCALE_API_KEY")
        self.base_url = (
            base_url
            or os.environ.get("NSCALE_BASE_URL")
            or "https://inference.api.nscale.com/v1"
        )
        dimension = output_dimensionality or os.environ.get(
            "EMBEDDING_OUTPUT_DIMENSIONALITY"
        )
        self.output_dimensionality = int(dimension) if dimension else None

        missing = [
            name
            for name, value in (
                ("EMBEDDING_MODEL", self.model),
                ("NSCALE_API_KEY", self.api_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing Nscale embedding configuration: " + ", ".join(missing)
            )
        if self.output_dimensionality is not None and self.output_dimensionality <= 0:
            raise ValueError("EMBEDDING_OUTPUT_DIMENSIONALITY must be positive")

        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ImportError(
                    "Nscale embeddings require the OpenAI Python SDK. "
                    "Install project dependencies with `uv sync`."
                ) from error
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.client = client

    def embed(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[float]:
        """Return one validated embedding; Nscale does not use task_type."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding input text must be a non-empty string")
        if task_type not in {"RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"}:
            raise ValueError(
                "task_type must be RETRIEVAL_DOCUMENT or RETRIEVAL_QUERY"
            )

        request = {"model": self.model, "input": text}
        if self.output_dimensionality is not None:
            request["dimensions"] = self.output_dimensionality
        response = self.client.embeddings.create(**request)
        data = getattr(response, "data", None)
        embedding = getattr(data[0], "embedding", None) if data else None
        if not embedding:
            raise RuntimeError("Nscale returned no embedding values")

        values = list(embedding)
        if (
            self.output_dimensionality is not None
            and len(values) != self.output_dimensionality
        ):
            raise RuntimeError(
                "Nscale embedding dimension mismatch: expected "
                f"{self.output_dimensionality}, received {len(values)}"
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise RuntimeError("Nscale returned invalid embedding values")
        return [float(value) for value in values]
