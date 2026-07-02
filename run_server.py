#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp[cli]>=1.0",
#   "requests>=2.31",
#   "python-dotenv>=1.0",
# ]
# ///
"""
LearnUpon MCP Server — Claude Desktop entry point.

Claude Desktop spawns this as a subprocess via claude_desktop_config.json.
Credentials are loaded from a .env file in the same directory as this script.

Setup:
  1. Copy .env.example to .env and fill in your credentials
  2. Add to claude_desktop_config.json (see README.md)
  3. Quit and reopen Claude Desktop — start a NEW conversation
"""

import os
import sys
from pathlib import Path

# Load .env from this file's directory (explicit path — Claude Desktop doesn't set cwd)
project_dir = Path(__file__).parent.resolve()
env_file = project_dir / ".env"

if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except ImportError:
        # dotenv not installed — fall back to manual parsing
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())
else:
    print(
        f"Warning: .env file not found at {env_file}. "
        "Copy .env.example to .env and add your credentials.",
        file=sys.stderr,
    )

# Ensure the server module is importable
sys.path.insert(0, str(project_dir))

from learnupon_server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
