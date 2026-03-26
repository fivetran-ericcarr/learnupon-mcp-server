#!/usr/bin/env python3
"""
LearnUpon MCP Server — integration test client.

Exercises the core helpers and tools directly against the live API.
Requires a valid .env in this directory (or environment variables already set).

Usage:
    python3 test_client.py
    python3 test_client.py --email someone@example.com
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Load .env from this directory if present
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except ImportError:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

# Ensure the server module is importable
sys.path.insert(0, str(Path(__file__).parent))

from learnupon_server import (
    get_conn,
    _get_all_groups,
    _get_all_courses,
    _find_user_by_email,
    lu_lms_status,
    lu_list_groups,
    lu_list_courses,
    lu_lookup_user,
)


def _pass(label: str):
    print(f"  ✅ {label}")


def _fail(label: str, detail: str = ""):
    print(f"  ❌ {label}" + (f": {detail}" if detail else ""))


def _section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_credentials():
    _section("Test: get_conn()")
    try:
        auth, base = get_conn()
        assert auth is not None
        assert base.startswith("https://")
        _pass(f"Connected to {base}")
    except Exception as e:
        _fail("get_conn() raised an exception", str(e))
        sys.exit(1)


def test_list_groups():
    _section("Test: _get_all_groups() + lu_list_groups()")
    auth, base = get_conn()
    try:
        groups = _get_all_groups(base, auth)
        assert isinstance(groups, list), f"Expected list, got {type(groups)}"
        _pass(f"_get_all_groups() returned {len(groups)} groups")
    except Exception as e:
        _fail("_get_all_groups() raised an exception", str(e))

    result = json.loads(lu_list_groups())
    if "error" in result:
        _fail("lu_list_groups() returned error", result["error"])
    else:
        _pass(f"lu_list_groups() returned {result['total']} groups")
        if result["groups"]:
            sample = result["groups"][0]
            assert "id" in sample and "title" in sample and "members" in sample
            _pass(f"Sample group: {sample['title']!r} ({sample['members']} members)")


def test_list_courses():
    _section("Test: _get_all_courses() + lu_list_courses()")
    auth, base = get_conn()
    try:
        courses = _get_all_courses(base, auth)
        assert isinstance(courses, list), f"Expected list, got {type(courses)}"
        _pass(f"_get_all_courses() returned {len(courses)} courses")
    except Exception as e:
        _fail("_get_all_courses() raised an exception", str(e))

    result = json.loads(lu_list_courses())
    if "error" in result:
        _fail("lu_list_courses() returned error", result["error"])
    else:
        _pass(f"lu_list_courses() returned {result['total']} courses")


def test_lms_status():
    _section("Test: lu_lms_status()")
    result = json.loads(lu_lms_status())
    if result.get("status") == "connected":
        _pass(
            f"LMS status: {result['total_groups']} groups, "
            f"{result['total_courses']} courses, "
            f"{result['total_enrolled']} enrolled, "
            f"{result['overall_pass_rate_pct']}% pass rate"
        )
    else:
        _fail("lu_lms_status() returned error", result.get("error", "unknown"))


def test_user_lookup(email: str):
    _section(f"Test: _find_user_by_email() + lu_lookup_user() for {email}")
    auth, base = get_conn()
    try:
        user = _find_user_by_email(base, auth, email)
        if user is None:
            _pass(f"_find_user_by_email() returned None (user not found or pending invite)")
        else:
            _pass(f"_find_user_by_email() found: {user.get('first_name')} {user.get('last_name')} (id={user.get('id')})")
    except Exception as e:
        _fail("_find_user_by_email() raised unexpected exception", str(e))

    result = json.loads(lu_lookup_user(email))
    if result.get("found"):
        _pass(f"lu_lookup_user() found: {result['first_name']} {result['last_name']}, "
              f"{result['number_of_enrollments']} enrollment(s)")
    elif result.get("found") is False:
        _pass(f"lu_lookup_user() correctly returned not-found for {email}")
    else:
        _fail("lu_lookup_user() returned error", result.get("error", "unknown"))


def test_not_found_user():
    _section("Test: _find_user_by_email() with nonexistent email")
    auth, base = get_conn()
    try:
        user = _find_user_by_email(base, auth, "definitely.not.a.real.user@nowhere.example.com")
        if user is None:
            _pass("Correctly returned None for nonexistent user")
        else:
            _fail("Expected None but got a user dict", str(user))
    except Exception as e:
        _fail("Raised exception instead of returning None", str(e))


def main():
    parser = argparse.ArgumentParser(description="LearnUpon MCP Server integration tests")
    parser.add_argument(
        "--email",
        default="",
        help="Email address to test lu_lookup_user against (optional; skipped if not provided)",
    )
    args = parser.parse_args()

    print("\nLearnUpon MCP Server — Integration Tests")
    print("==========================================")

    test_credentials()
    test_lms_status()
    test_list_groups()
    test_list_courses()
    test_not_found_user()

    if args.email:
        test_user_lookup(args.email)
    else:
        print("\n  (Skipping user lookup — pass --email to test)")

    print("\n==========================================")
    print("  Tests complete.\n")


if __name__ == "__main__":
    main()
