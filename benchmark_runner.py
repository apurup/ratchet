#!/usr/bin/env python3
"""
Ratchet Benchmark Runner - Tests the core thesis:
Strong Infrastructure > Bigger Models
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratchet.agent import RatchetAgent, AgentConfig, AgentMode
from ratchet.models import get_client


TASKS = [
    "Write a function that checks if a string is a palindrome",
    "Implement binary search in Python",
    "Create a function to merge two sorted arrays",
    "Write a function to find the factorial of a number",
    "Implement a stack with push and pop operations",
]


def run_benchmark(provider, model, mode, tasks):
    print(f"\n{'='*60}")
    print(f"Benchmark: {model} + {mode}")
    print(f"{'='*60}")
    
    config = AgentConfig(
        provider=provider,
        model=model,
        mode=mode,
        max_iterations=2,
    )
    
    try:
        agent = RatchetAgent(config)
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
        return []
    
    results = []
    for i, task in enumerate(tasks, 1):
        print(f"\nTask {i}/5: {task[:50]}...")
        try:
            trace = agent.execute_task_sync(task)
            results.append({
                "task": task,
                "success": trace.success,
                "duration_ms": trace.duration_ms,
                "cost": trace.total_cost,
                "iterations": len(trace.steps),
                "error": trace.error,
            })
            status = "✅" if trace.success else "❌"
            print(f"  {status} success={trace.success} cost=${trace.total_cost:.4f} time={trace.duration_ms:.0f}ms")
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            results.append({"task": task, "success": False, "error": str(e)})
    
    return results


def main():
    print("="*60)
    print("RATCHET FRAMEWORK BENCHMARK")
    print("Core Thesis: Strong Infrastructure > Bigger Models")
    print("="*60)
    
    # Check API keys
    has_minimax = bool(os.environ.get("MINIMAX_API_KEY"))
    
    if not has_minimax:
        print("\n⚠️  MINIMAX_API_KEY not set - cannot run benchmarks")
        print("   Set: export MINIMAX_API_KEY=your-key")
        return
    
    all_results = {}
    
    # Run MiniMax BASIC
    if has_minimax:
        results = run_benchmark("minimax", "MiniMax-M2.7", AgentMode.BASIC, TASKS)
        all_results["minimax_basic"] = results
    
    # Run MiniMax SELF_IMPROVE (skill mode)
    if has_minimax:
        results = run_benchmark("minimax", "MiniMax-M2.7", AgentMode.SELF_IMPROVE, TASKS)
        all_results["minimax_skill"] = results
    
    # Summary
    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)
    
    for config_name, results in all_results.items():
        if not results:
            continue
        successes = sum(1 for r in results if r.get("success", False))
        total = len(results)
        avg_cost = sum(r.get("cost", 0) for r in results) / total
        avg_time = sum(r.get("duration_ms", 0) for r in results) / total / 1000
        rate = successes / total * 100 if total > 0 else 0
        print(f"\n{config_name}:")
        print(f"  Success Rate: {rate:.0f}% ({successes}/{total})")
        print(f"  Avg Cost: ${avg_cost:.4f}")
        print(f"  Avg Time: {avg_time:.2f}s")
    
    # Save results
    with open("/workspace/ratchet/benchmark_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n📁 Results saved to benchmark_results.json")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
