"""Input limits for user-controlled analysis requests."""

import json
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator


class AnalyzeRequest(BaseModel):
    analysis_type: str = Field(
        default="portfolio",
        min_length=1,
        max_length=64,
        description="Type of analysis to perform",
    )
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Analysis options",
    )

    @field_validator("options")
    @classmethod
    def validate_options(cls, options: Dict[str, Any]) -> Dict[str, Any]:
        if len(options) > 32:
            raise ValueError("options must contain at most 32 entries")

        serialized = json.dumps(
            options,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        if len(serialized.encode("utf-8")) > 16_384:
            raise ValueError("serialized options must be at most 16384 bytes")
        return options
