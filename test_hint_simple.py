#!/usr/bin/env python3
import sys

sys.path.insert(0, ".")

print("Test started", flush=True)

try:
    print("Step 1: Loading config...", flush=True)
    from config import load_settings

    settings = load_settings()

    if not settings.openai_api_key:
        print("ERROR: No OpenAI key", flush=True)
        sys.exit(1)

    print(f"Step 2: Key found: {settings.openai_api_key[:15]}...", flush=True)

    print("Step 3: Importing generator...", flush=True)
    from tasks.ai_hints_generator import generate_task_hint

    print("Step 4: Generating hint...", flush=True)
    hint = generate_task_hint("Кофейня", "food", "cafe")

    if hint:
        print(f"SUCCESS: {hint}", flush=True)
    else:
        print("FAILED: No hint generated", flush=True)
        sys.exit(1)

except Exception as e:
    print(f"ERROR: {e}", flush=True)
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("Test completed", flush=True)
