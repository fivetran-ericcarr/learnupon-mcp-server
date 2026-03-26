# Changelog

All notable changes to the LearnUpon MCP Server are documented here.

---

## [1.1.0] — 2026-03-26

### Added

- **`lu_lms_status` tool** — new health-check tool that verifies credentials and returns a
  high-level snapshot: total groups, total courses, total enrolled learners, and overall pass
  rate. Use this to confirm connectivity before running provisioning or cert checks.

- **`status_filter` parameter on `lu_enrollment_status`** — filter enrollments by status
  without post-processing. Accepts `'passed'`, `'failed'`, `'in_progress'`, `'not_started'`,
  `'completed'`. Example: "Show me all of Arun's in-progress courses."

- **`test_client.py`** — integration test script that exercises `get_conn`, `_get_all_groups`,
  `_get_all_courses`, `_find_user_by_email`, and all discovery tools directly against the live
  API. Run with `python3 servers/test_client.py [--email someone@example.com]`.

- **`available_groups` in group-not-found responses** — `lu_course_progress` now includes a
  list of all available group names when the requested group isn't found, matching the existing
  behavior for course-not-found responses.

- **`suggestion` keys in error responses** — actionable next-step hints added throughout:
  `lu_lms_status`, `lu_list_groups`, `lu_list_courses`, `lu_lookup_user`, `lu_enrollment_status`,
  `lu_course_progress`, and `lu_provision_users`.

- **`_build_user_cache` helper** — pre-fetches all user records for a provisioning batch in a
  single pass before the enrollment loop. Eliminates the N×M lookup pattern (previously: one
  API call per user per course).

- **`_raise_for_response` helper** — centralized response validation that includes the full
  response body in error messages. Used internally by `api_get` and optionally by `api_post`.

- **Rate-limit retry logic in `api_get`** — automatically retries up to 3 times on HTTP 429,
  honoring the `Retry-After` header and falling back to exponential backoff.

### Changed

- **`lu_provision_users` now accepts native lists** — `users` parameter is now `list[dict]`
  (was `users_json: str`) and `courses` is now `list[str]` (was `course_names_json: str`).
  Claude no longer needs to JSON-encode these arguments; pass them directly as lists.

- **`api_post` gains a `check` parameter** — `api_post(..., check=True)` raises `HTTPError`
  immediately on non-2xx. Used for group creation in `lu_provision_users` where a failure must
  halt the workflow. Default (`check=False`) preserves the existing per-status-code handling
  for group invites and enrollments.

- **`_find_user_by_email` now re-raises unexpected errors** — previously swallowed all
  exceptions silently. Now catches only `HTTPError` with status 404 (genuine not-found);
  all other errors (auth failures, network errors, 5xx) propagate to the caller.

- **Error messages from `get_conn` include remediation guidance** — missing env var errors
  now tell you to check your `.env` file placement and contents.

- **`lu_course_progress` group-not-found uses `group_error` key** — was `group_warning`
  (ambiguous); renamed to `group_error` to match severity and tooling conventions.

### Fixed

- **N×M API call pattern in `lu_provision_users`** — user lookups were previously called
  inside the per-course enrollment loop (O(users × courses) calls). Now called once per user
  before the loop (O(users) calls), with results cached in `user_cache`.

- **Silent exception swallowing in `_find_user_by_email`** — the bare `except Exception: pass`
  could hide auth errors, network failures, and server errors as a "user not found" result.
  Fixed to only suppress genuine 404s.

- **Unchecked `api_post` for group creation** — group creation used `resp.raise_for_status()`
  inline; standardized to `api_post(..., check=True)` which provides full response body in
  error messages.

---

## [1.0.0] — Initial release

- `lu_list_groups`, `lu_list_courses`, `lu_lookup_user`, `lu_enrollment_status`,
  `lu_course_progress`, `lu_provision_users`
- Basic auth via `LU_API_KEY` / `LU_API_SECRET` / `LU_SUBDOMAIN` environment variables
- Group auto-creation, dry-run mode, invite-then-enroll flow
- `run_server.py` entry point with explicit `.env` loading
