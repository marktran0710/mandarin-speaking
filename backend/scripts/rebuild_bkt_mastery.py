"""Replay normalized vocabulary responses into the BKT cache.

Usage from backend/: ``python scripts/rebuild_bkt_mastery.py [student_id]``.
The migration backfills mappable historical JSONB responses; this command is
for recalibration, audits, and explicit cache rebuilds after parameter changes.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.bkt_mastery import rebuild_all_vocabulary_mastery, rebuild_student_vocabulary_mastery  # noqa: E402
from database import connect_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild student vocabulary BKT mastery from raw responses")
    parser.add_argument("student_id", nargs="?", help="Only rebuild one student; omit to rebuild everyone")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with connect_db() as db:
        if args.student_id:
            rebuild_student_vocabulary_mastery(db, args.student_id)
            logging.info("Rebuilt vocabulary mastery for student %s", args.student_id)
        else:
            rebuild_all_vocabulary_mastery(db)
            logging.info("Rebuilt vocabulary mastery for all students")


if __name__ == "__main__":
    main()
