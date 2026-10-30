"""The PreToolUse hook that keeps commits and pushes off main (.claude/hooks/block-main.py)."""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "block-main.py"


def run(command, cwd):
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, cwd=cwd).returncode


def repo(tmp_path, branch):
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=tmp_path, check=True)
    return tmp_path


def test_commit_on_main_is_blocked(tmp_path):
    assert run("git commit -m x", repo(tmp_path, "main")) == 2


def test_commit_on_item_branch_is_allowed(tmp_path):
    assert run("git commit -m x", repo(tmp_path, "cost/b-04-ledger-pivot")) == 0


def test_push_to_main_from_a_branch_is_blocked(tmp_path):
    cwd = repo(tmp_path, "cost/b-04")
    assert run("git push origin HEAD:main", cwd) == 2
    assert run("git push origin main", cwd) == 2


def test_branch_names_containing_main_are_allowed(tmp_path):
    cwd = repo(tmp_path, "tooling/main-guard")
    assert run("git push -u origin tooling/main-guard", cwd) == 0
    assert run("git push -u origin cost/main-menu", cwd) == 0


def test_words_inside_messages_and_heredocs_are_ignored(tmp_path):
    cwd = repo(tmp_path, "cost/b-04")
    assert run('git commit -m "stop pushing to main"', cwd) == 0
    assert run("git commit -F - <<'E'\nnever git push origin main\nE", cwd) == 0


def test_other_commands_are_allowed_on_main(tmp_path):
    cwd = repo(tmp_path, "main")
    assert run("git status", cwd) == 0
    assert run("git log --oneline", cwd) == 0
    assert run("ls", cwd) == 0
