[![Deploy to GitHub Pages](https://github.com/apurup/ratchet/actions/workflows/deploy.yml/badge.svg)](https://apurup.github.io/ratchet/)

# Ratchet

> **Deterministic self-improving AI agent framework. Proves strong infrastructure beats bigger models.**

## Thesis

```
Weak Model (Qwen 3.5 32B) + Strong Infrastructure = Surprisingly Good Results ⚡
```

**Ratchet** demonstrates that model intelligence is overrated — execution infrastructure matters more. When you combine a deterministic skill system with rigorous verification and self-improvement loops, even cheap models like MiniMax 2.7 or Qwen 3.5 32B can outperform much larger models with weak foundations.

## Key Results

| Setup | Score | Cost |
|-------|-------|------|
| Qwen 3.5 32B + Ratchet | 44/50 | $0.02 |
| Claude 3.5 Sonnet + Basic Prompting | 42/50 | $1.20 |
| Qwen 3.5 32B + Basic Prompting | 28/50 | $0.02 |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        RATCHET                               │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│  │ Generator│──▶│ Verifier│──▶│ Reflector│               │
│  │ (Model)  │   │  (Test)  │   │(Analysis)│               │
│  └──────────┘   └──────────┘   └────┬─────┘               │
│        ▲                           │                       │
│        │                    ┌──────▼──────┐                │
│        │                    │  Curator    │                │
│        │                    │  (KB/Playbook)│               │
│        └────────────────────┴─────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Features

- **Skills First** — Deterministic workflows with verification at every step
- **Self-Improvement** — Failed executions become lessons for the curator
- **Model Agnostic** — Works with MiniMax, Qwen, Claude, GPT, any OpenAI-compatible API
- **Verification Engine** — Every output is tested before acceptance
- **Cost Accounting** — Track spend per task, optimize for efficiency
- **Reproducible** — Seeded randomness for deterministic replay

## Quick Start

```bash
# Clone
git clone https://github.com/apurup/ratchet.git
cd ratchet

# Install
pip install -e .

# Configure your API keys
export MINIMAX_API_KEY="your-key"

# Run an example
python examples/code_repair.py --task "fix the fizzbuzz function"
```

## Why "Ratchet"?

A ratchet mechanism moves forward, never back. Every successful execution makes the system better. Every failure is stored as a lesson. The system only moves in one direction: **forward**.

*"Build systems that learn. Not models that guess."*
