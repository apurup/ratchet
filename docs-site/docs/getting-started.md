---
sidebar_position: 2
---

# Getting Started

## Installation

```bash
git clone https://github.com/apurup/ratchet.git
cd ratchet
pip install -e .
```

## Configuration

Set your API keys:

```bash
export MINIMAX_API_KEY="your-minimax-key"
export DASHSCOPE_API_KEY="your-qwen-key"  # optional, for Qwen
```

## Quick Start

```python
from ratchet.agent import RatchetAgent, AgentConfig, AgentMode

config = AgentConfig(
    provider="minimax",
    model="MiniMax-M2.7",
    mode=AgentMode.SELF_IMPROVE,
    max_iterations=3,
)

agent = RatchetAgent(config)

# Run a task
trace = agent.execute_task_sync("Write a prime checker function")
print(f"Success: {trace.success}")
print(f"Output: {trace.output}")
```

## Examples

See the `examples/` directory for:
- `code_repair.py` - Self-fixing code loop
- `benchmark.py` - Compare model performance
