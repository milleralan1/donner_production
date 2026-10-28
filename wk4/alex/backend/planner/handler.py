"""
Financial Planner Orchestrator Handler
"""

import json
import asyncio
import logging
from typing import Dict, Any

from agents import Agent, Runner, trace
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import database package
from src import Database

from templates import ORCHESTRATOR_INSTRUCTIONS
from agent import create_agent, handle_missing_instruments, load_portfolio_summary
from market import update_instrument_prices
from observability import observe

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize database
db = Database()

@retry(
    retry=retry_if_exception_type(RateLimitError),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    before_sleep=lambda retry_state: logger.info(f"Planner: Rate limit hit, retrying in {retry_state.next_action.sleep} seconds...")
)
async def run_orchestrator(job_id: str) -> None:
    """Run the orchestrator agent to coordinate portfolio analysis."""
    try:
        # Update job status to running
        db.jobs.update_status(job_id, 'running')
        
        # Handle missing instruments first (non-agent pre-processing)
        await asyncio.to_thread(handle_missing_instruments, job_id, db)

        # Update instrument prices after tagging
        logger.info("Planner: Updating instrument prices from market data")
        await asyncio.to_thread(update_instrument_prices, job_id, db)

        # Load portfolio summary (just statistics, not full data)
        portfolio_summary = await asyncio.to_thread(load_portfolio_summary, job_id, db)
        
        # Create agent with tools and context
        model, tools, task, context = create_agent(job_id, portfolio_summary, db)
        
        # Run the orchestrator
        with trace("Planner Orchestrator"):
            from agent import PlannerContext
            agent = Agent[PlannerContext](
                name="Financial Planner",
                instructions=ORCHESTRATOR_INSTRUCTIONS,
                model=model,
                tools=tools
            )
            
            result = await Runner.run(
                agent,
                input=task,
                context=context,
                max_turns=20
            )
            
            # Mark job as completed after all agents finish
            db.jobs.update_status(job_id, "completed")
            logger.info(f"Planner: Job {job_id} completed successfully")
            
    except Exception as e:
        logger.error(f"Planner: Error in orchestration: {e}", exc_info=True)
        db.jobs.update_status(job_id, 'failed', error_message=str(e))
        raise

def handle_event(event):
    """
    Entrypoint for GCP Cloud Run (Pub/Sub push or direct invocation).

    Accepted event shapes:
      Pub/Sub push (via gcp_agents/gcp_server.py /pubsub endpoint):
        {"job_id": "<uuid>"}

      Direct invocation (testing / planner tool calls):
        {"job_id": "<uuid>"}

    """
    # Wrap entire handler with observability context
    with observe():
        try:
            logger.info(f"Planner invoked with event: {json.dumps(event)[:500]}")

            job_id = event.get('job_id')
            if not job_id:
                raise ValueError("job_id is required")

            logger.info(f"Planner: Starting orchestration for job {job_id}")

            if not db.jobs.claim_for_processing(job_id):
                job = db.jobs.find_by_id(job_id)
                if not job:
                    logger.warning("Planner: Job %s no longer exists", job_id)
                    return {"success": True, "message": "Job no longer exists"}
                if job.get("status") in {"running", "completed"}:
                    if job["status"] == "running":
                        logger.info(
                            "Planner: Deferring duplicate delivery for running job %s",
                            job_id,
                        )
                        return {"retry": True, "message": "Job is already running"}
                    logger.info("Planner: Ignoring completed job %s", job_id)
                    return {"success": True, "message": "Job already completed"}
                raise RuntimeError(
                    f"Could not claim job {job_id} in state {job.get('status')}"
                )

            # Run the orchestrator
            asyncio.run(run_orchestrator(job_id))

            return {
                "success": True,
                "message": f"Analysis completed for job {job_id}",
            }

        except Exception as e:
            logger.error(f"Planner: Error handling request: {e}", exc_info=True)
            raise

# For local testing
if __name__ == "__main__":
    # Define a test user
    test_user_id = "test_user_planner_local"

    # Ensure the test user exists before creating a job
    from src.schemas import UserCreate, JobCreate
    
    user = db.users.find_by_clerk_id(test_user_id)
    if not user:
        print(f"Creating test user: {test_user_id}")
        user_create = UserCreate(clerk_user_id=test_user_id, display_name="Test Planner User")
        db.users.create(user_create.model_dump(), returning='clerk_user_id')

    # Create a test job
    print("Creating test job...")
    job_create = JobCreate(
        clerk_user_id=test_user_id,
        job_type='portfolio_analysis',
        request_payload={
            'analysis_type': 'comprehensive',
            'test': True
        }
    )
    
    job = db.jobs.create(job_create.model_dump())
    job_id = job
    
    print(f"Created test job: {job_id}")
    
    # Test the handler
    test_event = {
        'job_id': job_id
    }
    
    result = handle_event(test_event)
    print(json.dumps(result, indent=2))