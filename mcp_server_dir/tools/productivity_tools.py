"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
Productivity Tools Mixin for mem20 MCP Server

Provides productivity tools:
- Task/todo management
- Calendar operations
- Note-taking
- Time tracking
- Pomodoro timer
- Habit tracking
- Goal setting
- Project management
- Meeting notes
- Document templates
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

# try:
    # from mcp.server import Server
    # from mcp.server.lowlevel.server import ServerRequestContext
    # import mcp_types as mt
# except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    # sys.exit(1)


class ProductivityToolsMixin:
    """Productivity tools for mem20."""

    def register_productivity_tools(self):
        """Register all productivity tools."""
        self.tools["prod_task_create"] = mt.Tool(
            name="prod_task_create",
            title="Create Task",
            description="Create a new task or todo item",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "description": {"type": "string", "description": "Task description", "default": ""},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "default": "medium"},
                    "due_date": {"type": "string", "description": "Due date (ISO format)", "default": ""},
                    "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
                },
                "required": ["title"],
            },
        )
        self.tools["prod_task_list"] = mt.Tool(
            name="prod_task_list",
            title="List Tasks",
            description="List all tasks with optional filters",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["all", "pending", "completed", "overdue"], "default": "all"},
                    "priority": {"type": "string", "enum": ["all", "low", "medium", "high", "urgent"], "default": "all"},
                    "tag": {"type": "string", "description": "Filter by tag", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["prod_task_update"] = mt.Tool(
            name="prod_task_update",
            title="Update Task",
            description="Update an existing task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID to update"},
                    "status": {"type": "string", "enum": ["pending", "completed", "cancelled"], "default": ""},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "default": ""},
                    "title": {"type": "string", "description": "New title", "default": ""},
                },
                "required": ["task_id"],
            },
        )
        self.tools["prod_note_create"] = mt.Tool(
            name="prod_note_create",
            title="Create Note",
            description="Create a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Note title"},
                    "content": {"type": "string", "description": "Note content"},
                    "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
                },
                "required": ["title", "content"],
            },
        )
        self.tools["prod_note_search"] = mt.Tool(
            name="prod_note_search",
            title="Search Notes",
            description="Search notes by content or tags",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "tag": {"type": "string", "description": "Filter by tag", "default": ""},
                },
                "required": ["query"],
            },
        )
        self.tools["prod_time_track"] = mt.Tool(
            name="prod_time_track",
            title="Track Time",
            description="Track time spent on a task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task name"},
                    "action": {"type": "string", "enum": ["start", "stop", "log"], "default": "start"},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes (for log action)", "default": 0},
                },
                "required": ["task", "action"],
            },
        )
        self.tools["prod_habit_track"] = mt.Tool(
            name="prod_habit_track",
            title="Track Habit",
            description="Track a daily habit",
            inputSchema={
                "type": "object",
                "properties": {
                    "habit": {"type": "string", "description": "Habit name"},
                    "completed": {"type": "boolean", "description": "Whether completed today", "default": True},
                },
                "required": ["habit"],
            },
        )
        self.tools["prod_goal_set"] = mt.Tool(
            name="prod_goal_set",
            title="Set Goal",
            description="Set a new goal",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Goal title"},
                    "description": {"type": "string", "description": "Goal description", "default": ""},
                    "target_date": {"type": "string", "description": "Target date (ISO format)", "default": ""},
                    "milestones": {"type": "string", "description": "Comma-separated milestones", "default": ""},
                },
                "required": ["title"],
            },
        )
        self.tools["prod_meeting_notes"] = mt.Tool(
            name="prod_meeting_notes",
            title="Meeting Notes",
            description="Create structured meeting notes",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Meeting title"},
                    "attendees": {"type": "string", "description": "Comma-separated attendees", "default": ""},
                    "agenda": {"type": "string", "description": "Meeting agenda", "default": ""},
                    "notes": {"type": "string", "description": "Meeting notes", "default": ""},
                    "action_items": {"type": "string", "description": "Action items", "default": ""},
                },
                "required": ["title"],
            },
        )
        self.tools["prod_project_create"] = mt.Tool(
            name="prod_project_create",
            title="Create Project",
            description="Create a new project",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Project name"},
                    "description": {"type": "string", "description": "Project description", "default": ""},
                    "start_date": {"type": "string", "description": "Start date (ISO format)", "default": ""},
                    "end_date": {"type": "string", "description": "End date (ISO format)", "default": ""},
                },
                "required": ["name"],
            },
        )

    def _get_productivity_store(self) -> Path:
        """Get the productivity data store path."""
        store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
        prod_path = store_path / "productivity"
        prod_path.mkdir(parents=True, exist_ok=True)
        return prod_path

    def _load_data(self, filename: str) -> List[Dict]:
        """Load JSON data file."""
        store = self._get_productivity_store()
        filepath = store / filename
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return []

    def _save_data(self, filename: str, data: List[Dict]):
        """Save JSON data file."""
        store = self._get_productivity_store()
        filepath = store / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    async def _prod_task_create(self, args: Dict) -> str:
        title = args.get("title", "")
        tasks = self._load_data("tasks.json")
        task = {
            "id": f"task-{int(time.time())}",
            "title": title,
            "description": args.get("description", ""),
            "priority": args.get("priority", "medium"),
            "status": "pending",
            "due_date": args.get("due_date", ""),
            "tags": [t.strip() for t in args.get("tags", "").split(",") if t.strip()],
            "created_at": datetime.now().isoformat(),
        }
        tasks.append(task)
        self._save_data("tasks.json", tasks)
        return f"Task created: {task['id']} - {title}"

    async def _prod_task_list(self, args: Dict) -> str:
        tasks = self._load_data("tasks.json")
        status_filter = args.get("status", "all")
        priority_filter = args.get("priority", "all")
        tag_filter = args.get("tag", "")
        filtered = []
        for t in tasks:
            if status_filter != "all" and t.get("status") != status_filter:
                continue
            if priority_filter != "all" and t.get("priority") != priority_filter:
                continue
            if tag_filter and tag_filter not in t.get("tags", []):
                continue
            filtered.append(t)
        if not filtered:
            return "No tasks found."
        output = f"Tasks ({len(filtered)}):\n"
        for t in filtered:
            output += f"  [{t['status']}] {t['id']}: {t['title']} (priority: {t['priority']})\n"
        return output

    async def _prod_task_update(self, args: Dict) -> str:
        task_id = args.get("task_id", "")
        tasks = self._load_data("tasks.json")
        for t in tasks:
            if t["id"] == task_id:
                if args.get("status"):
                    t["status"] = args["status"]
                if args.get("priority"):
                    t["priority"] = args["priority"]
                if args.get("title"):
                    t["title"] = args["title"]
                self._save_data("tasks.json", tasks)
                return f"Task updated: {task_id}"
        return f"Task not found: {task_id}"

    async def _prod_note_create(self, args: Dict) -> str:
        title = args.get("title", "")
        content = args.get("content", "")
        notes = self._load_data("notes.json")
        note = {
            "id": f"note-{int(time.time())}",
            "title": title,
            "content": content,
            "tags": [t.strip() for t in args.get("tags", "").split(",") if t.strip()],
            "created_at": datetime.now().isoformat(),
        }
        notes.append(note)
        self._save_data("notes.json", notes)
        return f"Note created: {note['id']} - {title}"

    async def _prod_note_search(self, args: Dict) -> str:
        query = args.get("query", "").lower()
        tag_filter = args.get("tag", "")
        notes = self._load_data("notes.json")
        results = []
        for n in notes:
            if query in n.get("title", "").lower() or query in n.get("content", "").lower():
                if tag_filter and tag_filter not in n.get("tags", []):
                    continue
                results.append(n)
        if not results:
            return "No notes found."
        output = f"Notes ({len(results)}):\n"
        for n in results:
            output += f"  {n['id']}: {n['title']}\n"
        return output

    async def _prod_time_track(self, args: Dict) -> str:
        task = args.get("task", "")
        action = args.get("action", "start")
        entries = self._load_data("time_entries.json")
        if action == "start":
            entry = {
                "id": f"time-{int(time.time())}",
                "task": task,
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "duration_minutes": 0,
            }
            entries.append(entry)
            self._save_data("time_entries.json", entries)
            return f"Time tracking started for: {task}"
        elif action == "stop":
            for e in reversed(entries):
                if e["task"] == task and e["end_time"] is None:
                    e["end_time"] = datetime.now().isoformat()
                    start = datetime.fromisoformat(e["start_time"])
                    end = datetime.fromisoformat(e["end_time"])
                    e["duration_minutes"] = int((end - start).total_seconds() / 60)
                    self._save_data("time_entries.json", entries)
                    return f"Time tracking stopped for: {task} ({e['duration_minutes']} min)"
            return f"No active time tracking found for: {task}"
        elif action == "log":
            duration = args.get("duration_minutes", 0)
            entry = {
                "id": f"time-{int(time.time())}",
                "task": task,
                "start_time": datetime.now().isoformat(),
                "end_time": datetime.now().isoformat(),
                "duration_minutes": duration,
            }
            entries.append(entry)
            self._save_data("time_entries.json", entries)
            return f"Time logged for: {task} ({duration} min)"

    async def _prod_habit_track(self, args: Dict) -> str:
        habit = args.get("habit", "")
        completed = args.get("completed", True)
        habits = self._load_data("habits.json")
        today = datetime.now().strftime("%Y-%m-%d")
        existing = next((h for h in habits if h["name"] == habit), None)
        if not existing:
            existing = {"name": habit, "history": []}
            habits.append(existing)
        if completed:
            if today not in existing["history"]:
                existing["history"].append(today)
        else:
            if today in existing["history"]:
                existing["history"].remove(today)
        self._save_data("habits.json", habits)
        status = "completed" if completed else "not completed"
        return f"Habit '{habit}' marked as {status} for today"

    async def _prod_goal_set(self, args: Dict) -> str:
        title = args.get("title", "")
        goals = self._load_data("goals.json")
        goal = {
            "id": f"goal-{int(time.time())}",
            "title": title,
            "description": args.get("description", ""),
            "target_date": args.get("target_date", ""),
            "milestones": [m.strip() for m in args.get("milestones", "").split(",") if m.strip()],
            "status": "active",
            "created_at": datetime.now().isoformat(),
        }
        goals.append(goal)
        self._save_data("goals.json", goals)
        return f"Goal set: {goal['id']} - {title}"

    async def _prod_meeting_notes(self, args: Dict) -> str:
        title = args.get("title", "")
        notes = self._load_data("meeting_notes.json")
        note = {
            "id": f"meeting-{int(time.time())}",
            "title": title,
            "attendees": [a.strip() for a in args.get("attendees", "").split(",") if a.strip()],
            "agenda": args.get("agenda", ""),
            "notes": args.get("notes", ""),
            "action_items": [a.strip() for a in args.get("action_items", "").split(",") if a.strip()],
            "created_at": datetime.now().isoformat(),
        }
        notes.append(note)
        self._save_data("meeting_notes.json", notes)
        return f"Meeting notes created: {note['id']} - {title}"

    async def _prod_project_create(self, args: Dict) -> str:
        name = args.get("name", "")
        projects = self._load_data("projects.json")
        project = {
            "id": f"project-{int(time.time())}",
            "name": name,
            "description": args.get("description", ""),
            "start_date": args.get("start_date", ""),
            "end_date": args.get("end_date", ""),
            "status": "active",
            "created_at": datetime.now().isoformat(),
        }
        projects.append(project)
        self._save_data("projects.json", projects)
        return f"Project created: {project['id']} - {name}"
