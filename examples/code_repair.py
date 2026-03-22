"""
Code Repair Example - Demonstrates Ratchet fixing broken code
"""

from ratchet import Agent, Generator, Verifier, Curator, Skill, Step, StepType, VerificationRule, VerificationType


def main():
    print("=" * 60)
    print("Ratchet Code Repair Example")
    print("=" * 60)

    # Initialize components
    agent = Agent(
        generator=Generator(provider="minimax"),
        verifier=Verifier(),
        curator=Curator(),
    )

    # Define a code repair skill
    repair_skill = Skill(
        name="code_repair",
        description="Repair broken Python code using error analysis",
        trigger_pattern="fix.*bug|repair.*code",
        trigger_type="pattern",
        steps=[
            Step(
                id="analyze",
                type=StepType.PROMPT,
                description="Analyze the broken code and identify the bug",
                prompt="""Analyze this Python code and identify the bug.
                    
Broken code:
```python
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)

result = calculate_average([1, 2, 3, "four", 5])
print(f"Average: {result}")
```

Identify:
1. What is the bug?
2. What error does it cause?
3. How to fix it?""",
            ),
            Step(
                id="fix",
                type=StepType.PROMPT,
                description="Generate the fixed code",
                prompt="""Based on the analysis, generate the corrected Python code.
Only output the fixed code in a ```python``` block.""",
                verification=VerificationRule(
                    type=VerificationType.OUTPUT,
                    must_contain=["def calculate_average"],
                    must_not_contain=["traceback", "TypeError"],
                ),
            ),
            Step(
                id="verify",
                type=StepType.EXEC,
                description="Run the fixed code to verify it works",
                command="python3 -c \"\ndef calculate_average(numbers):\n    total = sum(numbers)\n    return total / len(numbers)\n\nresult = calculate_average([1, 2, 3, 4, 5])\nprint(f'Average: {result}')\n\"",
                verification=VerificationRule(
                    type=VerificationType.EXIT_CODE,
                    expected_code=0,
                    description="Code should execute without errors",
                ),
            ),
        ],
        self_improve=True,
        learn_from_failures=True,
    )

    # Run the skill
    print("\nRunning code repair skill...\n")
    result = agent.run(
        repair_skill,
        context={"task": "fix type error in calculate_average"},
    )

    # Report results
    print(f"\n{'SUCCESS' if result.passed else 'FAILED'}")
    print(f"Total cost: ${result.total_cost:.4f}")
    print(f"Total time: {result.total_time_ms:.0f}ms")
    print(f"Steps executed: {len(result.steps)}")

    for step in result.steps:
        status = "PASS" if step.passed else "FAIL"
        print(f"  [{status}] {step.step_id}: {step.error or 'OK'}")


if __name__ == "__main__":
    main()
