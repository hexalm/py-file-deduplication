"""Entry point for the consolidation command."""

import sys
from pathlib import Path

from app.cli import run_consolidate

if __name__ == "__main__":
    force: bool = "--force" in sys.argv
    run_consolidate(project_root=Path(__file__).resolve().parent.parent, force=force)
