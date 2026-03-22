"""
Benchmark Example - Measure Ratchet agent performance
"""

import time
from ratchet import Agent, Generator, Verifier, Curator, Skill, Step, StepType, VerificationRule, VerificationType


def benchmark_single_step():
    """Benchmark a single step execution."""
    generator = Generator(provider="minimax")
    verifier = Verifier()

    prompt = "Write a Python function to reverse a string."

    start = time.time()
    result = generator.generate(prompt)
    elapsed = (time.time() - start) * 1000

    print(f"  Latency: {result.latency_ms:.0f}ms")
    print(f"  Cost: ${result.cost:.6f}")
    print(f"  Model: {result.model}")
    print(f"  Response length: {len(result.content)} chars")
    print(f"  Wall time: {elapsed:.0f}ms")


def benchmark_verification():
    """Benchmark verification step."""
    verifier = Verifier()

    rule = VerificationRule(
        type=VerificationType.OUTPUT,
        must_contain=["def", "return"],
        must_not_contain=["error", "fail"],
    )

    code_output = """
def reverse_string(s):
    return s[::-1]
"""

    start = time.time()
    result = verifier.verify(rule, code_output)
    elapsed = (time.time() - start) * 1000

    print(f"  Verification: {'PASS' if result.passed else 'FAIL'}")
    print(f"  Time: {elapsed:.1f}ms")


def benchmark_full_skill():
    """Benchmark a full skill execution."""
    agent = Agent(
        generator=Generator(provider="minimax"),
        verifier=Verifier(),
        curator=Curator(),
    )

    echo_skill = Skill(
        name="echo_test",
        description="Simple echo test",
        steps=[
            Step(
                id="echo",
                type=StepType.PROMPT,
                prompt="Return the word 'benchmark' exactly.",
                verification=VerificationRule(
                    type=VerificationType.OUTPUT,
                    must_contain=["benchmark"],
                ),
            ),
        ],
    )

    start = time.time()
    result = agent.run(echo_skill)
    elapsed = (time.time() - start) * 1000

    print(f"  Result: {'PASS' if result.passed else 'FAIL'}")
    print(f"  Total cost: ${result.total_cost:.6f}")
    print(f"  Total time: {result.total_time_ms:.0f}ms")
    print(f"  Wall time: {elapsed:.0f}ms")


def main():
    print("=" * 60)
    print("Ratchet Benchmark Suite")
    print("=" * 60)

    print("\n[1] Single Step Generation Benchmark")
    print("-" * 40)
    benchmark_single_step()

    print("\n[2] Verification Benchmark")
    print("-" * 40)
    benchmark_verification()

    print("\n[3] Full Skill Execution Benchmark")
    print("-" * 40)
    benchmark_full_skill()

    print("\n" + "=" * 60)
    print("Benchmark complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
