"""AutoMate Logging System.

Provides rich console logging and structured action tracking for replay and analysis.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DEFAULT_LOG_FILE = "automate_actions.log"

# Safeguard Windows console encoding if needed
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()


@dataclass
class ActionRecord:
    """Represents an individual action executed by the AutoMate agent."""

    step: int
    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert action record to dictionary representation."""
        return asdict(self)


class ActionLogger:
    """Tracks, records, displays, and exports agent actions."""

    def __init__(self, log_file: str | Path | None = None, auto_flush: bool = True) -> None:
        self.records: list[ActionRecord] = []
        self.log_file = Path(log_file) if log_file else None
        self.auto_flush = auto_flush
        self._logger = get_logger("automate.actions")

    def log_action(
        self,
        step: int,
        action_type: str,
        params: dict[str, Any] | None = None,
        success: bool = True,
        error: str | None = None,
        duration_ms: float = 0.0,
    ) -> ActionRecord:
        """Record an executed action."""
        record = ActionRecord(
            step=step,
            action_type=action_type,
            params=params or {},
            success=success,
            error=error,
            duration_ms=duration_ms,
        )
        self.records.append(record)

        param_str = ", ".join(f"{k}={v}" for k, v in (params or {}).items())
        status_str = "[green]SUCCESS[/green]" if success else f"[red]FAILED ({error})[/red]"
        self._logger.debug(
            f"Step {step} | {action_type.upper()} | {param_str} | {status_str} ({duration_ms:.1f}ms)"
        )

        if self.auto_flush and self.log_file:
            self.export_json(self.log_file)

        return record

    def get_history(self) -> list[ActionRecord]:
        """Return full action history."""
        return list(self.records)

    def clear(self) -> None:
        """Clear action history."""
        self.records.clear()

    def to_json(self) -> str:
        """Export action history as formatted JSON string."""
        data = [r.to_dict() for r in self.records]
        return json.dumps(data, indent=2)

    def export_json(self, path: str | Path) -> None:
        """Save action history to a JSON file for replay or telemetry."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_json(), encoding="utf-8")

    def build_summary_table(self, title: str = "Agent Execution Summary") -> Table:
        """Construct a Rich Table visualization of all executed actions."""
        table = Table(
            title=title,
            header_style="bold cyan",
            border_style="bright_blue",
            show_lines=True,
        )
        table.add_column("Step", justify="center", style="bold", width=6)
        table.add_column("Timestamp", style="dim", width=12)
        table.add_column("Action", style="bold magenta", width=14)
        table.add_column("Parameters", style="yellow")
        table.add_column("Status", justify="center", width=10)
        table.add_column("Time", justify="right", style="cyan", width=8)

        for rec in self.records:
            time_part = rec.timestamp.split(" ")[-1] if " " in rec.timestamp else rec.timestamp
            params_display = ", ".join(f"{k}={v}" for k, v in rec.params.items()) or "-"
            if rec.success:
                status_widget = Text("[OK] PASS", style="bold green")
            else:
                status_widget = Text(f"[X] FAIL ({rec.error or 'err'})", style="bold red")

            table.add_row(
                str(rec.step),
                time_part,
                rec.action_type.upper(),
                params_display,
                status_widget,
                f"{rec.duration_ms:.0f}ms",
            )
        return table

    def print_summary(self, target_console: Console | None = None) -> None:
        """Print rich summary table to console."""
        out = target_console or console
        if not self.records:
            out.print(Panel("[dim]No actions recorded.[/dim]", title="Action Log"))
            return
        out.print(self.build_summary_table())


_configured_loggers: dict[str, logging.Logger] = {}


def get_logger(
    name: str = "automate",
    level: str | int = "INFO",
    log_file: str | Path = DEFAULT_LOG_FILE,
) -> logging.Logger:
    """Get or create a configured Rich logger with dual console and file handlers.

    Args:
        name: Logger name
        level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        log_file: Path to append action log file
    """
    if name in _configured_loggers:
        return _configured_loggers[name]

    logger = logging.getLogger(name)

    if isinstance(level, str):
        level_val = getattr(logging, level.upper(), logging.INFO)
    else:
        level_val = level
    logger.setLevel(level_val)

    if not logger.handlers:
        logger.propagate = False

        rich_handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            show_time=True,
            show_path=False,
            markup=True,
        )
        rich_handler.setLevel(level_val)
        logger.addHandler(rich_handler)

        try:
            file_path = Path(log_file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(file_path, encoding="utf-8")
            file_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(level_val)
            logger.addHandler(file_handler)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not configure file logging: {e}[/yellow]")

    _configured_loggers[name] = logger
    return logger
