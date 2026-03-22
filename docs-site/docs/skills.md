---
sidebar_position: 4
---

# Skills

Skills are deterministic workflows that define how tasks are executed.

## Skill Schema

```python
from ratchet.skill import Skill, Step, StepType

skill = Skill(
    name="code_repair",
    description="Fix broken Python code",
    steps=[
        Step(id="generate", type=StepType.PROMPT, prompt="..."),
        Step(id="verify", type=StepType.VERIFY, verification=...),
    ],
    self_improve=True,
)
```

## Step Types

- **PROMPT** - Send to model
- **EXEC** - Execute command  
- **VERIFY** - Run verification
- **BRANCH** - Conditional branching
