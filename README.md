# LearnUpon MCP Server

Integrates the LearnUpon LMS with Claude via MCP, giving you natural-language access to the
Fivetran Partner Academy for provisioning, cert tracking, and group management.

## How it works

Claude Desktop spawns `run_server.py` as a subprocess (stdio transport). Credentials are
loaded from a `.env` file next to the server — no separate process to run, no startup scripts.

## Setup

### 1. Place server files

Save these files to a local directory (e.g. `~/mcp/learnupon/`):
- `learnupon_server.py`
- `run_server.py`
- `.env.example`

### 2. Create your .env file

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:
```bash
LU_SUBDOMAIN=fivetranpartneracademy
LU_API_KEY=your_api_key_here
LU_API_SECRET=your_api_secret_here
```

API credentials are in LearnUpon admin: **Settings → Integrations → API**.

### 3. Install dependencies

```bash
pip install "mcp[cli]" requests
```

### 4. Verify your Python path

```bash
which python3
# e.g. /usr/bin/python3 or /usr/local/bin/python3
```

### 5. Add to Claude Desktop config

Open `~/Library/Application Support/Claude/claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "learnupon": {
      "command": "/usr/bin/python3",
      "args": ["/Users/YOUR_USERNAME/mcp/learnupon/run_server.py"]
    }
  }
}
```

Use **absolute paths only** — no `~`, no relative paths.
Replace `command` with the output of `which python3`.
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

> "List all groups in the Partner Academy."

> "Add these 12 Infosys contacts to the 'Infosys Sentara' group and enroll them in Fivetran Technical Foundations Certification."

> "Check if neha.kale@infosys.com has completed the Fivetran Technical Foundations cert."

> "How many people have passed the Fivetran Technical Foundations Certification?"

> "Show me completion status for the Capgemini group in the Fivetran Fundamentals course."

> "Show me all enrollments for arun@infosys.com where status is in_progress."

---

## Testing

Run the integration test client to verify your setup against the live API:

```bash
# Basic connectivity and list tests
python3 servers/test_client.py

# Include a user lookup test
python3 servers/test_client.py --email someone@example.com
```

The test client exercises `get_conn`, `_get_all_groups`, `_get_all_courses`, `_find_user_by_email`,
`lu_lms_status`, `lu_list_groups`, `lu_list_courses`, and `lu_lookup_user`.

---

## Troubleshooting

**Tools not showing up:**
- Confirm both paths in `claude_desktop_config.json` are absolute and actually exist
- Validate the JSON: `python3 -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json`
- Check logs: `tail -f ~/Library/Logs/Claude/mcp*.log`
- Quit Claude Desktop completely (Cmd+Q), reopen, start a NEW conversation

**Auth errors:**
- Confirm `.env` is in the same directory as `run_server.py`
- Verify credentials in LearnUpon: Settings → Integrations → API
- Run `python3 servers/test_client.py` to diagnose connection issues directly

**Rate limiting (429 errors):**
- The server automatically retries with backoff (up to 3 attempts, respecting `Retry-After`)
- If you're hitting persistent rate limits, reduce the number of users in a single `lu_provision_users` call

---

## Invitation flow note

New users get an invitation email. Until they accept, they won't appear in user lookups
and can't be enrolled. Re-running provisioning after they accept completes enrollment
automatically — no duplicates.
