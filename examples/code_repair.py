"""
Example: Code Repair Loop with Self-Improvement
Run: python examples/code_repair.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratchet.agent import RatchetAgent, AgentConfig, AgentMode
from ratchet.skill import Skill, Step, StepType


def main():
    print("=" * 60)
    print("RATCHET - Code Repair Example")
    print("=" * 60)

    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("ERROR: Set MINIMAX_API_KEY environment variable")
        sys.exit(1)

    config = AgentConfig(
        provider="minimax",
        model="MiniMax-M2.7",
        mode=AgentMode.SELF_IMPROVE,
        max_iterations=3,
    )
    agent = RatchetAgent(config)

    skill = Skill(
        name="code_repair",
        description="Fix broken Python code",
        steps=[
            Step(id="generate", type=StepType.PROMPT, prompt="Write a Python function that implements fizzbuzz: returns 'FizzBuzz' for multiples of 15, 'Fizz' for 3, 'Buzz' for 5. Return only code."),
        ],
        self_improve=True,
    )

    task = "implement fizzbuzz correctly"
    print(f"\n🔧 Task: {task}")
    print("\n🚀 Running self-improving code repair...")

    trace = agent.execute_task_sync(task, skill=skill)

    print(f"\n📊 Results:")
    print(f"   Success: {trace.success}")
    print(f"   Duration: {trace.duration_ms:.0f}ms")
    print(f"   Cost: ${trace.total_cost:.4f}")

    if trace.output:
        print(f"\n📝 Output:\n{trace.output[:500]}")

    stats = agent.get_stats()
    print(f"\n📈 Stats: {stats}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
