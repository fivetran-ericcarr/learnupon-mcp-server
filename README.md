# LearnUpon MCP Server

Integrates the LearnUpon LMS with Claude via MCP, giving you natural-language access to your
Partner Academy for provisioning, cert tracking, and group management.

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
| `lu_enrollment_status` | Check a user's course enrollments and completion status |
| `lu_course_progress` | Aggregate pass/completion stats for a course; per-user detail for a group |
| `lu_provision_users` | Bulk-invite users to a group and enroll in courses |

---

## Example prompts

> "List all groups in the Partner Academy."

> "Add these 12 Infosys contacts to the 'Infosys Sentara' group and enroll them in Fivetran Technical Foundations Certification."

> "Check if neha.kale@infosys.com has completed the Fivetran Technical Foundations cert."

> "How many people have passed the Fivetran Technical Foundations Certification?"

> "Show me completion status for the Capgemini group in the Fivetran Fundamentals course."

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
