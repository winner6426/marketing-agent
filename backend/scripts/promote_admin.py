"""Grant the admin role to an existing account, since the API can never create the first admin."""

import argparse
import sys

from dotenv import load_dotenv

from src.models import db
from src.utils import current_timestamp


def promote(email: str) -> bool:
    with db.get_session() as session:
        profile = session.query(db.UserProfile).filter(db.UserProfile.email == email).one_or_none()
        if profile is None:
            return False
        profile.role = db.UserRole.ADMIN
        profile.updated_at = current_timestamp()
        session.commit()
        return True


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email of an account that has already registered")
    email = parser.parse_args().email
    if not promote(email):
        print(f"No profile found for {email}; register the account first.", file=sys.stderr)
        return 1
    print(f"{email} is now an admin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
