#!/usr/bin/env python3
"""
Simple test for Tagger agent
"""

import asyncio
import json
from dotenv import load_dotenv

load_dotenv(override=True)

from handler import handle_event

def test_tagger():
    """Test the tagger agent with unknown instruments"""
    
    test_event = {
        "instruments": [
            {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF"}
        ]
    }
    
    print("Testing Tagger Agent...")
    print("=" * 60)
    
    result = handle_event(test_event)
    
    print(f"Result: {result}")
    
    if result.get("success") is False:
        print(f"Error: {result.get('error', 'No result')}")
        raise SystemExit(1)

    body = result
    tagged = body.get("tagged", 0)
    print(f"Tagged: {tagged} instruments")
    print(f"Updated: {body.get('updated', [])}")
    if body.get("classifications"):
        for classification in body["classifications"]:
            print(f"  {classification['symbol']}: {classification['type']}")

    expected = len(test_event["instruments"])
    if body.get("errors") or tagged != expected:
        print(
            f"Error: expected {expected} classifications, got {tagged}; "
            f"details: {body.get('errors', [])}"
        )
        raise SystemExit(1)
    
    print("=" * 60)

if __name__ == "__main__":
    test_tagger()