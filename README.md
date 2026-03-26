# LearnUpon MCP Server

Integrates the LearnUpon LMS with Claude via MCP, giving you natural-language access to your
LearnUpon instance for provisioning, cert tracking, and group management.

## How it works

Claude Desktop spawns `run_server.py` as a subprocess (stdio transport). Credentials are
loaded from a `.env` file next to the server — no separate process to run, no startup scripts.

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/learnupon-mcp-server.git ~/mcp/learnupon
```

### 2. Create your .env file

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:
```bash
LU_SUBDOMAIN=your-subdomain
LU_API_KEY=your_api_key_here
LU_API_SECRET=your_api_secret_here
```

Your subdomain is the part before `.learnupon.com` in your LMS URL.
API credentials are in LearnUpon admin: **Settings → Integrations → API**.

### 3. Install dependencies

```bash
uv pip install "mcp[cli]" requests
```

If you don't have `uv` installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 4. Find your uv path

```bash
which uv
# e.g. /Users/your_username/.local/bin/uv
```

### 5. Add to Claude Desktop config

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

### 6. Restart Claude Desktop

Quit completely (Cmd+Q), reopen, and **start a new conversation**.

---

## Tools

| Tool | Description |
|------|-------------|
| `lu_lms_status` | Health check — verifies credentials and returns snapshot stats (groups, courses, enrollments, pass rate) |
| `lu_list_groups` | List all groups with member counts |
| `lu_list_courses` | List all courses with enrollment and completion stats |
| `lu_lookup_user` | Look up a user by email |
| `lu_enrollment_status` | Check a user's course enrollments and completion status; filter by `status_filter` (e.g. `'passed'`, `'in_progress'`) |
| `lu_course_progress` | Aggregate pass/completion stats for a course; per-user detail for a group |
| `lu_provision_users` | Bulk-invite users to a group and enroll in courses |

---

## Example prompts

> "Check if the LearnUpon connection is working."

> "List all groups in the LMS."

> "Add these 10 users to the 'Acme Onboarding' group and enroll them in the Technical Foundations course."

> "Check if jane.doe@example.com has completed the Technical Foundations cert."

> "How many people have passed the Technical Foundations course?"

> "Show me completion status for the Acme group in the Technical Foundations course."

> "Show me all enrollments for john.smith@example.com where status is in_progress."

---

## Testing

Run the integration test client to verify your setup against the live API:

```bash
# Basic connectivity and list tests
uv run test_client.py

# Include a user lookup test
uv run test_client.py --email someone@example.com
```

The test client exercises `get_conn`, `_get_all_groups`, `_get_all_courses`, `_find_user_by_email`,
`lu_lms_status`, `lu_list_groups`, `lu_list_courses`, and `lu_lookup_user`.

---

## Troubleshooting

**Tools not showing up:**
- Confirm both paths in `claude_desktop_config.json` are absolute and actually exist
- Validate the JSON: `uv run -c "import json, pathlib; json.loads(pathlib.Path('~/Library/Application Support/Claude/claude_desktop_config.json').expanduser().read_text())"`
- Check logs: `tail -f ~/Library/Logs/Claude/mcp*.log`
- Quit Claude Desktop completely (Cmd+Q), reopen, start a NEW conversation

**Auth errors:**
- Confirm `.env` is in the same directory as `run_server.py`
- Verify credentials in LearnUpon: Settings → Integrations → API
- Run `uv run test_client.py` to diagnose connection issues directly

**Rate limiting (429 errors):**
- The server automatically retries with backoff (up to 3 attempts, respecting `Retry-After`)
- If you're hitting persistent rate limits, reduce the number of users in a single `lu_provision_users` call

---

## Invitation flow note

New users get an invitation email. Until they accept, they won't appear in user lookups
and can't be enrolled. Re-running provisioning after they accept completes enrollment
automatically — no duplicates.
