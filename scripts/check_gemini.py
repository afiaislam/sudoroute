#!/usr/bin/env python3
"""Check that your Gemini key works with SudoRoute.

    python scripts/check_gemini.py

Reads GEMINI_API_KEY from the environment or the project's .env file, finds a working
model, and runs one intent classification and one reply rewrite.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sudoroute import config  # noqa: E402  (loads .env)
from sudoroute.agent import llm  # noqa: E402

if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
    sys.exit("No key found. Create a file named .env in the project folder containing:\n"
             "  GEMINI_API_KEY=your-key-here")
config.LLM_PROVIDER = config.LLM_PROVIDER or "gemini"
print(f"Provider: {config.LLM_PROVIDER} · trying models: {', '.join(dict.fromkeys(config.GEMINI_MODELS))}")

intent = llm.classify("can you sort out my semester fees for me?")
if intent is None:
    sys.exit(f"✗ Gemini call failed: {llm.status()['last_error']}\n"
             "  Check the key at https://aistudio.google.com/apikey, or set TS_LLM_MODEL in .env to a model "
             "your key can use.")
print(f"✓ Model in use: {llm.status()['model']}")
print(f"✓ Intent: {intent['intent']}")
reply = llm.compose("pay my fees", "I've prepared a payment of 18,500.00 MYR via EduPay today. "
                    "Estimated cost 541,330 BDT. Enter the one-time code to confirm.", "pay_tuition")
print("✓ Reply rewrite:" if reply else "! Reply rewrite fell back to the template (number check):")
print("  " + (reply or llm.status()["last_error"] or "").replace("\n", "\n  "))
print("\nGemini is ready. Start the app with: python run.py")
