"""
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
import mcp_types as mt


import os
import sys
import json
import subprocess
import asyncio
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional



class VersionControlToolsMixin:
    """Version control tools for mem20."""

    def register_versioncontrol_tools(self):
        """Register all version control tools."""
        self.tools["vcs_git_status"] = mt.Tool(
            name="vcs_git_status",
            title="Git Status",
            description="Get git repository status",
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
            input_schema={
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
