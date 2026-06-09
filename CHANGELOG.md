# Changelog

All notable changes to the LearnUpon MCP Server are documented here.

---

## [2.1.0] — 2026-06-09

### Added

- **`suggestion` key in `lu_course_progress`** — non-group calls now include a suggestion to
  pass `group_name` for per-user detail, consistent with other tools.

### Fixed

- **`_paginate` infinite loop on sustained 429** — added `max_429_retries` (default 5) per
  page fetch. Previously the retry loop had no upper bound; a sustained rate limit would loop
  forever. Now raises after the retry budget is exhausted.

- **`lu_get_group_invites` null name handling** — LearnUpon returns `null` for `first_name`
  and `last_name` on pending invites. The `name` field in results now falls back to the email
  address instead of returning an empty string.

- **`lu_get_group_invites` pending count** — `pending` now counts only `invite_status=="sent"`
  records. Previously used `!= "accepted"` which would have miscounted any other status values
  (expired, etc.) as pending.

- **`lu_enrollment_status` missing `suggestion` key** — the exception handler now returns a
  suggestion consistent with all other tools.

- **`_build_user_cache` bare `except Exception`** — changed to `except requests.HTTPError`
  so only HTTP errors trigger the per-email fallback. Non-HTTP errors (network, auth) now
  propagate to the caller instead of being silently swallowed.

- **`_split_full_name` docstring** — added explicit documentation of all three cases
  (1-word, 2-word, 3+-word) and the rationale for the 3+-word first-two-words rule.

### Changed

- **SKILL.md v2.3.0** — corrected name splitting docs (2-word names split normally, not
  combined into first_name), added Step 6 to provisioning workflow (proactively offer
  lu_get_group_invites when pending_invite count > 0), updated tools table to show group_id
  alternative in lu_get_group_invites entry.

---

## [2.0.1] — 2026-06-09

### Fixed

- **`lu_get_group_invites` API response parsing** — the LearnUpon API returns group invites
  under the key `"group_invite"` (singular), not any of the pluralized variants that were being
  tried. The tool now uses `_paginate` with the correct key and correctly maps the response
  fields `invite_email_address` → `email`, `invite_status` → `status`. The `accept_url` is
  now also expanded from a relative path (`/accept_invitation/...`) to a full URL
  (`https://fivetranpartner.learnupon.com/accept_invitation/...`) before being returned.
  Removed the debug-only fallback code that raw-fetched and inspected response keys.

---

## [2.0.0] — 2026-06-09

### Added

- **`lu_get_group_invites` tool** — retrieves all pending invites for a group, including the
  per-user `accept_url`. Accepts `group_name` (resolved automatically) or `group_id`. Returns
  name, email, status, accept_url, created_at, and accepted_at per invitee. Designed for
  partners with email delivery issues (e.g. TCS) — share accept_urls directly instead of
  relying on invitation email delivery. Returns `pending`/`accepted` counts and a suggestion
  when pending invites exist.

- **`lu_lms_status` tool** — health-check tool that verifies credentials and returns a
  high-level snapshot: total groups, total courses, total enrolled learners, and overall pass
  rate. Use to confirm connectivity before running provisioning or cert checks.

- **`status_filter` parameter on `lu_enrollment_status`** — filter enrollments by status
  without post-processing. Accepts `'passed'`, `'failed'`, `'in_progress'`, `'not_started'`,
  `'completed'`. Example: "Show me all of Arun's in-progress courses."

- **`_build_user_cache` helper** — pre-fetches all user records in a single paginated pass
  before the enrollment loop. Eliminates the N×M lookup pattern (previously: one API call per
  user per course). Falls back to per-email lookups if the bulk fetch fails.

- **`_raise_for_response` helper** — centralized response validation that includes the full
  response body in error messages. Used by `api_get` and optionally by `api_post`.

- **Rate-limit retry logic in `api_get`** — automatically retries up to 3 times on HTTP 429,
  honoring the `Retry-After` header and falling back to exponential backoff.

- **`suggestion` keys in error responses** — actionable next-step hints added throughout:
  `lu_lms_status`, `lu_list_groups`, `lu_list_courses`, `lu_lookup_user`, `lu_enrollment_status`,
  `lu_course_progress`, and `lu_provision_users`.

- **`lu_provision_users` suggestion on pending invites** — when the provisioning run produces
  pending_invite results, the response now includes a `suggestion` key pointing to
  `lu_get_group_invites` as the next step.

### Changed

- **`lu_provision_users` now accepts native lists** — `users` parameter is now `list[dict]`
  (was `users_json: str`) and `courses` is now `list[str]` (was `course_names_json: str`).
  Claude no longer needs to JSON-encode these arguments; pass them directly as lists.

- **`api_post` gains a `check` parameter** — `api_post(..., check=True)` raises `HTTPError`
  immediately on non-2xx with full response body in message. Used for group creation in
  `lu_provision_users`. Default (`check=False`) preserves per-status-code handling for
  group invites and enrollments.

- **`lu_course_progress` group-not-found uses `group_error` key** — renamed from
  `group_warning` to match severity and tooling conventions. Also adds `available_groups`
  list and `suggestion` key.

- **`lu_lookup_user` not-found suggestion** — now points to `lu_get_group_invites` as the
  recommended next step when a user isn't found.

### Fixed

- **N×M API call pattern in `lu_provision_users`** — user lookups were called inside the
  per-course enrollment loop (O(users × courses) calls). Now pre-fetched once via
  `_build_user_cache` before the loop (O(1) bulk fetch).

- **Silent exception swallowing in `_find_user_by_email`** — the bare `except Exception`
  could hide auth errors and 5xx failures as "user not found." Fixed to only suppress
  genuine 404s; all other errors propagate.

- **Rate limits in `_paginate`** — pagination loop now retries on 429 instead of raising.

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
