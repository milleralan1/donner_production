#!/usr/bin/env python3
"""
Simple test for Planner orchestrator
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Mock remote agent services for testing
os.environ['MOCK_AGENT_SERVICES'] = 'true'

from src import Database
from src.schemas import JobCreate

def setup_test_data():
    """Ensure test data exists and create a test job"""
    # Run reset_db with test data to ensure we have a test user and portfolio
    print("Ensuring test data exists...")
    result = subprocess.run(
        ["uv", "run", "reset_db.py", "--with-test-data", "--skip-drop"],
        cwd=Path(__file__).resolve().parents[1] / "database",
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Could not ensure Planner test data:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    
    db = Database()
    
    # The reset_db script creates test_user_001
    test_user_id = "test_user_001"
    
    # Check if user exists
    user = db.users.find_by_clerk_id(test_user_id)
    if not user:
        raise ValueError(f"Test user {test_user_id} not found. Please run: cd ../database && uv run reset_db.py --with-test-data")
    
    # Create test job
    job_create = JobCreate(
        clerk_user_id=test_user_id,
        job_type="portfolio_analysis",
        request_payload={"analysis_type": "comprehensive", "test": True}
    )
    job_id = db.jobs.create(job_create.model_dump())
    
    return job_id

def test_planner():
    """Test the planner orchestrator"""
    
    # Setup test data
    job_id = setup_test_data()
    
    test_event = {
        "job_id": str(job_id)
    }
    
    print("Testing Planner Orchestrator...")
    print(f"Job ID: {job_id}")
    print("=" * 60)
    
    from handler import handle_event
    
    result = handle_event(test_event)
    
    print(f"Result: {result}")
    
    if result.get('success'):
        body = result
        print(f"Success: {body.get('success', False)}")
        print(f"Message: {body.get('message', 'N/A')}")
    else:
        print(f"Error: {result.get('error', 'No result')}")
    
    print("=" * 60)

if __name__ == "__main__":
    test_planner()