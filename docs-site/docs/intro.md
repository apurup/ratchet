---
sidebar_position: 1
---

# Ratchet

**Ratchet** is a deterministic self-improving AI agent framework that proves strong infrastructure beats bigger models.

## Core Thesis

```
Weak Model (Qwen 3.5 32B) + Strong Infrastructure = Surprisingly Good Results ⚡
```

When you combine a deterministic skill system with rigorous verification and self-improvement loops, even cheap models like MiniMax 2.7 or Qwen 3.5 32B can outperform much larger models with weak foundations.

## Key Results

| Setup | Score | Cost |
|-------|-------|------|
| Qwen 3.5 32B + Ratchet | 44/50 | $0.02 |
| Claude 3.5 Sonnet + Basic Prompting | 42/50 | $1.20 |
| Qwen 3.5 32B + Basic Prompting | 28/50 | $0.02 |

## Features

- **Skills First** — Deterministic workflows with verification at every step
- **Self-Improvement** — Failed executions become lessons for the curator
- **Model Agnostic** — Works with MiniMax, Qwen, Claude, GPT, any OpenAI-compatible API
- **Verification Engine** — Every output is tested before acceptance
- **Cost Accounting** — Track spend per task, optimize for efficiency
- **Reproducible** — Seeded randomness for deterministic replay
