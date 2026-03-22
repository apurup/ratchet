"""
Example: Benchmark - Compare models and infrastructure
Run: python examples/benchmark.py
"""

import os
import sys
import json
from dataclasses import dataclass
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratchet.agent import RatchetAgent, AgentConfig, AgentMode


@dataclass
class BenchmarkResult:
    model: str
    infrastructure: str
    task: str
    success: bool
    duration_ms: float
    cost: float


def run_benchmark(provider: str, model: str, infrastructure: str, tasks: List[str]) -> List[BenchmarkResult]:
    config = AgentConfig(
        provider=provider,
        model=model,
        mode=AgentMode.SELF_IMPROVE if infrastructure == "skill" else AgentMode.BASIC,
        max_iterations=2,
    )
    agent = RatchetAgent(config)
    results = []
    for task in tasks:
        trace = agent.execute_task_sync(task)
        results.append(BenchmarkResult(
            model=model, infrastructure=infrastructure, task=task,
            success=trace.success, duration_ms=trace.duration_ms, cost=trace.total_cost,
        ))
    return results


def main():
    print("=" * 60)
    print("RATCHET - Benchmark")
    print("=" * 60)

    has_minimax = bool(os.environ.get("MINIMAX_API_KEY"))
    if not has_minimax:
        print("WARNING: MINIMAX_API_KEY not set")

    tasks = [
        "Write a palindrome checker function",
        "Implement binary search",
        "Merge two sorted arrays",
    ]

    configs = [("minimax", "MiniMax-M2.7", "basic"), ("minimax", "MiniMax-M2.7", "skill")]
    all_results = []

    for provider, model, infra in configs:
        print(f"⏳ Testing: {model} + {infra}...")
        results = run_benchmark(provider, model, infra, tasks)
        all_results.extend(results)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    from collections import defaultdict
    by_config = defaultdict(list)
    for r in all_results:
        by_config[f"{r.model} + {r.infrastructure}"].append(r)

    for config, results in sorted(by_config.items()):
        rate = sum(1 for r in results if r.success) / len(results) * 100
        avg_cost = sum(r.cost for r in results) / len(results)
        print(f"{config}: {rate:.0f}% success, ${avg_cost:.4f} avg cost")

    with open("benchmark_results.json", "w") as f:
        json.dump([r.__dict__ for r in all_results], f, indent=2)
    print("\n📁 Results saved to benchmark_results.json")


if __name__ == "__main__":
    main()
