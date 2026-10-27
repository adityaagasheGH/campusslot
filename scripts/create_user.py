"""Create one CampusSlot account. The password is typed hidden and only its salted
PBKDF2 hash is stored (same code as the API's sign-in).

    python3 scripts/create_user.py EMAIL "Full Name" student|admin
"""
import getpass
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "backend" / "src"))
from stack_outputs import output  # noqa: E402


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    email, name, role = sys.argv[1:]
    os.environ.setdefault("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
    os.environ["DATA_BUCKET"] = os.environ.get("DATA_BUCKET") or output("DataBucketName")

    import accounts
    import storage

    password = getpass.getpass(f"Password for {email} (at least 8 characters): ")
    if password != getpass.getpass("Type it again: "):
        sys.exit("Passwords do not match; nothing was created.")
    try:
        user = accounts.make_user(email, name, role, password)
        accounts.save_new_user(user)
    except ValueError as err:
        sys.exit(f"Not created: {err}")
    except storage.PreconditionFailed:
        sys.exit(f"Not created: an account for {email} already exists.")
    print(f"Created {role} {user['email']} ({user['name']})")


if __name__ == "__main__":
    main()
