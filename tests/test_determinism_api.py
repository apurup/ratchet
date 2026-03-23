#!/usr/bin/env python3
import os
import sys
import json
import time
import hashlib

sys.path.insert(0, '/workspace/ratchet')

from ratchet.models import MiniMaxClient
from ratchet.agent import RatchetAgent, AgentConfig, AgentMode

TASK = "Write a Python function that checks if a number is prime"

def main():
    print("="*60)
    print("DETERMINISM TEST - Same task x 3 runs")
    print("="*60)
    print(f"\nTask: {TASK}\n")
    
    # Use the fixed MiniMax client directly
    client = MiniMaxClient()
    
    results = []
    for run in range(1, 4):
        print(f"--- Run {run}/3 ---")
        print("Calling MiniMax API...")
        
        resp = client.complete(
            f"{TASK}. Only output the Python code, no explanations.",
            model="MiniMax-M2.7",
            max_tokens=1000
        )
        
        print(f"  Content: {resp.content[:100]}...")
        print(f"  Cost: ${resp.cost:.6f}")
        print(f"  Thinking: {resp.thinking[:50] if resp.thinking else 'None'}...")
        
        results.append({
            "run": run,
            "content": resp.content,
            "content_hash": hashlib.md5(resp.content.encode()).hexdigest() if resp.content else "EMPTY",
            "cost": resp.cost,
            "thinking_preview": resp.thinking[:100] if resp.thinking else None,
        })
        
        print(f"  Hash: {results[-1]['content_hash']}")
        
        if run < 3:
            print("  Waiting 3s before next call (rate limit)...")
            time.sleep(3)
        
        print()
    
    # Analysis
    print("="*60)
    print("DETERMINISM ANALYSIS")
    print("="*60)
    
    hashes = [r["content_hash"] for r in results]
    all_same = len(set(hashes)) == 1
    
    print(f"\nOutput hashes: {hashes}")
    print(f"All outputs identical: {'✅ YES' if all_same else '❌ NO - some variation'}")
    
    # Show first few chars of each
    print("\nFirst 80 chars of each output:")
    for r in results:
        print(f"  Run {r['run']}: {r['content'][:80]}...")
    
    # Save
    with open("/workspace/ratchet/determinism_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n✅ Results saved to determinism_results.json")

if __name__ == "__main__":
    main()