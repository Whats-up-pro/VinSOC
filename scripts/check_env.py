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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

KeySource = Literal[
    "dotenv",
    "process_environment",
    "both_same",
    "conflicting_key_sources",
    "missing",
]


@dataclass(frozen=True)
class OpenAIKeyResolution:
    """Resolved key plus a non-sensitive description of its source."""

    key: str | None
    source: KeySource


def resolve_openai_key(
    process_env: Mapping[str, str], dotenv_env: Mapping[str, str]
) -> OpenAIKeyResolution:
    """Resolve OPENAI_API_KEY without exposing any property of its value."""
    process_value = process_env.get("OPENAI_API_KEY") or None
    dotenv_value = dotenv_env.get("OPENAI_API_KEY") or None
    if process_value and dotenv_value:
        if process_value == dotenv_value:
            return OpenAIKeyResolution(process_value, "both_same")
        return OpenAIKeyResolution(None, "conflicting_key_sources")
    if process_value:
        return OpenAIKeyResolution(process_value, "process_environment")
    if dotenv_value:
        return OpenAIKeyResolution(dotenv_value, "dotenv")
    return OpenAIKeyResolution(None, "missing")


def load_env(path: Path) -> dict[str, str]:
    """Load environment variables from .env file without modifying the file."""
    if not path.exists():
        return {}
    return {
        key: value
        for key, value in dotenv_values(path, interpolate=False).items()
        if isinstance(value, str)
    }


def check_env(
    *,
    process_env: Mapping[str, str] | None = None,
    dotenv_env: Mapping[str, str] | None = None,
) -> int:
    """Check .env configuration and report status."""
    process_values = os.environ if process_env is None else process_env
    dotenv_values_map = load_env(Path(".env")) if dotenv_env is None else dotenv_env
    resolution = resolve_openai_key(process_values, dotenv_values_map)
    print(f"OPENAI_API_KEY source: {resolution.source}")
    if resolution.source == "conflicting_key_sources":
        return 1

    if resolution.key:
        print("OPENAI_API_KEY: present")
    else:
        print("OPENAI_API_KEY: missing")
        print("  -> Set OPENAI_API_KEY in .env to use local evaluation")

    if process_values.get("OPENAI_BASE_URL") or dotenv_values_map.get("OPENAI_BASE_URL"):
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
