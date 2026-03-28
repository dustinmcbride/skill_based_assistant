#!/usr/bin/env python3
"""CLI entrypoint for chat mode.

Usage:
    python run.py --user tim 
    python run.py --user tim --fresh
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure assistant/ is importable when invoked directly
sys.path.insert(0, str(Path(__file__).parent))

import agent
import memory
from user import load_user

logging.basicConfig(level=logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description="Personal Assistant (chat mode)")
    parser.add_argument("--user", required=True, help="Username")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start a new session (clears existing history)",
    )
    args = parser.parse_args()

    user = load_user(args.user)
    hist = [] if args.fresh else memory.load(user)

    print(f"Assistant ready. Hello, {user.display_name}! (Ctrl+C to exit)\n")

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except EOFError:
                break
            if not user_input:
                continue

            hist.append({"role": "user", "content": user_input})
            try:
                response_text, skill_name, _ = agent.run(hist, user=user, mode="chat")
            except Exception as e:
                print(f"[Error: {e}]")
                # Remove the user turn we just added so history stays consistent
                hist.pop()
                continue

            print(f"Assistant: {response_text}\n")
            memory.save(hist, user)

    except KeyboardInterrupt:
        print("\nGoodbye.")
        memory.save(hist, user)


if __name__ == "__main__":
    main()
