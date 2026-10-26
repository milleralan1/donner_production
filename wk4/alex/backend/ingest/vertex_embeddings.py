"""Generate text embeddings with Vertex AI."""

import math
import os
from typing import List, Optional


class VertexEmbeddingClient:
    """Generate task-aware text embeddings through the Google Gen AI SDK."""

    def __init__(
        self,
        model: Optional[str] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
        output_dimensionality: Optional[int] = None,
        client=None,
    ):
        self.model = model or os.environ.get("EMBEDDING_MODEL")
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = (
            location
            or os.environ.get("GOOGLE_CLOUD_LOCATION")
            or os.environ.get("GOOGLE_CLOUD_REGION")
        )
        dimension = output_dimensionality or os.environ.get(
            "EMBEDDING_OUTPUT_DIMENSIONALITY"
        )
        self.output_dimensionality = int(dimension) if dimension else None

        missing = [
            name
            for name, value in (
                ("EMBEDDING_MODEL", self.model),
                ("GOOGLE_CLOUD_PROJECT", self.project),
                ("GOOGLE_CLOUD_LOCATION", self.location),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing Vertex AI embedding configuration: " + ", ".join(missing)
            )
        if self.output_dimensionality is not None and self.output_dimensionality <= 0:
            raise ValueError("EMBEDDING_OUTPUT_DIMENSIONALITY must be positive")

        if client is None:
            try:
                from google import genai
            except ImportError as error:
                raise ImportError(
                    "Vertex AI embeddings require the GCP extra. "
                    "Install with `uv sync --extra gcp`."
                ) from error

            client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
            )
        self.client = client

    def embed(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[float]:
        """Return one validated embedding for a document or retrieval query."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding input text must be a non-empty string")
        if task_type not in {"RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"}:
            raise ValueError(
                "task_type must be RETRIEVAL_DOCUMENT or RETRIEVAL_QUERY"
            )

        try:
            from google.genai import types
        except ImportError as error:
            raise ImportError(
                "Vertex AI embeddings require the GCP extra. "
                "Install with `uv sync --extra gcp`."
            ) from error

        config_args = {"task_type": task_type}
        if self.output_dimensionality is not None:
            config_args["output_dimensionality"] = self.output_dimensionality

        response = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(**config_args),
        )
        embeddings = getattr(response, "embeddings", None)
        if not embeddings or not getattr(embeddings[0], "values", None):
            raise RuntimeError("Vertex AI returned no embedding values")

        values = list(embeddings[0].values)
        if self.output_dimensionality and len(values) != self.output_dimensionality:
            raise RuntimeError(
                "Vertex AI embedding dimension mismatch: expected "
                f"{self.output_dimensionality}, received {len(values)}"
            )
        if any(
            not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in values
        ):
            raise RuntimeError("Vertex AI returned invalid embedding values")
        return [float(value) for value in values]
