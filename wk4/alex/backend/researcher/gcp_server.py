"""GCP Researcher service using Vertex AI, Playwright MCP, and Cloud Run."""

import logging
import os
from datetime import UTC, datetime
from typing import Optional

from agents import Agent, Runner, trace
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from context import DEFAULT_RESEARCH_PROMPT
from gcp_context import get_agent_instructions
from gcp_tools import ingest_financial_document
from gcp_agents.huggingface_model import create_llm_model, get_llm_config
from mcp_servers import create_playwright_mcp_server

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Alex GCP Researcher", docs_url=None, redoc_url=None)
_MAX_TOPIC_LENGTH = 500


class ResearchConfigurationError(ValueError):
    """The researcher service is missing required deployment configuration."""


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: Optional[str] = Field(default=None, max_length=_MAX_TOPIC_LENGTH)

    @field_validator("topic")
    @classmethod
    def reject_blank_topic(cls, value):
        if value is not None and not value.strip():
            raise ValueError("topic must not be blank")
        return value


def _get_runtime_config():
    try:
        model_name = get_llm_config("researcher").model
    except ValueError as error:
        raise ResearchConfigurationError(str(error)) from error

    missing = ["ALEX_INGESTION_URL"] if not os.environ.get("ALEX_INGESTION_URL") else []
    if missing:
        raise ResearchConfigurationError(
            "Missing GCP researcher configuration: " + ", ".join(missing)
        )
    return model_name


async def run_research_agent(topic: Optional[str] = None) -> str:
    """Run bounded web research and store its result in the GCP knowledge base."""
    _get_runtime_config()

    query = (
        f"Research this investment topic: {topic.strip()}"
        if topic
        else DEFAULT_RESEARCH_PROMPT
    )
    model = create_llm_model("researcher")

    with trace("GCP Researcher"):
        async with create_playwright_mcp_server(
            timeout_seconds=120,
            no_sandbox=False,
            single_process=False,
            debug_logging=False,
        ) as playwright_mcp:
            agent = Agent(
                name="Alex Investment Researcher",
                instructions=get_agent_instructions(),
                model=model,
                tools=[ingest_financial_document],
                mcp_servers=[playwright_mcp],
            )
            result = await Runner.run(
                agent,
                input=query,
                max_turns=20,
            )

    if not isinstance(result.final_output, str) or not result.final_output.strip():
        raise RuntimeError("Research agent returned an empty result")
    return result.final_output


@app.get("/healthz")
async def health():
    return {
        "service": "Alex GCP Researcher",
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.post("/research")
async def research(request: ResearchRequest):
    try:
        return {"research": await run_research_agent(request.topic)}
    except ResearchConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.error("GCP research request failed (%s)", type(error).__name__)
        raise HTTPException(
            status_code=502, detail="Research request failed"
        ) from error


@app.post("/research/auto")
async def research_auto():
    try:
        result = await run_research_agent()
        return {
            "status": "success",
            "timestamp": datetime.now(UTC).isoformat(),
            "message": "Automated research completed",
            "preview": result[:200] + ("..." if len(result) > 200 else ""),
        }
    except ResearchConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.error("GCP automated research failed (%s)", type(error).__name__)
        raise HTTPException(
            status_code=502, detail="Automated research failed"
        ) from error


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
