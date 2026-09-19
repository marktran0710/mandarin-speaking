"""Delete every student flagged is_test_account, and everything they own.

Run this once, right before a real launch, to take the roster from "mixed
with QA/synthetic fixtures" to 100% real students. It is also what
``seed_test_accounts.py --clean`` calls to remove its own prior run.

Refuses to touch a non-localhost database unless --force is given, same
convention as the other seed/dev scripts in this directory.

Examples::

    python -m scripts.purge_test_accounts               # dry run: lists who would go
    python -m scripts.purge_test_accounts --yes          # actually deletes them
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import connect_db, delete_student_cascade  # noqa: E402


def _looks_local(url: str) -> bool:
    return "@127.0.0.1" in url or "@localhost" in url or "@::1" in url


def purge(url: str, *, apply: bool) -> list[tuple[str, str]]:
    with connect_db() as db:
        candidates = [
            (row["id"], row["name"])
            for row in db.execute("SELECT id, name FROM students WHERE is_test_account ORDER BY name").fetchall()
        ]
        if apply:
            for student_id, _name in candidates:
                delete_student_cascade(db, student_id)
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--yes", action="store_true", help="Actually delete. Without this, only lists who would be removed.")
    parser.add_argument("--force", action="store_true", help="Allow a non-localhost database URL.")
    args = parser.parse_args()

    url = args.database_url
    if not url:
        raise SystemExit("No database URL. Pass --database-url or set DATABASE_URL.")
    if not _looks_local(url) and not args.force:
        raise SystemExit("Refusing to touch a non-localhost database without --force.")

    removed = purge(url, apply=args.yes)
    if not removed:
        print("No test accounts found. Roster is already 100% real students.")
        return
    verb = "Deleted" if args.yes else "Would delete"
    print(f"{verb} {len(removed)} test account(s):")
    for student_id, name in removed:
        print(f"  {name} ({student_id})")
    if not args.yes:
        print("\nRe-run with --yes to actually delete them.")


if __name__ == "__main__":
    main()
