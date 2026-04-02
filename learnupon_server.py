#!/usr/bin/env python3
"""
LearnUpon MCP Server

Exposes LearnUpon LMS operations as MCP tools for Claude.

Required environment variables:
  LU_API_KEY      — LearnUpon API key
  LU_API_SECRET   — LearnUpon API secret
  LU_SUBDOMAIN    — LearnUpon subdomain (e.g. 'fivetranpartneracademy')

Install dependencies:
  uv run run_server.py       # recommended — deps declared inline in run_server.py
  # or: pip install "mcp[cli]" requests python-dotenv
"""

import json
import os
import sys
import time

try:
    import requests
    from requests.auth import HTTPBasicAuth
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


def get_conn():
    """Return (auth, base_url) from environment variables."""
    key = os.environ.get("LU_API_KEY", "")
    secret = os.environ.get("LU_API_SECRET", "")
    subdomain = os.environ.get("LU_SUBDOMAIN", "")
    missing = [k for k, v in [("LU_API_KEY", key), ("LU_API_SECRET", secret), ("LU_SUBDOMAIN", subdomain)] if not v]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    return HTTPBasicAuth(key, secret), f"https://{subdomain}.learnupon.com"


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(url, auth, params=None):
    resp = requests.get(url, auth=auth, headers=GET_HEADERS, params=params, timeout=30)
    if not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise requests.HTTPError(f"{resp.status_code} {resp.reason} — {detail}", response=resp)
    return resp.json()


def api_post(url, auth, payload):
    return requests.post(url, auth=auth, headers=POST_HEADERS, json=payload, timeout=30)


def _paginate(base, auth, endpoint, list_key, params=None, page_size=500):
    """Fetch all pages from a paginated LearnUpon endpoint."""
    results = []
    page = 1
    base_params = dict(params or {})
    while True:
        paged_params = {**base_params, "page": page, "per_page": page_size}
        resp = requests.get(
            f"{base}{endpoint}", auth=auth, headers=GET_HEADERS, params=paged_params, timeout=30
        )
        if not resp.ok:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise requests.HTTPError(f"{resp.status_code} {resp.reason} — {detail}", response=resp)
        data = resp.json()
        items = data if isinstance(data, list) else data.get(list_key, [])
        results.extend(items)
        has_next = resp.headers.get("LU-Has-Next-Page", "false").lower() == "true"
        if not has_next:
            break
        page += 1
    return results


def _get_all_groups(base, auth):
    return _paginate(base, auth, "/api/v1/groups", "groups")


def _get_all_courses(base, auth):
    return _paginate(base, auth, "/api/v1/courses", "courses")


def _find_group_by_name(groups, name):
    for g in groups:
        if g.get("title", "").lower() == name.lower():
            return g
    return None


def _find_course_by_name(courses, name):
    for c in courses:
        if c.get("name", "").lower() == name.lower():
            return c
    return None


def _find_user_by_email(base, auth, email):
    """
    Look up a user by email. Returns the user dict or None if not found.
    Raises requests.HTTPError for unexpected API errors (auth failure, 5xx, etc.).
    """
    try:
        data = api_get(f"{base}/api/v1/users", auth, params={"email": email})
        users = data if isinstance(data, list) else data.get("user", [])
        for u in users:
            if u.get("email", "").lower() == email.lower():
                return u
        return None
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise  # Re-raise auth failures, 5xx errors, etc.


def _split_full_name(full_name):
    parts = full_name.strip().split()
    if len(parts) >= 3:
        return " ".join(parts[:2]), " ".join(parts[2:])
    elif len(parts) == 2:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], ""
    return "", ""


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
        return json.dumps({"error": str(e)})


@mcp.tool()
def lu_list_courses() -> str:
    """
    List all courses in the LearnUpon LMS.
    Returns each course's id, name, version, enrollment count, and pass/completion stats.
    """
    try:
        auth, base = get_conn()
        courses = _get_all_courses(base, auth)
        summary = [
            {
                "id": c["id"],
                "name": c.get("name", ""),
                "version": c.get("version"),
                "enrolled": c.get("num_enrolled", 0),
                "passed": c.get("num_passed", 0),
                "completed": c.get("num_completed", 0),
                "in_progress": c.get("num_in_progress", 0),
                "not_started": c.get("num_not_started", 0),
                "failed": c.get("num_failed", 0),
                "pending_review": c.get("num_pending_review", 0),
            }
            for c in courses
        ]
        return json.dumps({"courses": summary, "total": len(summary)}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


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
def lu_enrollment_status(email: str, course_name: str = "") -> str:
    """
    Check a user's enrollment and completion status across all courses, or a specific course.
    Shows percentage complete, pass/fail status, completion date, and cert expiry.

    Args:
        email: The user's email address.
        course_name: Optional — filter results to a specific course (case-insensitive partial match).
                     Leave empty to return all enrollments.
    """
    try:
        auth, base = get_conn()
        user = _find_user_by_email(base, auth, email)
        if user is None:
            return json.dumps({
                "error": f"User not found: {email}",
                "note": "Users with pending invitations won't appear until they accept.",
            })

        user_id = user["id"]

        enrollments = _paginate(
            base, auth,
            "/api/v1/enrollments/search",
            "enrollments",
            params={"user_id": user_id},
        )

        if course_name:
            enrollments = [
                e for e in enrollments
                if course_name.lower() in (e.get("course_name") or "").lower()
            ]

        result = [
            {
                "course_name": e.get("course_name", ""),
                "status": e.get("status", ""),
                "percentage_complete": e.get("percentage_complete"),
                "score": e.get("percentage"),
                "passed": e.get("status") == "passed",
                "enrolled_at": e.get("date_enrolled"),
                "completed_at": e.get("date_completed"),
                "cert_expires_at": e.get("cert_expires_at"),
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
            })

        stats = {
            "course_name": course.get("name"),
            "course_id": course.get("id"),
            "version": course.get("version"),
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
                stats["group_warning"] = f"Group not found: {group_name!r}"
            else:
                try:
                    enrollments = _paginate(
                        base, auth,
                        "/api/v1/enrollments/search",
                        "enrollments",
                        params={"course_id": course["id"], "group_id": group["id"]},
                    )
                    stats["group_name"] = group_name
                    stats["group_members_enrolled"] = len(enrollments)
                    stats["group_enrollments"] = [
                        {
                            "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                            "email": e.get("email", ""),
                            "status": e.get("status", ""),
                            "percentage_complete": e.get("percentage_complete"),
                            "passed": e.get("status") == "passed",
                            "completed_at": e.get("date_completed"),
                            "cert_expires_at": e.get("cert_expires_at"),
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
    users_json: str,
    group_name: str,
    course_names_json: str = "[]",
    dry_run: bool = False,
) -> str:
    """
    Bulk-provision users: invite them to a group (creating it if needed) and enroll in courses.
    Users with pending invitations are invited and marked for enrollment — re-run after they
    accept to complete enrollment.

    Args:
        users_json: JSON array of user objects. Each needs 'email' plus one of:
                    - 'first_name' and 'last_name' (preferred)
                    - 'full_name' (split: first two words = first name, rest = last name)
                    - 'name' (alias for full_name)
                    Example: '[{"full_name": "Arun Kumar Mehta", "email": "arun@infosys.com"}]'

        group_name: Name of the group to add users to. Created automatically if it doesn't exist.

        course_names_json: JSON array of course names to enroll users in.
                           Example: '["Fivetran Technical Foundations Certification"]'
                           Leave as '[]' to only invite without enrolling.

        dry_run: If true, validates inputs and previews all actions without making API changes.
    """
    try:
        auth, base = get_conn()
    except Exception as e:
        return json.dumps({"error": str(e)})

    # Parse inputs
    try:
        raw_users = json.loads(users_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid users_json — not valid JSON: {e}"})

    try:
        course_list = json.loads(course_names_json) if course_names_json else []
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid course_names_json — not valid JSON: {e}"})

    # Normalize user records
    users = []
    for u in raw_users:
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
        users.append({"first_name": first_name, "last_name": last_name, "email": email})

    if not users:
        return json.dumps({"error": "No valid users found in users_json (check that each entry has an 'email' field)"})

    try:
        # Resolve group
        groups = _get_all_groups(base, auth)
        existing_group = _find_group_by_name(groups, group_name)
        if existing_group:
            group_id = existing_group["id"]
            group_created = False
        elif dry_run:
            group_id = -1
            group_created = True
        else:
            resp = api_post(f"{base}/api/v1/groups", auth, {"Group": {"title": group_name}})
            resp.raise_for_status()
            g = resp.json()
            group = g.get("group") or g.get("Group") or g
            group_id = group["id"]
            group_created = True

        # Resolve courses
        all_courses = _get_all_courses(base, auth)
        course_map = {c["name"].lower(): c["id"] for c in all_courses}
        resolved_courses = {}
        unresolved_courses = []
        for name in course_list:
            cid = course_map.get(name.lower())
            if cid:
                resolved_courses[name] = cid
            else:
                unresolved_courses.append(name)

        results = {
            "dry_run": dry_run,
            "group": group_name,
            "group_created": group_created,
            "courses": course_list,
            "unresolved_courses": unresolved_courses,
            "summary": {
                "total": len(users),
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

        for i, user in enumerate(users):
            email = user["email"]
            first_name = user["first_name"]
            last_name = user["last_name"]
            user_result = {
                "name": f"{first_name} {last_name}".strip(),
                "email": email,
                "invite": None,
                "enrollments": [],
            }

            # --- Invite to group ---
            if dry_run:
                invite_result = {"status": "dry_run", "message": "Would invite to group"}
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

            # --- Enroll in courses ---
            for course_name, course_id in resolved_courses.items():
                if dry_run:
                    enroll_result = {"status": "dry_run", "course": course_name, "message": "Would enroll"}
                else:
                    lu_user = _find_user_by_email(base, auth, email)
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

            if not dry_run and i < len(users) - 1:
                time.sleep(0.3)

        return json.dumps(results, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When run directly, default to stdio (Claude Desktop standard).
    # Use run_server.py as the entry point — it handles .env loading.
    mcp.run(transport="stdio")
