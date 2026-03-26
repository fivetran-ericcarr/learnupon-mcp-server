#!/usr/bin/env python3
"""
LearnUpon MCP Server

Exposes LearnUpon LMS operations as MCP tools for Claude.

Required environment variables:
  LU_API_KEY      — LearnUpon API key
  LU_API_SECRET   — LearnUpon API secret
  LU_SUBDOMAIN    — LearnUpon subdomain (e.g. 'fivetranpartneracademy')

Install dependencies:
  uv run --with "mcp[cli]" --with requests learnupon_server.py
  # or: pip install "mcp[cli]" requests
"""

import json
import os
import sys
import time

try:
    import requests
    from requests.auth import HTTPBasicAuth
    from requests.exceptions import HTTPError
except ImportError:
    print("Missing dependency: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("Missing dependency: pip install 'mcp[cli]'", file=sys.stderr)
    sys.exit(1)


mcp = FastMCP("learnupon")


# ---------------------------------------------------------------------------
# Auth & headers
# ---------------------------------------------------------------------------

GET_HEADERS = {"Accept": "application/json"}
POST_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

# Max retries for rate-limited (429) responses
_MAX_RETRIES = 3


def get_conn():
    """Return (auth, base_url) from environment variables."""
    key = os.environ.get("LU_API_KEY", "")
    secret = os.environ.get("LU_API_SECRET", "")
    subdomain = os.environ.get("LU_SUBDOMAIN", "")
    missing = [k for k, v in [("LU_API_KEY", key), ("LU_API_SECRET", secret), ("LU_SUBDOMAIN", subdomain)] if not v]
    if missing:
        raise RuntimeError(
            f"Missing environment variables: {', '.join(missing)}. "
            "Check that your .env file is in the same directory as run_server.py and contains all three variables."
        )
    return HTTPBasicAuth(key, secret), f"https://{subdomain}.learnupon.com"


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _raise_for_response(resp: requests.Response, context: str = "") -> dict:
    """
    Raise HTTPError for non-2xx responses; return parsed JSON for success.
    Includes response body in the error message for easier debugging.
    """
    if not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        prefix = f"{context}: " if context else ""
        raise HTTPError(
            f"{prefix}HTTP {resp.status_code} {resp.reason} — {detail}",
            response=resp,
        )
    try:
        return resp.json()
    except Exception:
        return {}


def api_get(url: str, auth: HTTPBasicAuth, params: dict = None) -> dict:
    """
    GET with automatic retry on 429 (rate limit).
    Respects Retry-After header; falls back to exponential backoff.
    Raises HTTPError on non-2xx responses.
    """
    for attempt in range(_MAX_RETRIES):
        resp = requests.get(url, auth=auth, headers=GET_HEADERS, params=params, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
            if attempt < _MAX_RETRIES - 1:
                time.sleep(retry_after)
                continue
        return _raise_for_response(resp)
    # Exhausted retries — raise on the last 429
    return _raise_for_response(resp)  # type: ignore[possibly-undefined]


def api_post(url: str, auth: HTTPBasicAuth, payload: dict, check: bool = False) -> requests.Response:
    """
    POST and return the raw response.
    If check=True, raises HTTPError on non-2xx (use for operations that must succeed).
    """
    resp = requests.post(url, auth=auth, headers=POST_HEADERS, json=payload, timeout=30)
    if check:
        _raise_for_response(resp)
    return resp


def _get_all_groups(base: str, auth: HTTPBasicAuth) -> list:
    data = api_get(f"{base}/api/v1/groups", auth)
    return data if isinstance(data, list) else data.get("groups", [])


def _get_all_courses(base: str, auth: HTTPBasicAuth) -> list:
    data = api_get(f"{base}/api/v1/courses", auth)
    return data if isinstance(data, list) else data.get("courses", [])


def _find_group_by_name(groups: list, name: str) -> dict | None:
    for g in groups:
        if g.get("title", "").lower() == name.lower():
            return g
    return None


def _find_course_by_name(courses: list, name: str) -> dict | None:
    for c in courses:
        if c.get("name", "").lower() == name.lower():
            return c
    return None


def _find_user_by_email(base: str, auth: HTTPBasicAuth, email: str) -> dict | None:
    """
    Look up a user by email. Returns the user dict or None if not found.
    Raises HTTPError for unexpected API errors (not 404).
    """
    try:
        data = api_get(f"{base}/api/v1/users", auth, params={"email": email})
        users = data if isinstance(data, list) else data.get("user", [])
        for u in users:
            if u.get("email", "").lower() == email.lower():
                return u
    except HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise
    return None


def _build_user_cache(base: str, auth: HTTPBasicAuth, emails: list[str]) -> dict[str, dict | None]:
    """
    Pre-fetch user records for a list of emails in a single pass.
    Returns {email: user_dict_or_None}.
    """
    cache: dict[str, dict | None] = {}
    for email in emails:
        cache[email] = _find_user_by_email(base, auth, email)
    return cache


def _split_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if len(parts) >= 3:
        return " ".join(parts[:2]), " ".join(parts[2:])
    elif len(parts) == 2:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], ""
    return "", ""


# ---------------------------------------------------------------------------
# MCP Tools — Health Check
# ---------------------------------------------------------------------------

@mcp.tool()
def lu_lms_status() -> str:
    """
    Quick health check for the LearnUpon LMS connection.
    Returns total groups, total courses, total enrolled learners, and overall pass rate.
    Use this to verify credentials and get a high-level snapshot before deeper operations.
    """
    try:
        auth, base = get_conn()
        groups = _get_all_groups(base, auth)
        courses = _get_all_courses(base, auth)

        total_enrolled = sum(c.get("num_enrolled", 0) for c in courses)
        total_passed = sum(c.get("num_passed", 0) for c in courses)
        pass_rate = round(total_passed / total_enrolled * 100, 1) if total_enrolled else 0.0

        return json.dumps({
            "status": "connected",
            "subdomain": os.environ.get("LU_SUBDOMAIN", ""),
            "total_groups": len(groups),
            "total_courses": len(courses),
            "total_enrolled": total_enrolled,
            "total_passed": total_passed,
            "overall_pass_rate_pct": pass_rate,
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": str(e),
            "suggestion": "Check LU_API_KEY, LU_API_SECRET, and LU_SUBDOMAIN in your .env file.",
        })


# ---------------------------------------------------------------------------
# MCP Tools — Discovery
# ---------------------------------------------------------------------------

@mcp.tool()
def lu_list_groups() -> str:
    """
    List all groups in the LearnUpon LMS.
    Returns each group's id, title, and member count.
    """
    try:
        auth, base = get_conn()
        groups = _get_all_groups(base, auth)
        summary = [
            {
                "id": g["id"],
                "title": g.get("title", ""),
                "members": g.get("number_of_members", 0),
            }
            for g in groups
        ]
        return json.dumps({"groups": summary, "total": len(summary)}, indent=2)
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "suggestion": "Run lu_lms_status to verify your connection.",
        })


@mcp.tool()
def lu_list_courses() -> str:
    """
    List all courses in the LearnUpon LMS.
    Returns each course's id, name, enrollment count, and pass/completion stats.
    """
    try:
        auth, base = get_conn()
        courses = _get_all_courses(base, auth)
        summary = [
            {
                "id": c["id"],
                "name": c.get("name", ""),
                "enrolled": c.get("num_enrolled", 0),
                "passed": c.get("num_passed", 0),
                "completed": c.get("num_completed", 0),
                "in_progress": c.get("num_in_progress", 0),
                "not_started": c.get("num_not_started", 0),
            }
            for c in courses
        ]
        return json.dumps({"courses": summary, "total": len(summary)}, indent=2)
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "suggestion": "Run lu_lms_status to verify your connection.",
        })


# ---------------------------------------------------------------------------
# MCP Tools — User Lookup
# ---------------------------------------------------------------------------

@mcp.tool()
def lu_lookup_user(email: str) -> str:
    """
    Look up a LearnUpon user by email address.
    Returns their profile including id, name, enrollment count, sign-in history, and account status.
    Users with pending (unaccepted) invitations may not appear.

    Args:
        email: The user's email address.
    """
    try:
        auth, base = get_conn()
        user = _find_user_by_email(base, auth, email)
        if user is None:
            return json.dumps({
                "found": False,
                "email": email,
                "message": "User not found — they may have a pending invitation they haven't accepted yet.",
                "suggestion": "Re-run lu_provision_users after the user accepts their invitation to complete enrollment.",
            })
        return json.dumps({
            "found": True,
            "id": user.get("id"),
            "email": user.get("email"),
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "enabled": user.get("enabled"),
            "user_type": user.get("user_type"),
            "sign_in_count": user.get("sign_in_count", 0),
            "number_of_enrollments": user.get("number_of_enrollments", 0),
            "last_sign_in_at": user.get("last_sign_in_at"),
            "created_at": user.get("created_at"),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# MCP Tools — Enrollment & Cert Status
# ---------------------------------------------------------------------------

@mcp.tool()
def lu_enrollment_status(email: str, course_name: str = "", status_filter: str = "") -> str:
    """
    Check a user's enrollment and completion status across all courses, or a specific course.
    Shows percentage complete, pass/fail status, and completion date.

    Args:
        email: The user's email address.
        course_name: Optional — filter results to a specific course (case-insensitive partial match).
                     Leave empty to return all enrollments.
        status_filter: Optional — filter by status. One of: 'passed', 'failed', 'in_progress',
                       'not_started', 'completed'. Leave empty to return all statuses.
    """
    try:
        auth, base = get_conn()
        user = _find_user_by_email(base, auth, email)
        if user is None:
            return json.dumps({
                "error": f"User not found: {email}",
                "note": "Users with pending invitations won't appear until they accept.",
                "suggestion": "Use lu_lookup_user to confirm, or re-run after they accept their invitation.",
            })

        user_id = user["id"]

        # Try the user-scoped enrollment endpoint first, fall back to global with filter
        try:
            data = api_get(f"{base}/api/v1/users/{user_id}/enrollments", auth)
            enrollments = data if isinstance(data, list) else data.get("enrollment", [])
        except Exception:
            data = api_get(f"{base}/api/v1/enrollments", auth, params={"user_id": user_id})
            enrollments = data if isinstance(data, list) else data.get("enrollment", [])

        if course_name:
            enrollments = [
                e for e in enrollments
                if course_name.lower() in (e.get("course_name") or e.get("name") or "").lower()
            ]

        if status_filter:
            enrollments = [
                e for e in enrollments
                if (e.get("status") or "").lower() == status_filter.lower()
            ]

        result = [
            {
                "course_name": e.get("course_name") or e.get("name", ""),
                "status": e.get("status", ""),
                "percentage_complete": e.get("percentage_complete"),
                "score": e.get("score"),
                "passed": e.get("passed"),
                "completed_at": e.get("completed_at"),
                "enrolled_at": e.get("created_at"),
            }
            for e in enrollments
        ]

        return json.dumps({
            "user": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "email": email,
            "total_enrollments": len(result),
            "enrollments": result,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def lu_course_progress(course_name: str, group_name: str = "") -> str:
    """
    Get aggregate completion and pass-rate stats for a course.
    Optionally scope to a specific group to see per-user details within that group.

    Args:
        course_name: The course name (case-insensitive, exact match preferred).
        group_name: Optional — scope results to a specific group for per-user detail.
    """
    try:
        auth, base = get_conn()
        courses = _get_all_courses(base, auth)
        course = _find_course_by_name(courses, course_name)
        if course is None:
            available = sorted(c["name"] for c in courses)
            return json.dumps({
                "error": f"Course not found: {course_name!r}",
                "available_courses": available,
                "suggestion": "Check spelling or use lu_list_courses to see all available courses.",
            })

        stats = {
            "course_name": course.get("name"),
            "course_id": course.get("id"),
            "total_enrolled": course.get("num_enrolled", 0),
            "not_started": course.get("num_not_started", 0),
            "in_progress": course.get("num_in_progress", 0),
            "completed": course.get("num_completed", 0),
            "passed": course.get("num_passed", 0),
            "failed": course.get("num_failed", 0),
            "pending_review": course.get("num_pending_review", 0),
        }

        if group_name:
            groups = _get_all_groups(base, auth)
            group = _find_group_by_name(groups, group_name)
            if group is None:
                available_groups = sorted(g.get("title", "") for g in groups)
                stats["group_error"] = f"Group not found: {group_name!r}"
                stats["available_groups"] = available_groups
                stats["suggestion"] = "Check spelling or use lu_list_groups to see all available groups."
            else:
                try:
                    data = api_get(
                        f"{base}/api/v1/enrollments",
                        auth,
                        params={"course_id": course["id"], "group_id": group["id"]},
                    )
                    enrollments = data if isinstance(data, list) else data.get("enrollment", [])
                    stats["group_name"] = group_name
                    stats["group_members_enrolled"] = len(enrollments)
                    stats["group_enrollments"] = [
                        {
                            "name": f"{e.get('user_first_name', '')} {e.get('user_last_name', '')}".strip(),
                            "email": e.get("user_email", ""),
                            "status": e.get("status", ""),
                            "percentage_complete": e.get("percentage_complete"),
                            "passed": e.get("passed"),
                            "completed_at": e.get("completed_at"),
                        }
                        for e in enrollments
                    ]
                except Exception as ex:
                    stats["group_warning"] = f"Could not fetch group-level detail: {ex}"

        return json.dumps(stats, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# MCP Tools — Provisioning
# ---------------------------------------------------------------------------

@mcp.tool()
def lu_provision_users(
    users: list[dict],
    group_name: str,
    courses: list[str] = [],
    dry_run: bool = False,
) -> str:
    """
    Bulk-provision users: invite them to a group (creating it if needed) and enroll in courses.
    Users with pending invitations are invited and marked for enrollment — re-run after they
    accept to complete enrollment.

    Args:
        users: List of user objects. Each needs 'email' plus one of:
               - 'first_name' and 'last_name' (preferred)
               - 'full_name' (split: first two words = first name, rest = last name)
               - 'name' (alias for full_name)
               Example: [{"full_name": "Arun Kumar Mehta", "email": "arun@infosys.com"}]

        group_name: Name of the group to add users to. Created automatically if it doesn't exist.

        courses: List of course names to enroll users in.
                 Example: ["Fivetran Technical Foundations Certification"]
                 Leave as [] to only invite without enrolling.

        dry_run: If true, validates inputs and previews all actions without making API changes.
    """
    try:
        auth, base = get_conn()
    except Exception as e:
        return json.dumps({"error": str(e)})

    # Normalize user records
    normalized_users = []
    for u in users:
        email = u.get("email", "").strip()
        if not email:
            continue
        if "first_name" in u or "last_name" in u:
            first_name = u.get("first_name", "").strip()
            last_name = u.get("last_name", "").strip()
        elif "full_name" in u:
            first_name, last_name = _split_full_name(u["full_name"])
        elif "name" in u:
            first_name, last_name = _split_full_name(u["name"])
        else:
            first_name = email.split("@")[0]
            last_name = ""
        normalized_users.append({"first_name": first_name, "last_name": last_name, "email": email})

    if not normalized_users:
        return json.dumps({"error": "No valid users found (check that each entry has an 'email' field)"})

    try:
        # Resolve group
        all_groups = _get_all_groups(base, auth)
        existing_group = _find_group_by_name(all_groups, group_name)
        if existing_group:
            group_id = existing_group["id"]
            group_created = False
        elif dry_run:
            group_id = -1
            group_created = True
        else:
            resp = api_post(
                f"{base}/api/v1/groups",
                auth,
                {"Group": {"title": group_name}},
                check=True,  # group creation must succeed — raise immediately if it doesn't
            )
            g = resp.json()
            group = g.get("group") or g.get("Group") or g
            group_id = group["id"]
            group_created = True

        # Resolve courses
        all_courses = _get_all_courses(base, auth)
        course_map = {c["name"].lower(): c["id"] for c in all_courses}
        resolved_courses: dict[str, int] = {}
        unresolved_courses: list[str] = []
        for name in courses:
            cid = course_map.get(name.lower())
            if cid:
                resolved_courses[name] = cid
            else:
                unresolved_courses.append(name)

        results: dict = {
            "dry_run": dry_run,
            "group": group_name,
            "group_created": group_created,
            "courses": courses,
            "unresolved_courses": unresolved_courses,
            "summary": {
                "total": len(normalized_users),
                "invited": 0,
                "already_in_group": 0,
                "enrolled": 0,
                "pending_invite": 0,
                "errors": 0,
            },
            "users": [],
        }

        if unresolved_courses:
            results["available_courses"] = sorted(c["name"] for c in all_courses)
            results["suggestion"] = (
                f"Could not find course(s): {unresolved_courses}. "
                "Check spelling — names must match exactly. See available_courses above."
            )

        # Pre-build user cache once — avoids N×M lookups (one lookup per user, not per user×course)
        emails = [u["email"] for u in normalized_users]
        user_cache: dict[str, dict | None] = {} if dry_run else _build_user_cache(base, auth, emails)

        for i, user in enumerate(normalized_users):
            email = user["email"]
            first_name = user["first_name"]
            last_name = user["last_name"]
            user_result: dict = {
                "name": f"{first_name} {last_name}".strip(),
                "email": email,
                "invite": None,
                "enrollments": [],
            }

            # --- Invite to group ---
            if dry_run:
                invite_result: dict = {"status": "dry_run", "message": "Would invite to group"}
            else:
                payload = {
                    "GroupInvite": {
                        "email_addresses": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "group_id": group_id,
                        "group_membership_type_id": 1,
                    }
                }
                resp = api_post(f"{base}/api/v1/group_invites", auth, payload)
                if resp.status_code in (200, 201):
                    invite_result = {"status": "invited", "message": "Invited to group"}
                elif resp.status_code in (400, 422):
                    body = resp.json() if resp.content else {}
                    msg = str(body.get("message") or body.get("error") or body)
                    if "duplicate invite" in msg.lower() or "already been invited" in msg.lower():
                        invite_result = {"status": "already_in_group", "message": "Already in group"}
                    else:
                        invite_result = {"status": "error", "message": f"HTTP {resp.status_code}: {body}"}
                else:
                    body = resp.json() if resp.content else {}
                    invite_result = {"status": "error", "message": f"HTTP {resp.status_code}: {body}"}

            user_result["invite"] = invite_result
            if invite_result["status"] == "invited":
                results["summary"]["invited"] += 1
            elif invite_result["status"] == "already_in_group":
                results["summary"]["already_in_group"] += 1
            elif invite_result["status"] == "error":
                results["summary"]["errors"] += 1

            # --- Enroll in courses (use pre-built cache — no repeated lookups) ---
            for course_name, course_id in resolved_courses.items():
                if dry_run:
                    enroll_result: dict = {"status": "dry_run", "course": course_name, "message": "Would enroll"}
                else:
                    lu_user = user_cache.get(email)
                    if lu_user is None:
                        enroll_result = {
                            "status": "pending_invite",
                            "course": course_name,
                            "message": "Re-run after user accepts their invitation",
                        }
                    else:
                        enroll_resp = api_post(
                            f"{base}/api/v1/enrollments",
                            auth,
                            {"Enrollment": {"user_id": lu_user["id"], "course_id": course_id}},
                        )
                        if enroll_resp.status_code in (200, 201):
                            enroll_result = {"status": "enrolled", "course": course_name, "message": "Enrolled"}
                        elif enroll_resp.status_code == 422:
                            body = enroll_resp.json() if enroll_resp.content else {}
                            enroll_result = {
                                "status": "already_enrolled",
                                "course": course_name,
                                "message": body.get("message", "Already enrolled"),
                            }
                        else:
                            body = enroll_resp.json() if enroll_resp.content else {}
                            enroll_result = {
                                "status": "error",
                                "course": course_name,
                                "message": f"HTTP {enroll_resp.status_code}: {body}",
                            }

                user_result["enrollments"].append(enroll_result)
                status = enroll_result["status"]
                if status in ("enrolled", "already_enrolled"):
                    results["summary"]["enrolled"] += 1
                elif status == "pending_invite":
                    results["summary"]["pending_invite"] += 1
                elif status == "error":
                    results["summary"]["errors"] += 1

            results["users"].append(user_result)

            if not dry_run and i < len(normalized_users) - 1:
                time.sleep(0.3)

        return json.dumps(results, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When run directly, default to stdio (Claude Desktop standard).
    # Use run_server.py as the entry point — it handles .env loading.
    mcp.run(transport="stdio")
