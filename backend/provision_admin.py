"""Interactively provision a SupportAI admin or support staff account."""

from getpass import getpass
import re

from backend.auth import hash_password, normalize_email
from backend.database import DuplicateStaffEmailError, create_staff_account


def main():
    print("Provision a SupportAI staff account")
    name = input("Name: ").strip()
    email = normalize_email(input("Email: "))
    role = input("Role (admin/support) [admin]: ").strip().lower() or "admin"
    if role not in {"admin", "support"}:
        raise SystemExit("Role must be admin or support.")
    if (
        not name
        or len(name) > 100
        or len(email) > 150
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        raise SystemExit("Enter a valid name and email.")

    password = getpass("Password (12-128 characters): ")
    confirmation = getpass("Confirm password: ")
    if not 12 <= len(password) <= 128:
        raise SystemExit("Password must contain between 12 and 128 characters.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    try:
        staff_id = create_staff_account(name, email, hash_password(password), role)
    except DuplicateStaffEmailError:
        raise SystemExit("A staff account already exists for that email.") from None

    print(f"Provisioned {role} account #{staff_id} for {email}.")


if __name__ == "__main__":
    main()
