"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
Version Control Tools Mixin for mem20 MCP Server

Provides version control tools with multi-backend support:
- Git operations (clone, commit, push, pull, branch, merge, rebase)
- GitHub integration (issues, PRs, CI runs)
- GitLab integration
- SVN operations
- Code review tools
- Diff visualization
- Blame/annotate
- Tag management
- Stash operations
- Submodule management
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

import os
import sys
import json
import subprocess
import asyncio
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)


class VersionControlToolsMixin:
    """Version control tools for mem20."""

    def register_versioncontrol_tools(self):
        """Register all version control tools."""
        self.tools["vcs_git_status"] = mt.Tool(
            name="vcs_git_status",
            title="Git Status",
            description="Get git repository status",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                },
                "required": [],
            },
        )
        self.tools["vcs_git_log"] = mt.Tool(
            name="vcs_git_log",
            title="Git Log",
            description="View git commit history",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "limit": {"type": "integer", "default": 20},
                    "branch": {"type": "string", "default": ""},
                    "author": {"type": "string", "default": ""},
                    "since": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["vcs_git_diff"] = mt.Tool(
            name="vcs_git_diff",
            title="Git Diff",
            description="View git diff",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "commit1": {"type": "string", "default": ""},
                    "commit2": {"type": "string", "default": ""},
                    "staged": {"type": "boolean", "default": False},
                },
                "required": [],
            },
        )
        self.tools["vcs_git_commit"] = mt.Tool(
            name="vcs_git_commit",
            title="Git Commit",
            description="Stage and commit changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "message": {"type": "string"},
                    "files": {"type": "string", "description": "JSON array of files to stage", "default": "[]"},
                    "amend": {"type": "boolean", "default": False},
                },
                "required": ["message"],
            },
        )
        self.tools["vcs_git_branch"] = mt.Tool(
            name="vcs_git_branch",
            title="Git Branch",
            description="List, create, or delete branches",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "action": {"type": "string", "enum": ["list", "create", "delete", "checkout"], "default": "list"},
                    "branch_name": {"type": "string", "default": ""},
                    "base_branch": {"type": "string", "default": "main"},
                },
                "required": [],
            },
        )
        self.tools["vcs_git_remote"] = mt.Tool(
            name="vcs_git_remote",
            title="Git Remote",
            description="Push, pull, fetch operations",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "action": {"type": "string", "enum": ["push", "pull", "fetch"], "default": "fetch"},
                    "remote": {"type": "string", "default": "origin"},
                    "branch": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["vcs_git_stash"] = mt.Tool(
            name="vcs_git_stash",
            title="Git Stash",
            description="Stash operations",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "action": {"type": "string", "enum": ["push", "pop", "list", "apply"], "default": "list"},
                    "message": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["vcs_git_tag"] = mt.Tool(
            name="vcs_git_tag",
            title="Git Tag",
            description="Tag management",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "action": {"type": "string", "enum": ["list", "create", "delete"], "default": "list"},
                    "tag_name": {"type": "string", "default": ""},
                    "message": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["vcs_github_pr"] = mt.Tool(
            name="vcs_github_pr",
            title="GitHub PR",
            description="GitHub pull request operations",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "view", "create", "merge", "comment"], "default": "list"},
                    "repo": {"type": "string", "default": ""},
                    "pr_number": {"type": "integer", "default": 0},
                    "title": {"type": "string", "default": ""},
                    "body": {"type": "string", "default": ""},
                    "base": {"type": "string", "default": "main"},
                    "head": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["vcs_github_issue"] = mt.Tool(
            name="vcs_github_issue",
            title="GitHub Issue",
            description="GitHub issue operations",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "view", "create", "close", "comment"], "default": "list"},
                    "repo": {"type": "string", "default": ""},
                    "issue_number": {"type": "integer", "default": 0},
                    "title": {"type": "string", "default": ""},
                    "body": {"type": "string", "default": ""},
                    "labels": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["vcs_git_blame"] = mt.Tool(
            name="vcs_git_blame",
            title="Git Blame",
            description="View git blame for a file",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "file": {"type": "string"},
                    "line_from": {"type": "integer", "default": 0},
                    "line_to": {"type": "integer", "default": 0},
                },
                "required": ["file"],
            },
        )

    async def _vcs_git_status(self, args: Dict) -> str:
        path = args.get("path", ".")
        try:
    result = subprocess.run(
    ["git", "status", "--short", "--branch"],
    capture_output=True, text=True, timeout=15, cwd=path
    )
    if result.returncode == 0:
    return f"Git Status:\n{result.stdout}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_git_log(self, args: Dict) -> str:
    path = args.get("path", ".")
    limit = args.get("limit", 20)
    branch = args.get("branch", "")
    author = args.get("author", "")
    since = args.get("since", "")
        try:
    cmd = ["git", "log", f"--max-count={limit}", "--oneline", "--graph", "--decorate"]
    if branch:
    cmd.append(branch)
    if author:
    cmd.extend(["--author", author])
    if since:
    cmd.extend(["--since", since])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=path)
    if result.returncode == 0:
    return f"Git Log:\n{result.stdout}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_git_diff(self, args: Dict) -> str:
    path = args.get("path", ".")
    commit1 = args.get("commit1", "")
    commit2 = args.get("commit2", "")
    staged = args.get("staged", False)
        try:
    cmd = ["git", "diff"]
    if staged:
    cmd.append("--staged")
    if commit1 and commit2:
    cmd.extend([commit1, commit2])
    elif commit1:
    cmd.append(commit1)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=path)
    if result.returncode == 0:
    return f"Git Diff:\n{result.stdout[:5000]}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_git_commit(self, args: Dict) -> str:
    path = args.get("path", ".")
    message = args.get("message", "")
    files = json.loads(args.get("files", "[]"))
    amend = args.get("amend", False)
        try:
    Stage files
    if files:
    subprocess.run(["git", "add"] + files, capture_output=True, cwd=path)
    else:
    subprocess.run(["git", "add", "-A"], capture_output=True, cwd=path)
    Commit
    cmd = ["git", "commit", "-m", message]
    if amend:
    cmd.append("--amend")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=path)
    if result.returncode == 0:
    return f"Committed: {result.stdout}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_git_branch(self, args: Dict) -> str:
    path = args.get("path", ".")
    action = args.get("action", "list")
    branch_name = args.get("branch_name", "")
    base_branch = args.get("base_branch", "main")
        try:
    if action == "list":
    result = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True, timeout=15, cwd=path)
    return f"Branches:\n{result.stdout}"
    elif action == "create":
    result = subprocess.run(["git", "checkout", "-b", branch_name, base_branch], capture_output=True, text=True, timeout=15, cwd=path)
    return f"Branch created: {result.stdout}"
    elif action == "delete":
    result = subprocess.run(["git", "branch", "-d", branch_name], capture_output=True, text=True, timeout=15, cwd=path)
    return f"Branch deleted: {result.stdout}"
    elif action == "checkout":
    result = subprocess.run(["git", "checkout", branch_name], capture_output=True, text=True, timeout=15, cwd=path)
    return f"Checked out: {result.stdout}"
    else:
    return f"Unknown action: {action}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_git_remote(self, args: Dict) -> str:
    path = args.get("path", ".")
    action = args.get("action", "fetch")
    remote = args.get("remote", "origin")
    branch = args.get("branch", "")
        try:
    if action == "push":
    cmd = ["git", "push", remote]
    if branch:
    cmd.append(branch)
    elif action == "pull":
    cmd = ["git", "pull", remote]
    if branch:
    cmd.append(branch)
    elif action == "fetch":
    cmd = ["git", "fetch", remote]
    else:
    return f"Unknown action: {action}"
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=path)
    if result.returncode == 0:
    return f"{action.capitalize()}: {result.stdout}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_git_stash(self, args: Dict) -> str:
    path = args.get("path", ".")
    action = args.get("action", "list")
    message = args.get("message", "")
        try:
    if action == "push":
    cmd = ["git", "stash", "push"]
    if message:
    cmd.extend(["-m", message])
    elif action == "pop":
    cmd = ["git", "stash", "pop"]
    elif action == "list":
    cmd = ["git", "stash", "list"]
    elif action == "apply":
    cmd = ["git", "stash", "apply"]
    else:
    return f"Unknown action: {action}"
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=path)
    if result.returncode == 0:
    return f"Stash {action}: {result.stdout}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_git_tag(self, args: Dict) -> str:
    path = args.get("path", ".")
    action = args.get("action", "list")
    tag_name = args.get("tag_name", "")
    message = args.get("message", "")
        try:
    if action == "list":
    result = subprocess.run(["git", "tag"], capture_output=True, text=True, timeout=15, cwd=path)
    return f"Tags:\n{result.stdout}"
    elif action == "create":
    cmd = ["git", "tag"]
    if message:
    cmd.extend(["-a", tag_name, "-m", message])
    else:
    cmd.append(tag_name)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=path)
    return f"Tag created: {result.stdout}"
    elif action == "delete":
    result = subprocess.run(["git", "tag", "-d", tag_name], capture_output=True, text=True, timeout=15, cwd=path)
    return f"Tag deleted: {result.stdout}"
    else:
    return f"Unknown action: {action}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_github_pr(self, args: Dict) -> str:
    action = args.get("action", "list")
    repo = args.get("repo", "")
    pr_number = args.get("pr_number", 0)
    title = args.get("title", "")
    body = args.get("body", "")
    base = args.get("base", "main")
    head = args.get("head", "")
        try:
    gh_path = shutil.which("gh")
    if not gh_path:
    return "Error: GitHub CLI (gh) not found."
    if action == "list":
    cmd = [gh_path, "pr", "list"]
    if repo:
    cmd.extend(["--repo", repo])
    elif action == "view":
    cmd = [gh_path, "pr", "view", str(pr_number)]
    if repo:
    cmd.extend(["--repo", repo])
    elif action == "create":
    cmd = [gh_path, "pr", "create", "--title", title, "--body", body, "--base", base, "--head", head]
    if repo:
    cmd.extend(["--repo", repo])
    elif action == "merge":
    cmd = [gh_path, "pr", "merge", str(pr_number)]
    if repo:
    cmd.extend(["--repo", repo])
    elif action == "comment":
    cmd = [gh_path, "pr", "comment", str(pr_number), "--body", body]
    if repo:
    cmd.extend(["--repo", repo])
    else:
    return f"Unknown action: {action}"
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
    return f"PR {action}: {result.stdout}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_github_issue(self, args: Dict) -> str:
    action = args.get("action", "list")
    repo = args.get("repo", "")
    issue_number = args.get("issue_number", 0)
    title = args.get("title", "")
    body = args.get("body", "")
    labels = args.get("labels", "")
        try:
    gh_path = shutil.which("gh")
    if not gh_path:
    return "Error: GitHub CLI (gh) not found."
    if action == "list":
    cmd = [gh_path, "issue", "list"]
    if repo:
    cmd.extend(["--repo", repo])
    elif action == "view":
    cmd = [gh_path, "issue", "view", str(issue_number)]
    if repo:
    cmd.extend(["--repo", repo])
    elif action == "create":
    cmd = [gh_path, "issue", "create", "--title", title, "--body", body]
    if labels:
    cmd.extend(["--label", labels])
    if repo:
    cmd.extend(["--repo", repo])
    elif action == "close":
    cmd = [gh_path, "issue", "close", str(issue_number)]
    if repo:
    cmd.extend(["--repo", repo])
    elif action == "comment":
    cmd = [gh_path, "issue", "comment", str(issue_number), "--body", body]
    if repo:
    cmd.extend(["--repo", repo])
    else:
    return f"Unknown action: {action}"
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
    return f"Issue {action}: {result.stdout}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _vcs_git_blame(self, args: Dict) -> str:
    path = args.get("path", ".")
    file = args.get("file", "")
    line_from = args.get("line_from", 0)
    line_to = args.get("line_to", 0)
        try:
    cmd = ["git", "blame", file]
    if line_from and line_to:
    cmd.extend(["-L", f"{line_from},{line_to}"])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=path)
    if result.returncode == 0:
    return f"Git Blame:\n{result.stdout}"
    return f"Error: {result.stderr}"
    except Exception as e:
    return f"Error: {str(e)}"
