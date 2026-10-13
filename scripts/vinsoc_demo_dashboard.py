"""Compatibility entry point for the unified mentor demo."""
import sys
from pathlib import Path

root = str(Path(__file__).resolve().parents[1])
if root not in sys.path:
    sys.path.insert(0, root)

from scripts.vinsoc_demo_app import main  # noqa: E402

if __name__ == '__main__':
    main()
