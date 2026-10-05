"""Offline-only wrapper for an existing case006 prediction; never calls a model.

--input must identify a saved prediction file. --output is a new directory.
Missing input exits INPUT_MISSING; a replay is not a new full dev suite.
"""
from scripts.audit_r2_saved_outputs import main


if __name__ == "__main__":
    raise SystemExit(main())
