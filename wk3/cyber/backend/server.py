import tempfile  # to create a file on disk for semgrep_scan
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import (
    Agent,
    ModelSettings,
    OpenAIChatCompletionsModel,
    Runner,
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
    trace,
)

from context import SECURITY_RESEARCHER_INSTRUCTIONS, get_analysis_prompt, enhance_summary
from mcp_servers import create_semgrep_server

load_dotenv(override=True)

OPENAI_MODEL = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
openai_base_url = os.getenv("OPENAI_BASE_URL")
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = None

if openai_base_url and openai_api_key:
    openai_client = AsyncOpenAI(api_key=openai_api_key, base_url=openai_base_url)
    set_default_openai_client(
        openai_client,
        use_for_tracing=False,
    )
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)

app = FastAPI(title="Cybersecurity Analyzer API")

# Configure CORS for development and production
cors_origins = [
    "http://localhost:3000",  # Local development
    "http://frontend:3000",  # Docker development
]

# In production, allow same-origin requests (static files served from same domain)
if os.getenv("ENVIRONMENT") == "production":
    cors_origins.append(
        "*"
    )  # Allow all origins in production since we serve frontend from same domain

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    code: str


class SecurityIssue(BaseModel):
    title: str = Field(description="Brief title of the security vulnerability")
    description: str = Field(
        description="Detailed description of the security issue and its potential impact"
    )
    code: str = Field(
        description="The specific vulnerable code snippet that demonstrates the issue"
    )
    fix: str = Field(description="Recommended code fix or mitigation strategy")
    cvss_score: float = Field(description="CVSS score from 0.0 to 10.0 representing severity")
    severity: str = Field(description="Severity level: critical, high, medium, or low")


class SecurityReport(BaseModel):
    summary: str = Field(description="Executive summary of the security analysis")
    issues: List[SecurityIssue] = Field(description="List of identified security vulnerabilities")


def validate_request(request: AnalyzeRequest) -> None:
    """Validate the analysis request."""
    if not request.code.strip():
        raise HTTPException(status_code=400, detail="No code provided for analysis")


def check_api_keys() -> None:
    """Verify required API keys are configured."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")


def create_security_agent(semgrep_server) -> Agent:
    """Create and configure the security analysis agent."""
    model = (
        OpenAIChatCompletionsModel(model=OPENAI_MODEL, openai_client=openai_client)
        if openai_client
        else OPENAI_MODEL
    )
    model_settings = ModelSettings()
    if openai_base_url and "api.groq.com" in openai_base_url:
        model_settings = ModelSettings(
            extra_body={
                "reasoning_effort": "low",
                "reasoning_format": "hidden",
                "max_completion_tokens": 4096,
            }
        )
    return Agent(
        name="Security Researcher",
        instructions=SECURITY_RESEARCHER_INSTRUCTIONS,
        model=model,
        model_settings=model_settings,
        mcp_servers=[semgrep_server],
    )


async def run_security_analysis(code: str) -> SecurityReport:
    """Execute the security analysis workflow."""
    with trace("Security Researcher"):
        async with create_semgrep_server() as semgrep:
            agent = create_security_agent(semgrep)
            try:
                with tempfile.NamedTemporaryFile(  # Creates a temporary file locally with teh code
                    mode="w", suffix=".py", delete=False
                ) as temp:
                    temp.write(code)
                    temp_path = temp.name
                try:
                    result = await Runner.run(
                        agent, input=get_analysis_prompt(code, temp_path)
                    )  # Sends code and path to the file
                    if not isinstance(result.final_output, str):
                        raise ValueError("Security agent returned a non-text report")
                    if not result.final_output.strip():
                        raise ValueError(
                            "Security agent returned an empty final answer; "
                            "check the model response and completion-token limit"
                        )
                    sorted_report = SecurityReport.model_validate_json(result.final_output)
                    sorted_report.issues.sort(key=lambda issue: issue.cvss_score, reverse=True)

                    return sorted_report
                finally:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
            except Exception as err:
                print(f"Unexpected {err=}, {type(err)=}")
                raise


def format_analysis_response(code: str, report: SecurityReport) -> SecurityReport:
    """Format the final analysis response."""
    enhanced_summary = enhance_summary(len(code), report.summary)
    return SecurityReport(summary=enhanced_summary, issues=report.issues)


@app.post("/api/analyze", response_model=SecurityReport)
async def analyze_code(request: AnalyzeRequest) -> SecurityReport:
    """
    Analyze Python code for security vulnerabilities using OpenAI Agents and Semgrep.

    This endpoint combines static analysis via Semgrep with AI-powered security analysis
    to provide comprehensive vulnerability detection and remediation guidance.
    """
    validate_request(request)
    check_api_keys()

    try:
        report = await run_security_analysis(request.code)
        return format_analysis_response(request.code, report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"message": "Cybersecurity Analyzer API"}


# Mount static files for frontend
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
