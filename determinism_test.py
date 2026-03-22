#!/usr/bin/env python3
"""
Determinism Test - Same task x 3 runs
Tests whether Ratchet produces consistent output across runs
"""

import os
import sys
import json
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratchet.agent import RatchetAgent, AgentConfig, AgentMode

TASK = "Write a Python function that checks if a number is prime"

def run_single(agent, run_num):
    print(f"\n--- Run {run_num} ---")
    trace = agent.execute_task_sync(TASK)
    print(f"Success: {trace.success}")
    print(f"Output preview: {trace.output[:200] if trace.output else 'None'}...")
    print(f"Cost: ${trace.total_cost:.6f}")
    print(f"Duration: {trace.duration_ms:.0f}ms")
    
    # Hash the output for comparison
    if trace.output:
        output_hash = hashlib.md5(trace.output.encode()).hexdigest()
    else:
        output_hash = "None"
    
    return {
        "run": run_num,
        "success": trace.success,
        "output_hash": output_hash,
        "output_length": len(trace.output) if trace.output else 0,
        "cost": trace.total_cost,
        "duration_ms": trace.duration_ms,
        "output": trace.output,
    }


def main():
    print("="*60)
    print("DETERMINISM TEST - Same task x 3 runs")
    print("="*60)
    print(f"\nTask: {TASK}")
    
    config = AgentConfig(
        provider="minimax",
        model="MiniMax-M2.7",
        mode=AgentMode.BASIC,  # BASIC mode for clean comparison
        max_iterations=1,
    )
    
    agent = RatchetAgent(config)
    
    results = []
    for i in range(1, 4):
        result = run_single(agent, i)
        results.append(result)
    
    # Analysis
    print("\n" + "="*60)
    print("DETERMINISM ANALYSIS")
    print("="*60)
    
    hashes = [r["output_hash"] for r in results]
    all_same = len(set(hashes)) == 1
    
    print(f"\nOutput hashes: {hashes}")
    print(f"All outputs identical: {'✅ YES' if all_same else '❌ NO'}")
    
    # Check other consistency metrics
    costs = [r["cost"] for r in results]
    durations = [r["duration_ms"] for r in results]
    
    print(f"\nCost consistency:")
    print(f"  Costs: {[f'${c:.6f}' for c in costs]}")
    print(f"  All same: {'✅' if len(set(costs)) == 1 else '⚠️  varies (expected with API)'}")
    
    print(f"\nDuration consistency:")
    print(f"  Times: {[f'{d:.0f}ms' for d in durations]}")
    
    # Save detailed results
    with open("/workspace/ratchet/determinism_results.json", "w") as f:
        json.dump({
            "task": TASK,
            "results": results,
            "all_outputs_identical": all_same,
        }, f, indent=2)
    
    print(f"\n📁 Results saved to determinism_results.json")
    
    # Show outputs side by side
    print("\n" + "="*60)
    print("OUTPUTS SIDE BY SIDE")
    print("="*60)
    for i, r in enumerate(results, 1):
        print(f"\n--- Run {i} ---")
        print(r["output"][:500] if r["output"] else "None")


if __name__ == "__main__":
    main()
