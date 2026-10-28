"""
Financial Planner Orchestrator Agent - coordinates portfolio analysis across specialized agents.
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from agents import function_tool, RunContextWrapper

logger = logging.getLogger()


MOCK_AGENT_SERVICES = os.getenv("MOCK_AGENT_SERVICES", "false").lower() == "true"


@dataclass
class PlannerContext:
    """Context for planner agent tools."""
    job_id: str


async def invoke_agent_service(
    agent_name: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Invoke a private agent service or return a local test stub."""

    # For local testing with mocked agents
    if MOCK_AGENT_SERVICES:
        logger.info(f"[MOCK] Would invoke {agent_name} with payload: {json.dumps(payload)[:200]}")
        return {"success": True, "message": f"[Mock] {agent_name} completed", "mock": True}

    return await asyncio.to_thread(
        invoke_cloud_run_agent, agent_name, payload
    )


def invoke_cloud_run_agent(agent_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a private GCP agent service with a Google-signed ID token."""
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.id_token import fetch_id_token_credentials

    service_key = agent_name.upper()
    service_url = os.environ.get(f"{service_key}_SERVICE_URL", "").rstrip("/")
    if not service_url.startswith("https://"):
        raise ValueError(f"{service_key}_SERVICE_URL must be an HTTPS URL")
    audience = os.environ.get(f"{service_key}_SERVICE_AUDIENCE") or service_url
    credentials = fetch_id_token_credentials(audience, Request())
    response = AuthorizedSession(credentials).post(
        f"{service_url}/invoke",
        json=payload,
        timeout=600,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError(f"{agent_name} service returned a non-object response")
    return result


def handle_missing_instruments(job_id: str, db) -> None:
    """
    Check for and tag any instruments missing allocation data.
    This is done automatically before the agent runs.
    """
    logger.info("Planner: Checking for instruments missing allocation data...")

    # Get job and portfolio data
    job = db.jobs.find_by_id(job_id)
    if not job:
        logger.error(f"Job {job_id} not found")
        return

    user_id = job["clerk_user_id"]
    accounts = db.accounts.find_by_user(user_id)

    missing = []
    for account in accounts:
        positions = db.positions.find_by_account(account["id"])
        for position in positions:
            instrument = db.instruments.find_by_symbol(position["symbol"])
            if instrument:
                has_allocations = bool(
                    instrument.get("allocation_regions")
                    and instrument.get("allocation_sectors")
                    and instrument.get("allocation_asset_class")
                )
                if not has_allocations:
                    missing.append(
                        {"symbol": position["symbol"], "name": instrument.get("name", "")}
                    )
            else:
                missing.append({"symbol": position["symbol"], "name": ""})

    if missing:
        logger.info(
            f"Planner: Found {len(missing)} instruments needing classification: {[m['symbol'] for m in missing]}"
        )

        try:
            result = invoke_cloud_run_agent(
                "Tagger", {"instruments": missing}
            )
            if result.get("errors"):
                raise RuntimeError("Tagger reported instrument update errors")
            logger.info(
                "Planner: InstrumentTagger completed - Tagged %s instruments",
                len(result.get("updated", [])),
            )

        except Exception as e:
            logger.error(f"Planner: Error tagging instruments: {e}")
    else:
        logger.info("Planner: All instruments have allocation data")


def load_portfolio_summary(job_id: str, db) -> Dict[str, Any]:
    """Load basic portfolio summary statistics only."""
    try:
        job = db.jobs.find_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        user_id = job["clerk_user_id"]
        user = db.users.find_by_clerk_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        accounts = db.accounts.find_by_user(user_id)
        
        # Calculate simple summary statistics
        total_value = 0.0
        total_positions = 0
        total_cash = 0.0
        
        for account in accounts:
            total_cash += float(account.get("cash_balance", 0))
            positions = db.positions.find_by_account(account["id"])
            total_positions += len(positions)
            
            # Add position values
            for position in positions:
                instrument = db.instruments.find_by_symbol(position["symbol"])
                if instrument and instrument.get("current_price"):
                    price = float(instrument["current_price"])
                    quantity = float(position["quantity"])
                    total_value += price * quantity
        
        total_value += total_cash
        
        # Return only summary statistics
        return {
            "total_value": total_value,
            "num_accounts": len(accounts),
            "num_positions": total_positions,
            "years_until_retirement": user.get("years_until_retirement", 30),
            "target_retirement_income": float(user.get("target_retirement_income", 80000))
        }

    except Exception as e:
        logger.error(f"Error loading portfolio summary: {e}")
        raise


async def invoke_reporter_internal(job_id: str) -> str:
    """
    Invoke the Report Writer service to generate portfolio analysis narrative.

    Args:
        job_id: The job ID for the analysis

    Returns:
        Confirmation message
    """
    result = await invoke_agent_service("Reporter", {"job_id": job_id})

    if "error" in result:
        return f"Reporter agent failed: {result['error']}"

    return "Reporter agent completed successfully. Portfolio analysis narrative has been generated and saved."


async def invoke_charter_internal(job_id: str) -> str:
    """
    Invoke the Chart Maker service to create portfolio visualizations.

    Args:
        job_id: The job ID for the analysis

    Returns:
        Confirmation message
    """
    result = await invoke_agent_service("Charter", {"job_id": job_id})

    if "error" in result:
        return f"Charter agent failed: {result['error']}"

    return "Charter agent completed successfully. Portfolio visualizations have been created and saved."


async def invoke_retirement_internal(job_id: str) -> str:
    """
    Invoke the Retirement Specialist service for retirement projections.

    Args:
        job_id: The job ID for the analysis

    Returns:
        Confirmation message
    """
    result = await invoke_agent_service("Retirement", {"job_id": job_id})

    if "error" in result:
        return f"Retirement agent failed: {result['error']}"

    return "Retirement agent completed successfully. Retirement projections have been calculated and saved."



@function_tool
async def invoke_reporter(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Report Writer agent to generate portfolio analysis narrative."""
    return await invoke_reporter_internal(wrapper.context.job_id)

@function_tool
async def invoke_charter(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Chart Maker agent to create portfolio visualizations."""
    return await invoke_charter_internal(wrapper.context.job_id)

@function_tool
async def invoke_retirement(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Retirement Specialist agent for retirement projections."""
    return await invoke_retirement_internal(wrapper.context.job_id)


def create_agent(job_id: str, portfolio_summary: Dict[str, Any], db):
    """Create the orchestrator agent with tools."""
    
    # Create context for tools
    context = PlannerContext(job_id=job_id)

    from gcp_agents.huggingface_model import create_llm_model

    model = create_llm_model()

    tools = [
        invoke_reporter,
        invoke_charter,
        invoke_retirement,
    ]

    # Create minimal task context
    task = f"""Job {job_id} has {portfolio_summary['num_positions']} positions.
Retirement: {portfolio_summary['years_until_retirement']} years.

Call the appropriate agents."""

    return model, tools, task, context
