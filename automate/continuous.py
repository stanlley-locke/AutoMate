"""Continuous and Overnight Execution Engine for AutoMate.

Orchestrates long-running, 24/7, and overnight autonomous desktop sessions
(e.g., unattended game grinding, web scraping, repetitive productivity tasks).
Includes system keep-awake, anti-stuck watchdog, error resilience, rate-limit backoff,
and memory garbage collection.
"""

from __future__ import annotations

import gc
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from automate.keep_awake import KeepAwake
from automate.logger import ActionLogger, get_logger
from automate.screen import ensure_windows_desktop_and_dpi

logger = get_logger("automate.continuous")
console = Console()


@dataclass
class ContinuousStats:
    """Telemetry and execution metrics for a long-running session."""

    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    total_cycles: int = 0
    actions_executed: int = 0
    errors_encountered: int = 0
    recoveries_performed: int = 0
    stuck_detections: int = 0
    last_action_timestamp: Optional[datetime] = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time or datetime.now()
        return max(0.0, (end - self.start_time).total_seconds())

    @property
    def elapsed_formatted(self) -> str:
        secs = int(self.elapsed_seconds)
        hours, remainder = divmod(secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"


class ContinuousRunner:
    """Manages 24/7 or overnight unattended operation of the AutoMate agent."""

    def __init__(
        self,
        agent: Any,
        task: str,
        duration_hours: float = 0.0,
        max_cycles: Optional[int] = None,
        loop_interval: float = 1.5,
        keep_awake: bool = True,
        anti_stuck_threshold: int = 5,
        gc_interval_cycles: int = 30,
        on_cycle_callback: Optional[Callable[[int, ContinuousStats], None]] = None,
    ) -> None:
        self.agent = agent
        self.task = task
        self.duration_hours = max(0.0, duration_hours)
        self.max_cycles = max_cycles if (max_cycles and max_cycles > 0) else None
        self.loop_interval = max(0.2, loop_interval)
        self.keep_awake_enabled = keep_awake
        self.anti_stuck_threshold = anti_stuck_threshold
        self.gc_interval_cycles = gc_interval_cycles
        self.on_cycle_callback = on_cycle_callback

        self.stats = ContinuousStats()
        self._stopped = False
        self._stuck_counter = 0
        self._last_screen_hash: Optional[int] = None
        self.keep_awake_mgr = KeepAwake(keep_display_on=True)

    def stop(self) -> None:
        """Signal the continuous runner to halt gracefully."""
        self._stopped = True
        logger.info("Continuous runner stop requested.")
        if hasattr(self.agent, "stop"):
            self.agent.stop()

    def _should_terminate(self) -> bool:
        """Check if time duration or cycle limit has been reached."""
        if self._stopped:
            return True

        if self.duration_hours > 0:
            elapsed_hrs = self.stats.elapsed_seconds / 3600.0
            if elapsed_hrs >= self.duration_hours:
                logger.info(
                    f"Target session duration reached ({self.duration_hours}h). "
                    "Terminating continuous run."
                )
                return True

        if self.max_cycles is not None:
            if self.stats.total_cycles >= self.max_cycles:
                logger.info(
                    f"Max cycle count ({self.max_cycles}) reached. "
                    "Terminating continuous run."
                )
                return True

        return False

    def _perform_anti_stuck_recovery(self) -> None:
        """Attempt recovery actions when agent appears frozen or stuck in a game/UI loop."""
        self.stats.stuck_detections += 1
        self.stats.recoveries_performed += 1
        logger.warning(
            f"Anti-stuck trigger: Screen unchanged for {self.anti_stuck_threshold} cycles. "
            "Executing recovery sequence (Esc -> refocus click -> pause)..."
        )
        try:
            # Step 1: Press escape or space to close dialogue/popups
            if hasattr(self.agent.controller, "press_key"):
                self.agent.controller.press_key("esc")
                time.sleep(0.5)

            # Step 2: Click center of screen to ensure active focus
            if hasattr(self.agent.screen, "get_screen_size") and hasattr(self.agent.controller, "click"):
                w, h = self.agent.screen.get_screen_size()
                self.agent.controller.click(w // 2, h // 2)
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error during anti-stuck recovery: {e}")

    def run(self) -> ContinuousStats:
        """Execute the continuous overnight / 24-7 automation loop."""
        ensure_windows_desktop_and_dpi()
        self.stats = ContinuousStats(start_time=datetime.now())
        self._stopped = False
        self._stuck_counter = 0

        target_desc = (
            f"{self.duration_hours:.1f} hours" if self.duration_hours > 0 else "Indefinite (24/7)"
        )

        console.print(
            Panel(
                f"[bold cyan]Task:[/bold cyan] {self.task}\n"
                f"[bold blue]Run Target:[/bold blue] {target_desc} | "
                f"[bold blue]Loop Delay:[/bold blue] {self.loop_interval}s\n"
                f"[bold blue]Keep-Awake:[/bold blue] [{'green' if self.keep_awake_enabled else 'dim'}]"
                f"{'ACTIVE (Sleep & Display-Off Prevented)' if self.keep_awake_enabled else 'Disabled'}[/]\n"
                "[dim]Press [yellow]Ctrl+C[/yellow] at any time to halt safely.[/dim]",
                title="🌙 AutoMate Overnight / Continuous Runner Started",
                border_style="magenta",
            )
        )

        # Engage Windows keep-awake if enabled
        if self.keep_awake_enabled:
            self.keep_awake_mgr.start()

        try:
            while not self._should_terminate():
                cycle_start = time.perf_counter()
                self.stats.total_cycles += 1
                cycle = self.stats.total_cycles

                # Periodic memory garbage collection
                if cycle % self.gc_interval_cycles == 0:
                    gc.collect()

                try:
                    # 1. Capture screen
                    screen_img = self.agent.screen.capture()
                    curr_hash = hash(screen_img.tobytes()[::100])  # Fast coarse hash

                    # Check for screen stagnation (anti-stuck)
                    if self._last_screen_hash is not None and curr_hash == self._last_screen_hash:
                        self._stuck_counter += 1
                        if self._stuck_counter >= self.anti_stuck_threshold:
                            self._perform_anti_stuck_recovery()
                            self._stuck_counter = 0
                    else:
                        self._stuck_counter = 0
                    self._last_screen_hash = curr_hash

                    # 2. Convert screenshot for provider
                    b64 = self.agent.screen.to_base64(screen_img)
                    raw_bytes = (
                        self.agent.screen.to_bytes(screen_img)
                        if hasattr(self.agent.screen, "to_bytes")
                        else screen_img.tobytes()
                    )

                    # 3. Decision step using configured provider
                    display_size = self.agent.screen.get_screen_size()
                    model_resp = self.agent.provider.decide_next_step(
                        task=self.task,
                        screenshot_bytes=raw_bytes,
                        screenshot_b64=b64,
                        display_size=display_size,
                        action_history=self.agent.action_history,
                        step_number=cycle,
                    )

                    if model_resp.error:
                        self.stats.errors_encountered += 1
                        logger.warning(
                            f"[Cycle {cycle}] Provider error: {model_resp.error}. "
                            "Backing off and resuming loop..."
                        )
                        time.sleep(min(15.0, self.loop_interval * 3))
                        continue

                    # Log thoughts if present
                    if model_resp.thought:
                        logger.info(f"[Cycle {cycle}] AI Thought: {model_resp.thought[:140]}...")

                    # 4. Execute returned actions
                    for act in model_resp.actions:
                        if self._stopped:
                            break
                        self.agent._execute_provider_action(act)
                        self.stats.actions_executed += 1
                        self.stats.last_action_timestamp = datetime.now()

                    # Check if model marked task complete (optional in continuous game mode)
                    if model_resp.is_finished:
                        logger.info(
                            f"[Cycle {cycle}] AI signaled task completion. "
                            "Continuing cycle monitoring for overnight/game task..."
                        )

                    # Trigger callback if registered
                    if self.on_cycle_callback:
                        self.on_cycle_callback(cycle, self.stats)

                    # Periodic console status log (every 10 cycles)
                    if cycle % 10 == 0:
                        logger.info(
                            f"Overnight Heartbeat: [Uptime: {self.stats.elapsed_formatted}] "
                            f"[Cycles: {cycle}] [Actions: {self.stats.actions_executed}] "
                            f"[Errors: {self.stats.errors_encountered}]"
                        )

                except KeyboardInterrupt:
                    raise
                except Exception as cycle_err:
                    self.stats.errors_encountered += 1
                    logger.error(f"[Cycle {cycle}] Unexpected error: {cycle_err}")
                    time.sleep(2.0)

                # Pacing interval
                cycle_duration = time.perf_counter() - cycle_start
                sleep_needed = max(0.1, self.loop_interval - cycle_duration)
                time.sleep(sleep_needed)

        except KeyboardInterrupt:
            console.print("\n[yellow]KeyboardInterrupt received. Stopping continuous runner...[/yellow]")
        finally:
            self.stats.end_time = datetime.now()
            if self.keep_awake_enabled:
                self.keep_awake_mgr.stop()
            self._print_final_summary()

        return self.stats

    def _print_final_summary(self) -> None:
        """Render session summary table."""
        table = Table(
            title="Continuous / Overnight Session Summary",
            header_style="bold magenta",
            border_style="cyan",
            show_lines=True,
        )
        table.add_column("Metric", style="bold cyan", width=26)
        table.add_column("Value", style="green")

        table.add_row("Total Uptime", self.stats.elapsed_formatted)
        table.add_row("Total Cycles Completed", str(self.stats.total_cycles))
        table.add_row("Actions Executed", str(self.stats.actions_executed))
        table.add_row("Errors Encountered", str(self.stats.errors_encountered))
        table.add_row("Anti-Stuck Recoveries", str(self.stats.recoveries_performed))
        table.add_row("Start Time", self.stats.start_time.strftime("%Y-%m-%d %H:%M:%S"))
        if self.stats.end_time:
            table.add_row("End Time", self.stats.end_time.strftime("%Y-%m-%d %H:%M:%S"))

        console.print()
        console.print(table)
        console.print()
