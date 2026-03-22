---
sidebar_position: 5
---

# API Reference

## Agent

### RatchetAgent

Main agent class for executing self-improving tasks.

```python
from ratchet.agent import RatchetAgent, AgentConfig

agent = RatchetAgent(config)
trace = agent.execute_task_sync(task)
```

### AgentConfig

Configuration options for the agent.

## Models

### MiniMaxClient

```python
from ratchet.models import MiniMaxClient

client = MiniMaxClient(api_key="key")
resp = client.complete(prompt, model="MiniMax-M2.7")
```

### QwenClient

OpenAI-compatible Qwen API client.
