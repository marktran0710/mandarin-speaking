"""Seed the standard local teaching data and demo accounts in one command.

This is intentionally a development-only entry point. It is idempotent: lesson
seeds keep existing authored content unless ``--overwrite`` is supplied, and
demo-account seeding never changes an existing account password.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


LESSON_MODULES = (
    "scripts.seed_grammar_lesson",
    "scripts.seed_listen_retell_lesson",
    "scripts.seed_vv_kan_lesson",
)


def main() -> None:
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise SystemExit("Development seed is disabled in production.")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing authored lessons before continuing.",
    )
    args = parser.parse_args()

    for module in (*LESSON_MODULES, "scripts.seed_demo_accounts"):
        command = [sys.executable, "-m", module]
        if args.overwrite and module in LESSON_MODULES:
            command.append("--overwrite")
        print(f"Running {module}...", flush=True)
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            raise SystemExit(f"Seed step failed: {module}")

    print("Development seed complete.")


if __name__ == "__main__":
    main()
