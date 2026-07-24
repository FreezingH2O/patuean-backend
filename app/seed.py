"""Seed two demo accounts so you can log in without signing up during a demo.

All phone-preview content (calls, family, settings, …) is static frontend data,
so nothing else needs seeding.

Run:  .venv/bin/python -m app.seed
Idempotent: does nothing if the seed users already exist.
"""

from app.db import SessionLocal, init_db
from app.models import User


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.get(User, "u-elder"):
            print("Seed users already present — skipping.")
            return
        db.add_all([
            User(
                id="u-elder",
                name="Somsak Rattanakosin",
                phone="+66 82 555 0147",
                email="somsak@example.com",
                role="elder",
                consent_recorded=False,
            ),
            User(
                id="u-guardian",
                name="Nok Rattanakosin",
                phone="+66 81 222 9981",
                email="nok@example.com",
                role="guardian",
                consent_recorded=False,
            ),
        ])
        db.commit()
        print("Seeded demo users: somsak@example.com (elder), nok@example.com (guardian).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
