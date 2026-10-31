#!/usr/bin/env python3
"""Janus (formerly GATE-BOT). PreToolUse hook: refuse git commit or push while on main (CLAUDE.md: branch per item)."""
import json, re, subprocess, sys

try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

# look at command words only: drop heredoc bodies and quoted text (commit messages, file contents)
cmd = cmd.split("<<")[0]
cmd = re.sub(r"'[^']*'|\"[^\"]*\"", "''", cmd)

if not re.search(r"\bgit\b[^;&|\n]*\b(commit|push)\b", cmd):
    sys.exit(0)

branch = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
pushes_main = re.search(r"\bgit\b[^;&|]*\bpush\b[^;&|\n]*(?<![\w/.-])(main|master)(?![\w/.-])", cmd)

if branch in ("main", "master") or pushes_main:
    sys.stderr.write("Janus: blocked. PMT work goes on a branch named for the backlog item, not main. "
                     "Create one with git checkout -b <area>/<item>, then open a pull request.\n")
    sys.exit(2)
sys.exit(0)
