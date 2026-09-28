"""Prepare SIM accounts for a local BKT runtime test.

Preview by default; use ``--apply`` to set deterministic dev passwords. The
script only touches SIM001-SIM040 and never creates or deletes accounts.
"""

from __future__ import annotations

import argparse

import security.auth as auth
from db import connect_db


SIM_IDS = tuple(f"SIM{index:03d}" for index in range(1, 41))
PASSWORD_SUFFIX = "-test-2026!"


def password_for(student_id: str) -> str:
    return f"{student_id}{PASSWORD_SUFFIX}"


def prepare(*, apply: bool) -> list[dict[str, str]]:
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT id, name, is_test_account, status, password_reset_required
            FROM students
            WHERE id = ANY(%s)
            ORDER BY id
            FOR UPDATE
            """,
            (list(SIM_IDS),),
        ).fetchall()
        if {row["id"] for row in rows} != set(SIM_IDS):
            raise ValueError("Expected all 40 SIM accounts to exist.")
        if any(not row["is_test_account"] for row in rows):
            raise ValueError("Refusing to modify a non-test account.")
        if any(row["status"] != "active" for row in rows):
            raise ValueError("All SIM accounts must be active before login testing.")

        credentials = [{"studentId": row["id"], "name": row["name"], "password": password_for(row["id"])} for row in rows]
        if apply:
            for credential, row in zip(credentials, rows):
                db.execute(
                    """
                    UPDATE students
                    SET password = %s,
                        password_reset_required = FALSE,
                        password_version = password_version + 1
                    WHERE id = %s AND is_test_account = TRUE
                    """,
                    (auth.hash_password(credential["password"]), row["id"]),
                )
        return credentials


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write passwords; without this flag only preview.")
    args = parser.parse_args()
    credentials = prepare(apply=args.apply)
    print("Applied" if args.apply else "Preview only")
    for credential in credentials:
        print(f"{credential['studentId']}\t{credential['password']}\t{credential['name']}")


if __name__ == "__main__":
    main()
