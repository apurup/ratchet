#!/usr/bin/env python3
import time
import sys
sys.path.insert(0, '/workspace/ratchet')

from ratchet.models import get_client
from ratchet.agent import RatchetAgent, AgentConfig, AgentMode

TASK = "Write a Python function that checks if a number is prime. Only output code."

print("="*60)
print("RATCHET - MiniMax vs LM Studio Benchmark")
print("="*60)

# Test MiniMax
print("\n[MiniMax] Testing...")
client_minimax = get_client("minimax")
agent_minimax = RatchetAgent(AgentConfig(provider="minimax", model="MiniMax-M2.7", mode=AgentMode.BASIC, max_iterations=1))

start = time.time()
trace_minimax = agent_minimax.execute_task_sync(TASK)
time_minimax = time.time() - start

print(f"  Success: {trace_minimax.success}")
print(f"  Time: {time_minimax:.1f}s")
print(f"  Output: {trace_minimax.output[:150] if trace_minimax.output else 'None'}...")

# Test LM Studio
print("\n[LM Studio - qwen/qwen3.5-35b-a3b] Testing...")
agent_lm = RatchetAgent(AgentConfig(provider="lmstudio", model="qwen/qwen3.5-35b-a3b", api_base="http://localhost:1234/v1", mode=AgentMode.BASIC, max_iterations=1))

start = time.time()
trace_lm = agent_lm.execute_task_sync(TASK)
time_lm = time.time() - start

print(f"  Success: {trace_lm.success}")
print(f"  Time: {time_lm:.1f}s")
print(f"  Output: {trace_lm.output[:150] if trace_lm.output else 'None'}...")

# Summary
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"MiniMax:    {time_minimax:.1f}s | {trace_minimax.success}")
print(f"LM Studio:  {time_lm:.1f}s | {trace_lm.success}")

import json
with open("/workspace/ratchet/lm_studio_benchmark.json", "w") as f:
    json.dump({
        "task": TASK,
        "minimax": {"time_s": time_minimax, "success": trace_minimax.success, "output": trace_minimax.output},
        "lm_studio": {"time_s": time_lm, "success": trace_lm.success, "output": trace_lm.output},
    }, f, indent=2)
print("\nResults saved to lm_studio_benchmark.json")
