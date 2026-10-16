"""AutoMate CLI - Command-Line Interface for Windows Desktop Automation.

Provides commands to run autonomous tasks, launch interactive REPL sessions,
capture screen diagnostics, and inspect system configuration.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

# Safeguard Windows console encoding if needed
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from automate.agent import AutoMateAgent
from automate.logger import get_logger

try:
    from automate.config import Config, get_config
except ImportError:
    Config = None  # type: ignore
    get_config = None  # type: ignore

try:
    from automate.screen import ScreenCapture
except ImportError:
    ScreenCapture = None  # type: ignore


console = Console()

ASCII_BANNER = r"""
 [bold cyan]    ___         __        __  ___      __       [/bold cyan]
 [bold cyan]   /   | __  __/ /_____  /  |/  /___ _/ /____   [/bold cyan]
 [bold blue]  / /| |/ / / / __/ __ \/ /|_/ / __ `/ __/ _ \  [/bold blue]
 [bold blue] / ___ / /_/ / /_/ /_/ / /  / / /_/ / /_/  __/  [/bold blue]
 [bold magenta]/_/  |_|\__,_/\__/\____/_/  /_/\__,_/\__/\___/   [/bold magenta]
"""


def show_banner() -> None:
    """Print the stylish AutoMate banner."""
    console.print(ASCII_BANNER)
    console.print(
        Panel(
            "[bold white]AutoMate[/bold white] [dim]|[/dim] "
            "[cyan]Windows Desktop Automation Agent[/cyan] [dim]|[/dim] "
            "[magenta]Powered by Cloudflare Workers AI & Claude[/magenta]",
            border_style="bright_blue",
            expand=False,
        )
    )
    console.print()


def get_effective_config(
    provider: str | None = None,
    cf_account_id: str | None = None,
    cf_token: str | None = None,
    cf_model: str | None = None,
    model: str | None = None,
    max_steps: int | None = None,
    api_key: str | None = None,
    delay: float | None = None,
    duration_hours: float | None = None,
    keep_awake: bool | None = None,
    loop_interval: float | None = None,
    safety_mode: bool | None = None,
    verbose: bool = False,
) -> Any:
    """Retrieve configuration merged with CLI flag overrides."""
    if get_config is not None:
        cfg = get_config()
    else:
        # Fallback config container
        class SimpleConfig:
            provider = "cloudflare"
            cloudflare_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
            cloudflare_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
            cloudflare_model = "@cf/meta/llama-3.2-11b-vision-instruct"
            anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            model = "claude-sonnet-4-20250514"
            screenshot_interval = 1.0
            max_steps = 50
            safety_mode = True
            display_width = 1920
            display_height = 1080
            action_delay = 0.5
            duration_hours = 0.0
            keep_awake = True
            loop_interval = 1.5
            anti_stuck_threshold = 5
            log_level = "INFO"

        cfg = SimpleConfig()

    # Apply overrides
    if provider:
        cfg.provider = provider.lower()
    if cf_account_id:
        cfg.cloudflare_account_id = cf_account_id
    if cf_token:
        cfg.cloudflare_api_token = cf_token
    if cf_model:
        cfg.cloudflare_model = cf_model
    if model:
        cfg.model = model
    if max_steps:
        cfg.max_steps = max_steps
    if api_key is not None:
        cfg.anthropic_api_key = api_key
    if delay is not None:
        cfg.action_delay = delay
    if duration_hours is not None:
        cfg.duration_hours = duration_hours
    if keep_awake is not None:
        cfg.keep_awake = keep_awake
    if loop_interval is not None:
        cfg.loop_interval = loop_interval
    if safety_mode is not None:
        cfg.safety_mode = safety_mode
    if verbose:
        cfg.log_level = "DEBUG"

    return cfg


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="automate")
@click.pass_context
def automate(ctx: click.Context) -> None:
    """AutoMate - Autonomous AI agent controlling Windows desktop via Cloudflare or Claude."""
    if ctx.invoked_subcommand is None:
        from automate.ui import launch_ui
        launch_ui()


@automate.command()
def ui() -> None:
    """Launch the modern AutoMate Windows Desktop Graphical User Interface."""
    from automate.ui import launch_ui
    launch_ui()


@automate.command()
@click.argument("task")
@click.option("--provider", "-p", default=None, type=click.Choice(["cloudflare", "anthropic"], case_sensitive=False), help="AI vision reasoning backend.")
@click.option("--repeat", "-r", default=1, type=int, help="Number of times to repeat the task or recipe (e.g. -r 3).")
@click.option("--duration", "-d", default=0.0, type=float, help="Duration in minutes to run task repeatedly.")
@click.option("--hours", default=0.0, type=float, help="Hours to run continuously/overnight (0 = unlimited / 24/7).")
@click.option("--watch-mins", default=None, type=float, help="Minutes to watch/stream YouTube video (default 2 to 3 mins).")
@click.option("--fast", "--quick", is_flag=True, help="Fast execution mode with abbreviated pauses.")
@click.option("--continuous", "--overnight", is_flag=True, help="Run in continuous/overnight mode.")
@click.option("--loop-interval", default=None, type=float, help="Seconds between perception cycles in continuous mode.")
@click.option("--keep-awake/--no-keep-awake", default=True, help="Prevent Windows sleep and display shutoff.")
@click.option("--max-steps", default=50, type=int, help="Maximum execution steps for discrete tasks.")
@click.option("--model", default=None, type=str, help="Model identifier override.")
@click.option("--api-key", default=None, type=str, help="Anthropic API Key override.")
@click.option("--cf-account-id", default=None, type=str, help="Cloudflare Account ID override.")
@click.option("--cf-token", default=None, type=str, help="Cloudflare API Token override.")
@click.option("--cf-model", default=None, type=str, help="Cloudflare Workers AI vision model override.")
@click.option("--delay", default=None, type=float, help="Delay in seconds between automated actions.")
@click.option("--no-safety", is_flag=True, help="Disable safety boundaries and confirmations.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose debug output.")
def run(
    task: str,
    provider: str | None,
    repeat: int,
    duration: float,
    hours: float,
    watch_mins: float | None,
    fast: bool,
    continuous: bool,
    loop_interval: float | None,
    keep_awake: bool,
    max_steps: int,
    model: str | None,
    api_key: str | None,
    cf_account_id: str | None,
    cf_token: str | None,
    cf_model: str | None,
    delay: float | None,
    no_safety: bool,
    verbose: bool,
) -> None:
    """Run a desktop automation task autonomously."""
    show_banner()

    if fast:
        os.environ["AUTOMATE_FAST_MODE"] = "1"
    if watch_mins is not None:
        os.environ["AUTOMATE_WATCH_MINS"] = str(watch_mins)

    log_level = "DEBUG" if verbose else "INFO"
    get_logger("automate", level=log_level)

    safety = not no_safety
    cfg = get_effective_config(
        provider=provider,
        cf_account_id=cf_account_id,
        cf_token=cf_token,
        cf_model=cf_model,
        model=model,
        max_steps=max_steps,
        api_key=api_key,
        delay=delay,
        duration_hours=hours,
        keep_awake=keep_awake,
        loop_interval=loop_interval,
        safety_mode=safety,
        verbose=verbose,
    )

    # Validate credential based on active provider
    if provider:
        chosen_provider = provider.lower()
    elif api_key is not None:
        chosen_provider = "anthropic"
    elif cf_token is not None or cf_account_id is not None:
        chosen_provider = "cloudflare"
    elif getattr(cfg, "cloudflare_api_token", ""):
        chosen_provider = "cloudflare"
    elif getattr(cfg, "anthropic_api_key", ""):
        chosen_provider = "anthropic"
    else:
        chosen_prov = getattr(cfg, "provider", "auto").lower()
        chosen_provider = "cloudflare" if chosen_prov == "cloudflare" else "anthropic"

    cfg.provider = chosen_provider

    if chosen_provider == "cloudflare":
        if not getattr(cfg, "cloudflare_api_token", ""):
            console.print(
                Panel(
                    "[bold red]Error: Cloudflare AI Token not found![/bold red]\n\n"
                    "Please configure [yellow]CLOUDFLARE_API_TOKEN[/yellow] and [yellow]CLOUDFLARE_ACCOUNT_ID[/yellow] "
                    "in your environment, in a [yellow].env[/yellow] file, or pass [yellow]--cf-token YOUR_TOKEN[/yellow].\n\n"
                    "[dim]Alternatively, pass [yellow]--provider anthropic --api-key YOUR_KEY[/yellow] to use Claude.[/dim]",
                    title="Configuration Missing",
                    border_style="red",
                )
            )
            sys.exit(1)
    elif chosen_provider == "anthropic":
        if not getattr(cfg, "anthropic_api_key", ""):
            console.print(
                Panel(
                    "[bold red]Error: Anthropic API Key not found![/bold red]\n\n"
                    "Please configure [yellow]ANTHROPIC_API_KEY[/yellow] in your environment, "
                    "in a [yellow].env[/yellow] file, or pass [yellow]--api-key YOUR_KEY[/yellow].",
                    title="Configuration Missing",
                    border_style="red",
                )
            )
            sys.exit(1)

    # Continuous / Overnight mode execution
    is_continuous = continuous or hours > 0
    if is_continuous:
        agent = AutoMateAgent(config=cfg)
        try:
            agent.run_continuous(
                task=task,
                duration_hours=hours,
                loop_interval=getattr(cfg, "loop_interval", 1.5),
                keep_awake=getattr(cfg, "keep_awake", True),
            )
        except KeyboardInterrupt:
            agent.stop()
            console.print("\n[yellow]Continuous run halted by user.[/yellow]")
        return

    # Check if task corresponds to a pre-packaged recipe or keyword match
    from automate.recipes import get_recipe
    recipe = get_recipe(task)
    if not recipe:
        tl = task.lower()
        if ("weather" in tl or "youtube" in tl or "browse" in tl) and ("code" in tl or "vscode" in tl or "python" in tl) and ("file" in tl or "folder" in tl or "explorer" in tl):
            recipe = get_recipe("full-human-worker")
        elif "all" in tl and "task" in tl:
            recipe = get_recipe("full-human-worker")
        elif "weather" in tl or "youtube" in tl or "browse" in tl or "chrome" in tl:
            recipe = get_recipe("browse-weather-youtube")
        elif "python" in tl or "vscode" in tl or "code" in tl or "script" in tl:
            recipe = get_recipe("code-python-project")
        elif "file manager" in tl or ("explorer" in tl and "folder" in tl) or ("file" in tl and "folder" in tl):
            recipe = get_recipe("file-manager-organize")

    if recipe:
        duration_desc = f"{duration}m" if duration > 0 else (f"{hours}h" if hours > 0 else "None")
        console.print(
            Panel(
                f"[bold green]Executing Autonomous Workflow Recipe:[/bold green] [yellow]{recipe.name}[/yellow]\n"
                f"[dim]Category:[/dim] {recipe.category}\n"
                f"[dim]Description:[/dim] {recipe.description}\n"
                f"[dim]Repetitions:[/dim] [cyan]{repeat}[/cyan] cycle(s) [dim]|[/dim] [dim]Duration Limit:[/dim] [cyan]{duration_desc}[/cyan]",
                title="Recipe Mode",
                border_style="green",
            )
        )
        from automate.tools import DesktopToolSuite
        suite = DesktopToolSuite()

        total_sec = (hours * 3600.0) + (duration * 60.0)
        end_time = (time.time() + total_sec) if total_sec > 0 else None

        cycle = 1
        try:
            while True:
                if end_time and time.time() >= end_time:
                    console.print(f"\n[bold green]Duration limit reached ({duration_desc}). Finished {cycle - 1} cycle(s).[/bold green]")
                    break
                if repeat > 1 and cycle > repeat:
                    console.print(f"\n[bold green]Completed all {repeat} repetition cycle(s) successfully![/bold green]")
                    break

                if repeat > 1 or end_time:
                    cycle_hdr = f"🔄 Recipe Cycle {cycle} of {repeat}" if repeat > 1 else f"🔄 Recipe Cycle {cycle}"
                    console.print(Panel(f"[bold cyan]{cycle_hdr}[/bold cyan]", border_style="cyan"))

                res = recipe.execute(suite)
                console.print(Panel(f"[bold green]Cycle {cycle} Completed Successfully![/bold green]\n\n{res}", title="Cycle Done", border_style="green"))

                cycle += 1
                if (repeat > 1 and cycle <= repeat) or (end_time and time.time() < end_time):
                    time.sleep(2.0)
            return
        except KeyboardInterrupt:
            console.print("\n[yellow]Recipe halted by user.[/yellow]")
            return

    # Discrete Task Overview Card
    active_model = cfg.cloudflare_model if chosen_provider == "cloudflare" else cfg.model
    duration_desc = f"{duration}m" if duration > 0 else (f"{hours}h" if hours > 0 else "None")
    console.print(
        Panel(
            f"[bold white]Task Instruction:[/bold white]\n[yellow]{task}[/yellow]\n\n"
            f"[dim]Provider:[/dim] [{'magenta' if chosen_provider == 'cloudflare' else 'cyan'}]{chosen_provider.upper()}[/] [dim]|[/dim] "
            f"[dim]Model:[/dim] [cyan]{active_model}[/cyan] [dim]|[/dim] "
            f"[dim]Max Steps:[/dim] [cyan]{cfg.max_steps}[/cyan] [dim]|[/dim] "
            f"[dim]Repetitions:[/dim] [cyan]{repeat}[/cyan] [dim]|[/dim] [dim]Duration:[/dim] [cyan]{duration_desc}[/cyan]\n"
            f"[dim]Safety Mode:[/dim] [{'green' if cfg.safety_mode else 'red'}]{cfg.safety_mode}[/] [dim]|[/dim] "
            f"[dim]Action Delay:[/dim] [cyan]{cfg.action_delay}s[/cyan] [dim]|[/dim] "
            f"[dim]Emergency Stop:[/dim] [yellow]Ctrl+C / Mouse to Corner[/yellow]",
            title="Task Initialized",
            border_style="bright_blue",
        )
    )

    agent = AutoMateAgent(config=cfg)
    total_sec = (hours * 3600.0) + (duration * 60.0)
    end_time = (time.time() + total_sec) if total_sec > 0 else None
    cycle = 1

    try:
        while True:
            if end_time and time.time() >= end_time:
                console.print(f"\n[bold green]Duration limit reached ({duration_desc}). Finished {cycle - 1} cycle(s).[/bold green]")
                break
            if repeat > 1 and cycle > repeat:
                console.print(f"\n[bold green]Completed all {repeat} repetition cycle(s) successfully![/bold green]")
                break

            if repeat > 1 or end_time:
                cycle_hdr = f"🔄 Task Cycle {cycle} of {repeat}" if repeat > 1 else f"🔄 Task Cycle {cycle}"
                console.print(Panel(f"[bold cyan]{cycle_hdr}[/bold cyan]", border_style="cyan"))

            with console.status(f"[bold green]AutoMate executing cycle {cycle}...[/bold green]", spinner="dots"):
                result = agent.run(task)

            # Display actions summary for this cycle
            console.print()
            agent.action_logger.print_summary(console)
            console.print()

            if result.success:
                console.print(
                    Panel(
                        f"[bold green]CYCLE {cycle} COMPLETED SUCCESSFULLY[/bold green]\n\n"
                        f"[bold]Steps Taken:[/bold] {result.steps_taken}\n"
                        f"[bold]Duration:[/bold] {result.total_duration_seconds:.2f}s\n"
                        f"[bold]Agent Summary:[/bold] {result.final_message or 'Done.'}",
                        title=f"Cycle {cycle} Success",
                        border_style="green",
                    )
                )
            else:
                console.print(
                    Panel(
                        f"[bold red]CYCLE {cycle} HALTED / INCOMPLETE[/bold red]\n\n"
                        f"[bold]Steps Taken:[/bold] {result.steps_taken}\n"
                        f"[bold]Duration:[/bold] {result.total_duration_seconds:.2f}s\n"
                        f"[bold]Reason / Error:[/bold] {result.error or result.final_message}",
                        title=f"Cycle {cycle} Incomplete",
                        border_style="red",
                    )
                )

            cycle += 1
            if (repeat > 1 and cycle <= repeat) or (end_time and time.time() < end_time):
                time.sleep(2.0)

    except KeyboardInterrupt:
        console.print("\n")
        agent.stop()
        console.print(
            Panel(
                "[bold yellow]Emergency stop triggered by user (Ctrl+C)![/bold yellow]\n"
                "Mouse input halted and active agent control loop aborted.",
                title="Interrupted",
                border_style="yellow",
            )
        )
        agent.action_logger.print_summary(console)
        sys.exit(130)

    except Exception as e:
        console.print(
            Panel(
                f"[bold red]Execution encountered unexpected error:[/bold red]\n{e}",
                title="Execution Error",
                border_style="red",
            )
        )
        sys.exit(1)


@automate.command()
@click.option("--max-steps", default=30, type=int, help="Max steps per interactive task.")
@click.option("--model", default=None, type=str, help="Claude model name override.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
def interactive(max_steps: int, model: str | None, verbose: bool) -> None:
    """Start interactive mode - type tasks one at a time in a REPL."""
    show_banner()
    console.print(
        Panel(
            "Welcome to [bold cyan]AutoMate Interactive REPL[/bold cyan]!\n"
            "Enter tasks to execute consecutively. AutoMate retains state and perception.\n"
            "Commands: [yellow]exit[/yellow] / [yellow]quit[/yellow] to quit, "
            "[yellow]history[/yellow] to view actions, [yellow]clear[/yellow] to clear console.",
            title="Interactive Session",
            border_style="cyan",
        )
    )

    cfg = get_effective_config(model=model, max_steps=max_steps, verbose=verbose)
    agent = AutoMateAgent(config=cfg)

    while True:
        try:
            task_input = Prompt.ask("\n[bold cyan]AutoMate Task[/bold cyan]").strip()
            if not task_input:
                continue

            cmd = task_input.lower()
            if cmd in ("exit", "quit", "q"):
                console.print("[dim]Exiting AutoMate interactive mode. Goodbye![/dim]")
                break
            elif cmd == "history":
                agent.action_logger.print_summary(console)
                continue
            elif cmd == "clear":
                console.clear()
                show_banner()
                continue

            console.print(f"[bold yellow]Executing:[/bold yellow] {task_input}")
            result = agent.run(task_input)

            if result.success:
                console.print(f"[bold green]Done ({result.steps_taken} steps)[/bold green]")
            else:
                console.print(f"[bold red]Incomplete: {result.error or result.final_message}[/bold red]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Task cancelled by user. Returning to prompt...[/yellow]")
        except EOFError:
            break


@automate.command()
@click.option("--output", "-o", default="screenshot.png", help="Path to save captured screenshot.")
def screenshot(output: str) -> None:
    """Take a screenshot of current desktop and save it (for diagnostics/testing)."""
    console.print("[dim]Capturing screenshot...[/dim]")
    save_path = Path(output).resolve()

    try:
        from automate.agent import FallbackScreenCapture

        capturer: Any
        if ScreenCapture is not None:
            try:
                capturer = ScreenCapture()
            except Exception:
                capturer = FallbackScreenCapture()
        else:
            capturer = FallbackScreenCapture()

        img = capturer.capture()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(save_path))

        file_size_kb = save_path.stat().st_size / 1024
        console.print(
            Panel(
                f"[bold green]Screenshot saved successfully![/bold green]\n\n"
                f"[bold]Destination:[/bold] {save_path}\n"
                f"[bold]Resolution:[/bold] {img.width}x{img.height}\n"
                f"[bold]File Size:[/bold] {file_size_kb:.1f} KB",
                title="Screen Capture",
                border_style="green",
            )
        )
    except Exception as e:
        console.print(
            Panel(
                f"[bold red]Failed to capture screenshot:[/bold red] {e}",
                title="Capture Error",
                border_style="red",
            )
        )
        sys.exit(1)


@automate.command()
@click.argument("task")
@click.option("--hours", "-H", default=8.0, type=float, help="Target duration in hours to run (default 8.0h for overnight; 0 for 24/7 infinite).")
@click.option("--provider", "-p", default="cloudflare", type=click.Choice(["cloudflare", "anthropic"], case_sensitive=False), help="AI provider.")
@click.option("--loop-interval", "-i", default=1.5, type=float, help="Pause seconds between perception cycles.")
@click.option("--keep-awake/--no-keep-awake", default=True, help="Prevent Windows sleep and monitor off.")
@click.option("--cf-account-id", default=None, type=str, help="Cloudflare Account ID override.")
@click.option("--cf-token", default=None, type=str, help="Cloudflare API Token override.")
@click.option("--cf-model", default=None, type=str, help="Cloudflare model override.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose debug output.")
def overnight(
    task: str,
    hours: float,
    provider: str,
    loop_interval: float,
    keep_awake: bool,
    cf_account_id: str | None,
    cf_token: str | None,
    cf_model: str | None,
    verbose: bool,
) -> None:
    """Run an unattended overnight or 24/7 session (ideal for games, repetitive tasks)."""
    show_banner()
    log_level = "DEBUG" if verbose else "INFO"
    get_logger("automate", level=log_level)

    cfg = get_effective_config(
        provider=provider,
        cf_account_id=cf_account_id,
        cf_token=cf_token,
        cf_model=cf_model,
        duration_hours=hours,
        keep_awake=keep_awake,
        loop_interval=loop_interval,
        verbose=verbose,
    )

    if provider == "cloudflare" and not getattr(cfg, "cloudflare_api_token", ""):
        console.print(
            Panel(
                "[bold red]Cloudflare API Token missing![/bold red]\n\n"
                "Please set [yellow]CLOUDFLARE_API_TOKEN[/yellow] and [yellow]CLOUDFLARE_ACCOUNT_ID[/yellow] "
                "in .env or pass [yellow]--cf-token[/yellow].",
                title="Configuration Required",
                border_style="red",
            )
        )
        sys.exit(1)

    agent = AutoMateAgent(config=cfg)
    try:
        agent.run_continuous(
            task=task,
            duration_hours=hours,
            loop_interval=loop_interval,
            keep_awake=keep_awake,
        )
    except KeyboardInterrupt:
        agent.stop()
        console.print("\n[yellow]Overnight session stopped by user.[/yellow]")


@automate.command("keep-awake")
@click.option("--minutes", "-m", default=60, type=int, help="Minutes to keep PC awake.")
def keep_awake_cmd(minutes: int) -> None:
    """Test and manually assert Windows sleep prevention."""
    from automate.keep_awake import KeepAwake

    console.print(
        Panel(
            f"[bold cyan]Windows Keep-Awake[/bold cyan] testing for [yellow]{minutes} minutes[/yellow].\n"
            "System sleep, hibernation, and screen display-off are now suspended.\n"
            "[dim]Press [yellow]Ctrl+C[/yellow] to release and restore normal power policies.[/dim]",
            title="Keep-Awake Active",
            border_style="green",
        )
    )

    mgr = KeepAwake(keep_display_on=True)
    if not mgr.start():
        console.print("[red]Could not engage Windows keep-awake state.[/red]")
        sys.exit(1)

    try:
        time.sleep(minutes * 60)
    except KeyboardInterrupt:
        pass
    finally:
        mgr.stop()
        console.print("[green]Keep-Awake released. Normal Windows sleep policies restored.[/green]")


@automate.command()
def config() -> None:
    """Show current AutoMate configuration and system environment."""
    show_banner()
    cfg = get_effective_config()

    table = Table(
        title="Active AutoMate Configuration",
        header_style="bold cyan",
        border_style="blue",
        show_lines=True,
    )
    table.add_column("Setting", style="bold magenta", width=24)
    table.add_column("Current Value", style="yellow")
    table.add_column("Description", style="dim")

    # Provider
    prov = getattr(cfg, "provider", "cloudflare")
    table.add_row("provider", f"[{'magenta' if prov == 'cloudflare' else 'cyan'}]{prov.upper()}[/]", "Default AI vision provider")

    # Cloudflare settings
    cf_acc = getattr(cfg, "cloudflare_account_id", "")
    cf_tok = getattr(cfg, "cloudflare_api_token", "")
    cf_acc_disp = f"{cf_acc[:6]}...{cf_acc[-4:]}" if len(cf_acc) > 10 else (cf_acc or "[red]Missing[/red]")
    cf_tok_disp = "[green]Configured[/green]" if cf_tok else "[red]Not configured (Missing)[/red]"

    table.add_row("cloudflare_account_id", cf_acc_disp, "Cloudflare Account ID")
    table.add_row("cloudflare_api_token", cf_tok_disp, "Cloudflare API Token for Workers AI")
    table.add_row("cloudflare_model", str(getattr(cfg, "cloudflare_model", "")), "Cloudflare Workers AI vision model")

    # Anthropic settings
    raw_key = getattr(cfg, "anthropic_api_key", "")
    if raw_key:
        masked_key = f"{raw_key[:7]}...{raw_key[-4:]}" if len(raw_key) > 12 else "***"
        key_display = f"[green]{masked_key} (Configured)[/green]"
    else:
        key_display = "[dim]Not configured[/dim]"

    table.add_row("anthropic_api_key", key_display, "Anthropic API Key (Claude fallback)")
    table.add_row("model", str(getattr(cfg, "model", "")), "Anthropic Claude model identifier")

    # Continuous / overnight settings
    table.add_row("duration_hours", f"{getattr(cfg, 'duration_hours', 0.0)}h (0=24/7 infinite)", "Default continuous run duration")
    table.add_row("keep_awake", str(getattr(cfg, "keep_awake", True)), "Prevent Windows sleep & display off")
    table.add_row("loop_interval", f"{getattr(cfg, 'loop_interval', 1.5)}s", "Pacing delay between perception cycles")
    table.add_row("max_steps", str(getattr(cfg, "max_steps", "")), "Max execution steps per discrete task")
    table.add_row("safety_mode", str(getattr(cfg, "safety_mode", "")), "Failsafe and boundary checks enabled")
    table.add_row(
        "display_resolution",
        f"{getattr(cfg, 'display_width', '')}x{getattr(cfg, 'display_height', '')} px",
        "Target primary display size",
    )
    table.add_row("action_delay", f"{getattr(cfg, 'action_delay', '')}s", "Delay between consecutive actions")
    table.add_row("log_level", str(getattr(cfg, "log_level", "")), "Active logging verbosity")

    console.print(table)


@automate.command(name="tools")
def list_tools() -> None:
    """List all available desktop automation tools and capabilities."""
    show_banner()
    from automate.tools import DesktopToolSuite

    suite = DesktopToolSuite()

    table = Table(
        title="🛠️ AutoMate Desktop Tools & Capabilities",
        header_style="bold cyan",
        border_style="magenta",
        show_lines=True,
    )
    table.add_column("Tool Name", style="bold green", width=20)
    table.add_column("Parameters", style="yellow", width=28)
    table.add_column("Description", style="white")

    for name, tool in suite._tools.items():
        params = ", ".join(tool.parameters.get("properties", {}).keys()) or "(none)"
        table.add_row(name, params, tool.description)

    console.print(table)


@automate.command(name="recipes")
def list_recipes_cmd() -> None:
    """List all pre-configured multi-step automation workflow recipes."""
    show_banner()
    from automate.recipes import list_recipes

    recipes = list_recipes()
    table = Table(
        title="📋 AutoMate Autonomous Workflow Recipes",
        header_style="bold cyan",
        border_style="green",
        show_lines=True,
    )
    table.add_column("Recipe Name", style="bold green", width=26)
    table.add_column("Category", style="bold magenta", width=18)
    table.add_column("Description", style="white")

    for r in recipes:
        table.add_row(r.name, r.category, r.description)

    console.print(table)
    console.print("\n[dim]Run any recipe with: [bold yellow]automate recipe <name>[/bold yellow] or [bold yellow]automate run \"<instruction>\"[/bold yellow][/dim]\n")


@automate.command(name="recipe")
@click.argument("name")
@click.option("--repeat", "-r", default=1, type=int, help="Number of times to repeat the recipe (e.g. -r 3).")
@click.option("--duration", "-d", default=0.0, type=float, help="Duration in minutes to run recipe repeatedly.")
@click.option("--hours", default=0.0, type=float, help="Hours to run recipe repeatedly.")
@click.option("--watch-mins", default=None, type=float, help="Minutes to watch/stream YouTube video (default 2 to 3 mins).")
@click.option("--fast", "--quick", is_flag=True, help="Fast execution mode with abbreviated pauses.")
def run_recipe_cmd(name: str, repeat: int, duration: float, hours: float, watch_mins: float | None, fast: bool) -> None:
    """Execute a predefined multi-step automation workflow recipe."""
    show_banner()
    from automate.recipes import get_recipe
    from automate.tools import DesktopToolSuite

    if fast:
        os.environ["AUTOMATE_FAST_MODE"] = "1"
    if watch_mins is not None:
        os.environ["AUTOMATE_WATCH_MINS"] = str(watch_mins)

    recipe = get_recipe(name)
    if not recipe:
        console.print(f"[bold red]Recipe '{name}' not found![/bold red] Use [yellow]automate recipes[/yellow] to see available workflows.")
        sys.exit(1)

    tools = DesktopToolSuite()
    total_sec = (hours * 3600.0) + (duration * 60.0)
    end_time = (time.time() + total_sec) if total_sec > 0 else None
    duration_desc = f"{duration}m" if duration > 0 else (f"{hours}h" if hours > 0 else "None")

    console.print(
        Panel(
            f"[bold cyan]Recipe:[/bold cyan] [bold yellow]{recipe.name}[/bold yellow] ([magenta]{recipe.category}[/magenta])\n"
            f"[dim]Description:[/dim] {recipe.description}\n"
            f"[dim]Repetitions:[/dim] [cyan]{repeat}[/cyan] cycle(s) [dim]|[/dim] [dim]Duration Limit:[/dim] [cyan]{duration_desc}[/cyan]",
            title="Recipe Execution",
            border_style="green",
        )
    )

    cycle = 1
    try:
        while True:
            if end_time and time.time() >= end_time:
                console.print(f"\n[bold green]Duration limit reached ({duration_desc}). Finished {cycle - 1} cycle(s).[/bold green]")
                break
            if repeat > 1 and cycle > repeat:
                console.print(f"\n[bold green]Completed all {repeat} repetition cycle(s) successfully![/bold green]")
                break

            if repeat > 1 or end_time:
                cycle_hdr = f"🔄 Recipe Cycle {cycle} of {repeat}" if repeat > 1 else f"🔄 Recipe Cycle {cycle}"
                console.print(Panel(f"[bold cyan]{cycle_hdr}[/bold cyan]", border_style="cyan"))

            res = recipe.execute(tools)
            console.print(f"[bold green]Cycle {cycle} Completed:[/bold green] {res}")

            cycle += 1
            if (repeat > 1 and cycle <= repeat) or (end_time and time.time() < end_time):
                time.sleep(2.0)

    except KeyboardInterrupt:
        console.print("\n[yellow]Recipe run halted by user.[/yellow]")


def main() -> None:
    """CLI script entrypoint."""
    automate(prog_name="automate")


if __name__ == "__main__":
    main()
