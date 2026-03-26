---
name: learnupon
description: >-
  Use this skill when the user wants to do anything in LearnUpon / the Fivetran
  Partner Academy — provisioning users, checking cert or enrollment status,
  managing groups, or reviewing course completion rates. Triggers on: "add these
  users to LearnUpon," "invite these partners to the Partner Academy," "enroll
  this list in the course," "check if someone is certified," "how many people
  passed the course," "what groups exist," "provision these people," "set up a
  new group," or any request involving a list of people and the LMS.
version: 2.0.0
---

# LearnUpon Skill

Use the `learnupon` MCP tools to interact with the Fivetran Partner Academy LMS.
The MCP server handles all API communication — no scripts or config files needed.

If the tools return a connection error, the MCP server may not be configured.
Direct the user to `README.md` in the server files for setup instructions.

## Tools at a Glance

| Tool | When to Use |
|------|-------------|
| `lu_list_groups` | User asks what groups exist, or to verify a group name before provisioning |
| `lu_list_courses` | User asks what courses are available, or to confirm a course name |
| `lu_lookup_user` | Check whether a specific person is registered and their account status |
| `lu_enrollment_status` | Check which courses a user is enrolled in and their completion/cert status |
| `lu_course_progress` | Get pass/completion stats for a course; per-user detail for a specific group |
| `lu_provision_users` | Invite a list of users to a group and enroll in courses |

---

## Workflow: Provision a batch of users

**Step 1 — Gather inputs.** Ask for or confirm:
- User list (pasted names/emails, or uploaded CSV)
- Group name (created automatically if it doesn't exist)
- Course name(s) — if unsure, call `lu_list_courses` first to confirm exact names
- Dry run? (offer this for large batches)

**Step 2 — Resolve course names.** If the user provides an approximate course name,
call `lu_list_courses` to find the exact name before proceeding.

**Step 3 — Format users as JSON.** Convert the input into a JSON array string:

```json
[
  {"full_name": "Arun Kumar Mehta", "email": "arun.mehta@infosys.com"},
  {"first_name": "Neha", "last_name": "Kale", "email": "neha.kale@infosys.com"},
  {"full_name": "Sathishkrishnaan K", "email": "sathishkrishnaan.k@infosys.com"}
]
```

Name splitting rule: first two words = `first_name`, everything after = `last_name`.
`"Sathishkrishnaan K"` → first: `"Sathishkrishnaan K"`, last: `""`

**Step 4 — Call `lu_provision_users`:**

```
users_json       = <JSON array string from Step 3>
group_name       = "Infosys Sentara"
course_names_json = '["Fivetran Technical Foundations Certification"]'
dry_run          = false  (or true if requested)
```

**Step 5 — Present results as a table:**

| User | Email | Invite | Enrollment |
|------|-------|--------|------------|
| Arun Kumar Mehta | arun@infosys.com | ✅ Invited | ✅ Enrolled |
| Neha Kale | neha@infosys.com | ⚠️ Already in group | ✅ Enrolled |
| Rithik R | r.rithik@infosys.com | ✅ Invited | ⏳ Pending invite |

Map result statuses to display labels:
- `invited` → ✅ Invited to group
- `already_in_group` → ⚠️ Already in group
- `enrolled` → ✅ Enrolled
- `already_enrolled` → ⚠️ Already enrolled
- `pending_invite` → ⏳ Pending — re-run after they accept their invite email
- `error` → ❌ Failed: [message]

If `unresolved_courses` is non-empty, show the user the `available_courses` list
and ask them to confirm the correct name.

---

## Workflow: Check cert / enrollment status

- **Single user, all courses:** `lu_enrollment_status(email=...)`
- **Single user, specific course:** `lu_enrollment_status(email=..., course_name=...)`
- **Course aggregate stats:** `lu_course_progress(course_name=...)`
- **Course stats for a group:** `lu_course_progress(course_name=..., group_name=...)`

---

## Workflow: Discovery

- **"What groups do we have?"** → `lu_list_groups()`
- **"What courses are available?"** → `lu_list_courses()`
- **"Is [person] registered?"** → `lu_lookup_user(email=...)`

---

## Key behaviors

- **Pending invites:** New users receive an invitation email. Until they accept, they won't
  appear in user lookups and can't be enrolled. The `pending_invite` status is expected for
  new users — re-running provisioning after they accept will complete enrollment automatically.

- **Idempotent re-runs:** Running the provisioner again for already-invited users is safe.
  They'll be marked `already_in_group` / `already_enrolled`, not duplicated.

- **Group auto-creation:** If the specified group doesn't exist, `lu_provision_users` creates
  it automatically and notes `group_created: true` in the result.

- **Exact course names required:** The course name match is case-insensitive but must be
  otherwise exact. Always use `lu_list_courses` to confirm the name if there's any doubt.
