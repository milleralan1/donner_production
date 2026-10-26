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
    
    if result.get('success', True):
        body = result
        print(f"Tagged: {body.get('tagged', 0)} instruments")
        print(f"Updated: {body.get('updated', [])}")
        if body.get('classifications'):
            for c in body['classifications']:
                print(f"  {c['symbol']}: {c['type']}")
    else:
        print(f"Error: {result.get('error', 'No result')}")
    
    print("=" * 60)

if __name__ == "__main__":
    test_tagger()