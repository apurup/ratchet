"""
Natural Language Scheduler for Ratchet.

Parses natural language scheduling expressions and manages cron jobs
that deliver to any gateway platform.
"""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

_hermes_home = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
_SCHEDULER_DIR = _hermes_home / "scheduler"
_TASKS_FILE = _SCHEDULER_DIR / "tasks.json"


@dataclass
class ScheduledTask:
    """A task scheduled for periodic execution."""
    id: str
    task: str  # natural language task description
    schedule: str  # human-readable schedule
    cron_expression: str
    platform: str  # telegram, discord, cli, etc.
    enabled: bool = True
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    run_count: int = 0
    failure_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledTask":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class NaturalLanguageScheduler:
    """
    Parse natural language schedules and manage scheduled tasks.

    Examples:
        "every day at 9am" → cron: "0 9 * * *"
        "every monday at 10am" → cron: "0 10 * * 1"
        "every 30 minutes" → cron: "*/30 * * * *"
        "nightly backups" → recognized pattern → cron: "0 2 * * *"
    """

    # Day name to cron number (0=Sunday in cron)
    DAY_MAP = {
        "sunday": "0",
        "sun": "0",
        "monday": "1",
        "mon": "1",
        "tuesday": "2",
        "tue": "2",
        "wednesday": "3",
        "wed": "3",
        "thursday": "4",
        "thu": "4",
        "friday": "5",
        "fri": "5",
        "saturday": "6",
        "sat": "6",
    }

    CRON_PATTERNS = [
        # (regex, format_template, description)
        (
            r"^every day at (\d+)(am|pm)$",
            "0 {hour} * * *",
            "daily at hour",
        ),
        (
            r"^every day at (\d+):(\d+)\s*(am|pm)?$",
            "0 {hour}:{minute} * * *",
            "daily at hour:minute",
        ),
        (
            r"^every (\w+) at (\d+)(am|pm)$",
            "0 {hour} * * {day}",
            "weekly on day at hour",
        ),
        (
            r"^every (\w+) at (\d+):(\d+)\s*(am|pm)?$",
            "0 {hour}:{minute} * * {day}",
            "weekly on day at hour:minute",
        ),
        (
            r"^every (\d+) minutes?$",
            "*/{minutes} * * * *",
            "every N minutes",
        ),
        (
            r"^every hour(?:s)?$",
            "0 * * * *",
            "hourly",
        ),
        (
            r"^every (\d+) hours?$",
            "0 */{hours} * * *",
            "every N hours",
        ),
        (
            r"^nightly at (\d+)$",
            "0 {hour} * * *",
            "nightly at hour",
        ),
        (
            r"^nightly$",
            "0 2 * * *",
            "nightly at 2am",
        ),
        (
            r"^weekly$",
            "0 10 * * 1",
            "weekly monday at 10am",
        ),
        (
            r"^monthly$",
            "0 9 1 * *",
            "monthly on 1st at 9am",
        ),
    ]

    TASK_CATEGORIES = {
        "backup": ("nightly backups", "0 2 * * *"),
        "report": ("daily report", "0 9 * * *"),
        "audit": ("weekly audit", "0 10 * * 1"),
        "healthcheck": ("health check", "*/15 * * * *"),
        "sync": ("data sync", "0 */4 * * *"),
    }

    def __init__(self):
        _SCHEDULER_DIR.mkdir(parents=True, exist_ok=True)

    def parse(self, task: str, schedule: str, platform: str = "cli") -> ScheduledTask:
        """
        Parse a natural language schedule string.

        Args:
            task: Natural language task description
            schedule: Human-readable schedule string
            platform: Target platform for delivery

        Returns:
            ScheduledTask with parsed cron_expression
        """
        cron_expr = self.to_cron(schedule)
        task_id = self._generate_id(task, schedule)

        # Calculate next run time
        next_run = self._calculate_next_run(cron_expr)

        return ScheduledTask(
            id=task_id,
            task=task,
            schedule=schedule,
            cron_expression=cron_expr,
            platform=platform,
            enabled=True,
            next_run=next_run,
        )

    def to_cron(self, schedule: str) -> str:
        """
        Convert natural language to cron expression.

        Args:
            schedule: Human-readable schedule string

        Returns:
            Cron expression string
        """
        schedule_lower = schedule.lower().strip()

        # Check task categories first
        for category, (_, default_cron) in self.TASK_CATEGORIES.items():
            if category in schedule_lower:
                return default_cron

        # Try each pattern (most specific first)
        for regex, format_template, _ in self.CRON_PATTERNS:
            match = re.match(regex, schedule_lower, re.IGNORECASE)
            if not match:
                continue

            groups = match.groups()
            result = format_template

            # Pattern 1: "every day at Xam/pm" → groups: (hour_str, period)
            if regex.startswith("^every day at"):
                hour_str, period = groups[0], groups[1]
                hour = int(hour_str)
                if period == "pm" and hour != 12:
                    hour += 12
                elif period == "am" and hour == 12:
                    hour = 0
                hour = hour % 24
                result = result.replace("{hour}", str(hour))
                return result

            # Pattern 2: "every day at H:M am/pm" → groups: (hour_str, minute_str, period)
            if "every day at" in regex and ":" in regex:
                hour_str, minute_str, period = groups[0], groups[1], (groups[2] if len(groups) > 2 else "")
                hour = int(hour_str)
                if period == "pm" and hour != 12:
                    hour += 12
                elif period == "am" and hour == 12:
                    hour = 0
                hour = hour % 24
                result = result.replace("{hour}", str(hour))
                result = result.replace("{minute}", minute_str)
                return result

            # Pattern 3: "every WEEKDAY at Xam/pm" → groups: (day_name, hour_str, period)
            if "every (" in regex and "at (\d+)(am|pm)" in regex:
                day_str, hour_str, period = groups[0], groups[1], groups[2]
                hour = int(hour_str)
                if period == "pm" and hour != 12:
                    hour += 12
                elif period == "am" and hour == 12:
                    hour = 0
                hour = hour % 24
                result = result.replace("{hour}", str(hour))
                day_num = self.DAY_MAP.get(day_str.lower(), "0")
                result = result.replace("{day}", day_num)
                return result

            # Pattern 4: "every WEEKDAY at H:M am/pm" → groups: (day_name, hour_str, minute_str, period)
            if "every (" in regex and ":" in regex:
                day_str, hour_str, minute_str, period = groups[0], groups[1], groups[2], (groups[3] if len(groups) > 3 else "")
                hour = int(hour_str)
                if period == "pm" and hour != 12:
                    hour += 12
                elif period == "am" and hour == 12:
                    hour = 0
                hour = hour % 24
                result = result.replace("{hour}", str(hour))
                result = result.replace("{minute}", minute_str)
                day_num = self.DAY_MAP.get(day_str.lower(), "0")
                result = result.replace("{day}", day_num)
                return result

            # Pattern 5: "every N minutes" → groups: (N,)
            if "every (\d+) minutes" in regex:
                result = result.replace("{minutes}", groups[0])
                return result

            # Pattern 6: "every N hours" → groups: (N,)
            if "every (\d+) hours" in regex:
                result = result.replace("{hours}", groups[0])
                return result

            # Pattern 7: "nightly at X" → groups: (hour_str,)
            if regex.startswith("^nightly at"):
                hour_str = groups[0]
                hour = int(hour_str) % 24
                result = result.replace("{hour}", str(hour))
                return result

            # Pattern 8: fixed expressions (nightly, weekly, monthly, hourly)
            if regex in ("^nightly$", "^weekly$", "^monthly$", "^every hour"):
                return result

            return result

        # No match — return as-is if it looks like a cron expression
        if re.match(r"^[\d\*\/\-, ]+$", schedule_lower):
            return schedule_lower

        # Default to daily at 9am
        return "0 9 * * *"

    def _generate_id(self, task: str, schedule: str) -> str:
        """Generate a stable ID for a task+schedule combination."""
        data = f"{task}:{schedule}".encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def _calculate_next_run(self, cron_expr: str) -> Optional[float]:
        """
        Calculate the next run timestamp for a cron expression.

        Uses croniter for accurate scheduling. Falls back to heuristic
        estimation if croniter is not available.
        """
        try:
            from croniter import croniter
            now = time.time()
            cron = croniter(cron_expr, now)
            return cron.get_next()
        except ImportError:
            # Fallback: rough estimation based on cron expression
            return self._estimate_next_run(cron_expr)

    def _estimate_next_run(self, cron_expr: str) -> Optional[float]:
        """Heuristic next-run estimation when croniter is unavailable."""
        parts = cron_expr.split()
        if len(parts) != 5:
            return None

        minute, hour = parts[0], parts[1]
        now = time.localtime()
        base = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
        target_seconds = int(minute) * 60 + int(hour) * 3600 if minute.isdigit() and hour.isdigit() else 32400  # default 9am

        if target_seconds > base:
            return time.time() + (target_seconds - base)
        return time.time() + (86400 - base + target_seconds)

    def save_task(self, task: ScheduledTask) -> None:
        """Persist a scheduled task to disk."""
        tasks = self._load_all()
        tasks[task.id] = task.to_dict()
        _SCHEDULER_DIR.mkdir(parents=True, exist_ok=True)
        with open(_TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, default=str)

    def _load_all(self) -> Dict[str, Dict[str, Any]]:
        """Load all tasks from disk."""
        if not _TASKS_FILE.exists():
            return {}
        try:
            with open(_TASKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def list_tasks(self, platform: str = None) -> List[ScheduledTask]:
        """
        List all scheduled tasks, optionally filtered by platform.

        Args:
            platform: If provided, only return tasks for this platform

        Returns:
            List of ScheduledTask objects
        """
        tasks_data = self._load_all()
        tasks = [ScheduledTask.from_dict(d) for d in tasks_data.values()]
        if platform:
            tasks = [t for t in tasks if t.platform == platform]
        return sorted(tasks, key=lambda t: t.next_run or 0)

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a specific task by ID."""
        tasks = self._load_all()
        data = tasks.get(task_id)
        return ScheduledTask.from_dict(data) if data else None

    def delete_task(self, task_id: str) -> bool:
        """Delete a scheduled task."""
        tasks = self._load_all()
        if task_id not in tasks:
            return False
        del tasks[task_id]
        with open(_TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, default=str)
        return True

    def set_enabled(self, task_id: str, enabled: bool) -> bool:
        """Enable or disable a scheduled task."""
        task = self.get_task(task_id)
        if not task:
            return False
        task.enabled = enabled
        self.save_task(task)
        return True

    def update_last_run(self, task_id: str, success: bool) -> None:
        """Update last_run timestamp and stats after a task executes."""
        task = self.get_task(task_id)
        if not task:
            return
        task.last_run = time.time()
        task.run_count += 1
        if not success:
            task.failure_count += 1
        # Recalculate next_run
        task.next_run = self._calculate_next_run(task.cron_expression)
        self.save_task(task)

    def get_due_tasks(self) -> List[ScheduledTask]:
        """Return all enabled tasks that are currently due."""
        now = time.time()
        all_tasks = self.list_tasks(platform=None)
        return [
            t for t in all_tasks
            if t.enabled and t.next_run is not None and t.next_run <= now
        ]
