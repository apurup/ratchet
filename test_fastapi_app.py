#!/usr/bin/env python3
"""
FastAPI App Creation Test - End to End
Tests Ratchet on: create a working FastAPI application, save it, verify it runs
"""

import os
import sys
import re
import tempfile
import subprocess
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratchet.agent import RatchetAgent, AgentConfig, AgentMode


TASK = """Create a FastAPI application in a single file called `app.py` with the following endpoints:

1. GET /hello - returns {"message": "Hello, World!"}
2. GET /users/{user_id} - returns {"user_id": <user_id>, "name": "Sample User"}
3. POST /items - accepts JSON body with "name" and "description" fields, returns the created item with an auto-generated "id" field starting from 1
4. GET /items - returns a list of all items

Use Python's FastAPI framework. Include proper type hints. Run the app with uvicorn on port 8765.

IMPORTANT: Save the file as `app.py` in the current directory."""

APP_FILE = "app.py"


def extract_code(raw_output: str) -> str:
    """Extract Python code from markdown code block in output."""
    match = re.search(r"```python\s*\n(.*?)```", raw_output, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try without language tag
    match = re.search(r"```\s*\n(.*?)```", raw_output, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_output.strip()


def check_syntax(code: str) -> tuple:
    """Check if code has valid Python syntax."""
    import py_compile
    try:
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w') as f:
            f.write(code)
            tmp = f.name
        py_compile.compile(tmp, doraise=True)
        os.unlink(tmp)
        return True, None
    except py_compile.PyCompileError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 60)
    print("FastAPI APP CREATION TEST")
    print("=" * 60)
    print(f"\nTask: Create a FastAPI app\n")

    config = AgentConfig(
        provider="minimax",
        model="MiniMax-M2.7",
        mode=AgentMode.SELF_IMPROVE,
        max_iterations=5,
    )

    agent = RatchetAgent(config)
    print("Agent initialized\n")

    print("Running agent (may take ~30s)...\n")
    trace = agent.execute_task_sync(TASK)

    print(f"\n{'='*60}")
    print("TRACE RESULTS")
    print(f"{'='*60}")
    print(f"Success: {trace.success}")
    print(f"Mode: {trace.mode}")
    print(f"Iterations: {len(trace.steps)}")
    print(f"Cost: ${trace.total_cost:.6f}")
    print(f"Duration: {trace.duration_ms/1000:.1f}s")

    # Extract code
    raw_output = trace.output or ""
    code = extract_code(raw_output)

    print(f"\n{'='*60}")
    print("EXTRACTED CODE")
    print(f"{'='*60}")
    print(code[:600])
    if len(code) > 600:
        print(f"... ({len(code)} chars total)")

    # Save to file
    print(f"\n{'='*60}")
    print("VERIFICATION")
    print(f"{'='*60}")

    if not code or len(code) < 50:
        print("⚠️  No code generated")
        return

    # Syntax check
    ok, err = check_syntax(code)
    if not ok:
        print(f"❌ Syntax error: {err}")
        return
    print("✅ Syntax OK")

    # Save file
    with open(APP_FILE, "w") as f:
        f.write(code)
    print(f"✅ Saved to {APP_FILE}")

    # Start server
    print(f"\nStarting uvicorn server on port 8765...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    time.sleep(3)

    try:
        # Test endpoints
        print("\nTesting endpoints...")

        # GET /hello
        r = requests.get("http://127.0.0.1:8765/hello", timeout=5)
        r.raise_for_status()
        print(f"  GET /hello → {r.json()}")

        # GET /users/42
        r = requests.get("http://127.0.0.1:8765/users/42", timeout=5)
        r.raise_for_status()
        print(f"  GET /users/42 → {r.json()}")

        # GET /items (empty)
        r = requests.get("http://127.0.0.1:8765/items", timeout=5)
        r.raise_for_status()
        print(f"  GET /items (empty) → {r.json()}")

        # POST /items
        r = requests.post("http://127.0.0.1:8765/items", json={"name": "Test Item", "description": "A test"}, timeout=5)
        r.raise_for_status()
        print(f"  POST /items → {r.json()}")

        # GET /items (with item)
        r = requests.get("http://127.0.0.1:8765/items", timeout=5)
        r.raise_for_status()
        print(f"  GET /items → {r.json()}")

        print("\n✅ All endpoints working!")

    except Exception as e:
        print(f"\n❌ Endpoint test failed: {e}")
        # Try to show server output
        try:
            stdout, stderr = proc.communicate(timeout=2)
            if stdout:
                print(f"STDOUT: {stdout.decode()[-500:]}")
            if stderr:
                print(f"STDERR: {stderr.decode()[-500:]}")
        except:
            pass

    finally:
        proc.terminate()
        proc.wait(timeout=5)
        print("\nServer stopped.")

    # Cleanup
    if os.path.exists(APP_FILE):
        os.unlink(APP_FILE)
        print(f"Cleaned up {APP_FILE}")

    print(f"\n{'='*60}")
    print("CURATOR")
    print(f"{'='*60}")
    from ratchet.curator import Curator
    curator = Curator()
    stats = curator.get_stats()
    print(f"Lessons: {stats.get('total_lessons', 0)}")
    print(f"Applications: {stats.get('total_applications', 0)}")
    if stats.get('total_lessons', 0) > 0:
        print(f"Avg success rate: {stats.get('average_success_rate', 0):.0%}")

    print("\n✅ Test complete!")


if __name__ == "__main__":
    main()
