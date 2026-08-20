# LearnUpon MCP Server

Integrates the LearnUpon LMS with Claude via MCP, giving you natural-language access to your
Partner Academy for provisioning, cert tracking, and group management.

## Repository structure

```
learnupon-mcp-server/
├── learnupon_server.py       # MCP server — all tools and API logic
├── run_server.py             # Entry point for Claude Desktop (uv, handles .env loading)
├── .env.example              # Credential template — copy to .env and fill in
├── .gitignore
├── README.md
├── .claude-plugin/
│   └── plugin.json           # Cowork plugin metadata (name, version, description)
└── skills/
    └── learnupon/
        └── SKILL.md          # Prompt instructions for Claude when using this plugin
```

---

## How it works

Claude Desktop spawns `run_server.py` as a subprocess (stdio transport). Credentials are
loaded from a `.env` file next to the server — no separate process to run, no startup scripts.

Dependencies are declared inline using [PEP 723](https://peps.python.org/pep-0723/) and
managed automatically by `uv` — no virtualenv setup required.

## Setup

### 1. Install uv

If you don't have `uv` installed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify: `which uv` — note the full path (e.g. `/Users/yourname/.local/bin/uv`).

### 2. Place server files

Save these files to a local directory (e.g. `~/mcp/learnupon/`):
- `learnupon_server.py`
- `run_server.py`
- `.env.example`

### 3. Create your .env file

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:
```bash
LU_SUBDOMAIN=yoursubdomain
LU_API_KEY=your_api_key_here
LU_API_SECRET=your_api_secret_here
```

API credentials are in LearnUpon admin: **Settings → Integrations → API**.

### 4. Add to Claude Desktop config

Open `~/Library/Application Support/Claude/claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "learnupon": {
      "command": "/Users/YOUR_USERNAME/.local/bin/uv",
      "args": ["run", "/Users/YOUR_USERNAME/mcp/learnupon/run_server.py"]
    }
  }
}
```

Use **absolute paths only** — no `~`, no relative paths.
Replace `command` with the output of `which uv`.
Replace the `args` path with the actual location of `run_server.py` on your machine.

On first run, `uv` will automatically install all dependencies declared in `run_server.py`.
No manual `pip install` needed.

### 5. Restart Claude Desktop

Quit completely (Cmd+Q), reopen, and **start a new conversation**.

---

## Tools

| Tool | Description |
|------|-------------|
| `lu_list_groups` | List all groups with member counts |
| `lu_list_courses` | List all courses with enrollment and completion stats |
| `lu_lookup_user` | Look up a user by email |
| `lu_enrollment_status` | Check a user's course enrollments, completion status, and cert expiry |
| `lu_course_progress` | Aggregate pass/completion stats for a course; per-user detail for a group |
| `lu_provision_users` | Bulk-invite users to a group and enroll in courses |

---

## Example prompts

> "List all groups in the Partner Academy."

> "Add these 12 Infosys contacts to the 'Infosys Sentara' group and enroll them in Fivetran Technical Foundations Certification."

> "Check if neha.kale@infosys.com has completed the Fivetran Technical Foundations cert."

> "How many people have passed the Fivetran Technical Foundations Certification?"

> "Show me completion status for the Capgemini group in the Fivetran Fundamentals course."

> "Who in TCS passed the Technical Foundations cert in March 2026?"

---

## Troubleshooting

**Tools not showing up:**
- Confirm both paths in `claude_desktop_config.json` are absolute and actually exist
- Validate the JSON: `python3 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json`
- Check logs: `tail -f ~/Library/Logs/Claude/mcp*.log`
- Quit Claude Desktop completely (Cmd+Q), reopen, start a NEW conversation

**`uv` not found:**
- Use the full path to uv in `claude_desktop_config.json` (e.g. `/Users/yourname/.local/bin/uv`)
- Claude Desktop has a restricted PATH that may not include your shell's PATH

**Auth errors:**
- Confirm `.env` is in the same directory as `run_server.py`
- Verify credentials in LearnUpon: Settings → Integrations → API

---

## Invitation flow note

New users get an invitation email. Until they accept, they won't appear in user lookups
and can't be enrolled. Re-running provisioning after they accept completes enrollment
automatically — no duplicates.

---

## LearnUpon API quirks

Hard-won behaviors of the upstream API. Verified empirically against
`fivetranpartneracademy` — check here before trusting a query parameter.

### `group_id` is accepted but ignored on most endpoints

Only `/api/v1/group_memberships` and `/api/v1/group_invites` actually honour `group_id`.
The others accept the parameter and **silently return unfiltered, platform-wide results**:

| Endpoint | `group_id` honoured? | Evidence |
| --- | --- | --- |
| `/api/v1/group_memberships` | ✅ yes | bogus id → 0 records; omitted → HTTP 404 |
| `/api/v1/group_invites` | ✅ yes | returns only that group's invites |
| `/api/v1/enrollments/search` | ❌ **ignored** | bogus id returns the full course roster |
| `/api/v1/users` | ❌ **ignored** | 496 of 499 returned were not group members |

No error, no warning — the filter is simply dropped. Any group scoping against
`enrollments/search` or `users` **must** be done client-side by intersecting on `user_id`.
This was the root cause of the v2.5.0 `lu_course_progress` bug.

### Group invites are not the membership roster

`/api/v1/group_invites` is an invite *log*, not a member list. Members added to a group
directly never appear in it. For "Hackathon FY26" the invite log held 417 records
(65 accepted) while actual membership was 439 — 374 members had no invite record at all.

Never derive "who is in this group" from invites. Use `/api/v1/group_memberships`
(or `number_of_members` on the group object, which agrees with it).

### `num_enrolled` disagrees with the enrollment records

The per-course counter on `/api/v1/courses` is cached and does not reliably match the
number of records returned by `/api/v1/enrollments/search`:

- It excludes records flagged `unenrolled: true` (withdrawn enrollments), which the
  enrollment search still returns. Filter these out to reconcile.
- It also just lags — Programmatic Management reported `num_enrolled: 68` against 67
  live records, with nothing withdrawn.

Prefer counts derived from the records themselves. Pagination is not the culprit here:
every enrollment id comes back exactly once, verified across all courses.

### A learner can hold several enrollment records on one course

Re-enrollment and recertification create genuinely distinct records with distinct
enrollment ids and enrollment dates (Connector SDK: 64 learners, 83 records). Deduplicate
by **enrollment id** for record integrity, and count **distinct `user_id`** when you mean
"how many people" — never dedupe by email, which discards real data.

### Response key naming is inconsistent

- `/api/v1/group_memberships` and `/api/v1/users` return the list under `"user"` (singular).
- `/api/v1/group_invites` returns `"group_invite"` (singular); its email field is
  `invite_email_address` and its status field is `invite_status`.
- `/api/v1/courses`, `/api/v1/groups`, `/api/v1/enrollments/search` use plural keys.

`_paginate` accepts a list of candidate keys to absorb this.

### Pagination

Pages are driven by the `LU-Has-Next-Page` response header, not by a total count.
`per_page=500` is accepted. `_paginate` also stops on an empty page as a defensive floor
against a stuck header.

---

## Changelog

### v1.2.0 — 2026-04-01

**Bug fixes — enrollment reporting now fully functional**

- **Fixed: enrollment search endpoint** — corrected `GET /api/v1/enrollments` to
  `GET /api/v1/enrollments/search` across `lu_course_progress` and `lu_enrollment_status`.
  The previous endpoint path returned 401 for all read operations. All per-user and
  group-scoped enrollment queries now work correctly.

- **Fixed: course stats returning zero** — corrected field names from `enrolled`/`passed`/
  `completed` etc. to the API's actual field names: `num_enrolled`, `num_passed`,
  `num_completed`, `num_in_progress`, `num_not_started`, `num_failed`, `num_pending_review`.
  `lu_list_courses` and `lu_course_progress` now return real aggregate data.

- **Improved: pagination** — `_paginate` now uses the `LU-Has-Next-Page` response header
  (LearnUpon's canonical pagination signal) instead of item count heuristics. Page size
  increased from 100 to 500 to match the enrollment search endpoint's maximum.

- **Improved: pagination params** — `_paginate` now accepts an optional `params` dict,
  enabling filtered paginated queries (e.g. by `course_id` + `group_id`).

**New fields surfaced**

- `lu_list_courses` / `lu_course_progress` — now includes `version` and `failed` count
  per course
- `lu_course_progress` (group-scoped) — now returns `cert_expires_at` per enrollment
- `lu_enrollment_status` — now returns `cert_expires_at`, corrected `score` source from
  `percentage` field, corrected `enrolled_at` from `date_enrolled`

### v1.1.0 — 2026-03-26

- Migrated to `uv` + PEP 723 inline dependencies — no virtualenv setup required
- Added `_paginate` helper for multi-page API responses
- Fixed group lookup to use `title` field (LearnUpon API) instead of `name`
- Fixed group creation payload to use `{"Group": {"title": ...}}`
- Fixed `_find_user_by_email` to re-raise non-404 HTTP errors instead of swallowing them
- Added `.gitignore`, `.env.example`, flat repo structure

### v1.0.0 — 2026-03-20

- Initial release: `lu_list_groups`, `lu_list_courses`, `lu_lookup_user`,
  `lu_enrollment_status`, `lu_course_progress`, `lu_provision_users`
