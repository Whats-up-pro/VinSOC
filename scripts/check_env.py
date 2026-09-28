#!/usr/bin/env python3
"""Check local .env configuration for VinSOC.

This script reads the local .env file at runtime to verify configuration.
It does NOT make API calls or validate keys with OpenAI.

Usage:
    python -m scripts.check_env --check
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    """Load environment variables from .env file without modifying the file."""
    env_vars = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, _, value = line.partition("=")
                        env_vars[key.strip()] = value.strip()
    return env_vars


def check_env() -> int:
    """Check .env configuration and report status."""
    env_path = Path(".env")
    env_vars = load_env(env_path)

    api_key = env_vars.get("OPENAI_API_KEY", "")
    base_url = env_vars.get("OPENAI_BASE_URL", "")

    # Check OPENAI_API_KEY
    if api_key:
        print("OPENAI_API_KEY: present")
    else:
        print("OPENAI_API_KEY: missing")
        print("  -> Set OPENAI_API_KEY in .env to use local evaluation")

    # Block OPENAI_BASE_URL
    if base_url:
        print("OPENAI_BASE_URL: configured")
        print("  -> BLOCKED: R2 pilot requires standard OpenAI endpoint")
        print("  -> Remove OPENAI_BASE_URL from .env")
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local .env configuration")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run configuration check",
    )
    args = parser.parse_args()

    if args.check:
        return check_env()
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
