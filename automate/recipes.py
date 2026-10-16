"""Predefined multi-step automation routines and recipes for AutoMate.

Provides high-level human worker execution routines:
- Complete web browsing (weather search, tab operations, YouTube play/pause/next, scrolling, reopen/close)
- Coding workflows (visually open VS Code, write Python character-by-character, save file, execute in terminal, close)
- File Explorer management (visually open Explorer, create folders, enter directory, create subfolders, save file, close)
- Full human worker routine combining all capabilities

Features organic human cadence:
- Visible character-by-character typing with natural keystroke variance
- Smooth, visible multi-stage page scrolling
- Organic random pauses between tasks (contemplation, reading, decision making)
- Substantial 2-3 minute YouTube video watching intervals with live progress countdowns
"""

from __future__ import annotations

import os
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List

from rich.console import Console
from rich.panel import Panel

from automate.logger import get_logger
from automate.tools import DesktopToolSuite

logger = get_logger("automate.recipes")
console = Console()

_RECIPE_STOP_EVENT = threading.Event()


def stop_recipe() -> None:
    """Signal any executing recipe to abort immediately."""
    _RECIPE_STOP_EVENT.set()


def reset_recipe_stop() -> None:
    """Reset the recipe stop signal before starting a new run."""
    _RECIPE_STOP_EVENT.clear()


def is_recipe_stopped() -> bool:
    """Check if a stop has been requested."""
    return _RECIPE_STOP_EVENT.is_set()


def human_pause(min_sec: float, max_sec: float, reason: str = "", countdown: bool = False) -> float:
    """Pause execution for a realistic random human contemplation interval.

    Args:
        min_sec: Minimum pause duration in seconds.
        max_sec: Maximum pause duration in seconds.
        reason: Explanation of the human worker's current action or contemplation.
        countdown: If True and duration >= 10s, displays a live remaining time countdown.

    Returns:
        The actual elapsed sleep time in seconds.
    """
    if _RECIPE_STOP_EVENT.is_set():
        raise InterruptedError("Recipe execution stopped by user")
    # Quick/test mode check: can be enabled via AUTOMATE_FAST_MODE=1
    if os.environ.get("AUTOMATE_FAST_MODE") == "1":
        fast_delay = min(0.3, min_sec)
        time.sleep(fast_delay)
        return fast_delay

    # Allow custom watch time override from environment if provided
    if countdown and min_sec >= 60.0 and os.environ.get("AUTOMATE_WATCH_MINS"):
        try:
            custom_m = float(os.environ["AUTOMATE_WATCH_MINS"])
            sec = custom_m * 60.0
        except ValueError:
            sec = random.uniform(min_sec, max_sec)
    else:
        sec = random.uniform(min_sec, max_sec)

    if countdown and sec >= 10.0:
        mins = int(sec // 60)
        secs = int(sec % 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        console.print(f"[bold cyan]⏳ {reason} [dim](waiting {time_str})...[/dim][/bold cyan]")

        start = time.time()
        last_log = start
        while True:
            if _RECIPE_STOP_EVENT.is_set():
                raise InterruptedError("Recipe execution stopped by user")
            elapsed = time.time() - start
            if elapsed >= sec:
                break
            remain = int(sec - elapsed)
            rem_m = remain // 60
            rem_s = remain % 60
            # Print milestone updates every 30 seconds for long waits
            if time.time() - last_log >= 30.0 and remain > 5:
                console.print(f"[dim cyan]  ... still {reason.lower()} ({rem_m:02d}:{rem_s:02d} remaining)[/dim cyan]")
                last_log = time.time()
            time.sleep(min(0.5, max(0.05, sec - elapsed)))
    else:
        if reason:
            logger.info(f"Human contemplation pause ({sec:.1f}s): {reason}")
        # Sleep in small slices to allow immediate stop
        t_start = time.time()
        while time.time() - t_start < sec:
            if _RECIPE_STOP_EVENT.is_set():
                raise InterruptedError("Recipe execution stopped by user")
            time.sleep(min(0.2, sec - (time.time() - t_start)))

    return sec


# Curated diverse library of captivating YouTube search topics across 8 categories
RANDOM_YOUTUBE_TOPICS: List[str] = [
    # 1. Ambient & Chill Music
    "japanese city pop 80s vinyl mix",
    "synthwave radio chill beats to code relax",
    "ambient cyberpunk rainy city night soundscape",
    "coffee shop acoustic guitar instrumental",
    "celtic fantasy harp relaxing medieval music",
    "lofi hip hop radio beats to relax study to",
    "piano chillhop study concentration beats",
    "retrowave synth instrumental driving at night",
    "nordic ambient folk relaxing nature sound",
    "deep focus electronic ambient mix",
    # 2. Tech, Engineering & Coding
    "building an 8 bit computer from scratch ben eater",
    "writing an operating system from scratch in rust",
    "how microchips are made inside asml cleanrooms",
    "restoring a 1980s vintage macintosh computer",
    "unreal engine 5 realistic environment design showcase",
    "mechanical keyboard custom build sound test",
    "how fiber optic cables cross oceans documentary",
    "history of the internet 1969 to present documentary",
    "retro supercomputing cray 1 breakdown",
    # 3. Science & Astronomy
    "james webb space telescope deep field 4k documentary",
    "deep ocean bioluminescence 4k full documentary",
    "how neutron stars and black holes merge",
    "quantum computing explained visually 4k",
    "journey to the edge of the universe documentary",
    "hubble vs james webb telescope comparison",
    "mysteries of the deep sea national geographic",
    "scale of the cosmos from quarks to observable universe",
    # 4. Nature & Scenic Aerials
    "swiss alps 4k drone scenic relaxation nature sounds",
    "walking in tokyo in the rain 4k binaural audio",
    "norway aurora borealis northern lights real time 4k",
    "iceland volcanic landscapes aerial 4k drone film",
    "patagonia wilderness wildlife 4k documentary",
    "scenic train journey across the canadian rockies 4k",
    "new zealand fjordland 4k drone nature film",
    # 5. Gaming & Speedruns
    "history of super mario 64 speedrun world records",
    "blender 3d complete environment animation breakdown",
    "pixel art animation timelapse game dev",
    "evolution of open world game physics 2000 to 2026",
    "shadow of the colossus behind the scenes design",
    "minecraft redstone computer architecture build",
    # 6. Ancient History & Architecture
    "how ancient roman concrete survived two thousand years",
    "the lost cities of the amazon lidar discovery documentary",
    "secrets of the international space station interior tour",
    "how bullet trains shinkansen work engineering marvel",
    "gothic cathedral architectural engineering secrets",
]


def fetch_dynamic_youtube_query() -> str:
    """Obtain a dynamic, creative YouTube search topic via Cloudflare Workers AI or diverse curated pool."""
    cf_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

    if cf_account_id and cf_token:
        try:
            from automate.providers.cloudflare import CloudflareAIProvider
            provider = CloudflareAIProvider(account_id=cf_account_id, api_token=cf_token)
            ai_topic = provider.generate_random_youtube_topic()
            if ai_topic and len(ai_topic) >= 4:
                console.print(Panel(f"[bold magenta]🤖 Cloudflare Workers AI Dynamic Topic:[/bold magenta] [bold yellow]\"{ai_topic}\"[/bold yellow]", border_style="magenta"))
                return ai_topic
        except Exception as e:
            logger.debug(f"Cloudflare topic generation fallback: {e}")

    # Fallback to random sampling from the diverse pool
    sampled = random.choice(RANDOM_YOUTUBE_TOPICS)
    console.print(Panel(f"[bold cyan]🎲 Selected Creative Topic:[/bold cyan] [bold yellow]\"{sampled}\"[/bold yellow]", border_style="cyan"))
    return sampled


@dataclass
class AutomationRecipe:
    """Specification of an autonomous multi-step workflow recipe."""

    name: str
    description: str
    category: str
    execute: Callable[[DesktopToolSuite], str]


def run_browse_weather_and_youtube(tools: DesktopToolSuite) -> str:
    """Execute end-to-end browsing routine with video play/pause/next, scrolling, and tab/app management."""
    console.print(Panel("🌐 Starting Browsing Routine: Weather -> Dynamic YouTube -> Reopen Sites -> Close", style="bold cyan"))

    # Random pre-task contemplation
    human_pause(2.0, 4.0, "Preparing to start web browsing task")

    # 1. Search weather in Chrome
    logger.info("Step 1: Opening weather search in Google Chrome...")
    tools.open_url("https://www.google.com/search?q=weather+in+Nairobi", browser="chrome")
    human_pause(3.5, 5.5, "Waiting for Google search results to render")
    tools.hotkey(["win", "up"])
    human_pause(1.0, 2.0, "Maximizing browser window")

    # 2. Scroll down to read forecast with progressive reading pauses
    logger.info("Step 2: Progressively scrolling down to inspect forecast cards...")
    tools.reading_scroll(clicks=-8, stages=3)
    human_pause(2.5, 4.5, "Reading current weather temperature and hourly forecast")

    # Scroll back up to the search bar
    tools.mouse_scroll(clicks=8)
    human_pause(2.5, 4.0, "Contemplating next destination")

    # 3. Open a new tab
    logger.info("Step 3: Opening a new tab (Ctrl+T) for YouTube...")
    tools.new_tab(url="https://www.youtube.com")
    human_pause(3.5, 6.0, "Waiting for YouTube homepage to load")

    # 4. Fetch random topic (from Cloudflare AI or diverse pool) and search on YouTube
    yt_query = fetch_dynamic_youtube_query()
    logger.info(f"Step 4: Searching YouTube for '{yt_query}'...")
    tools.search_youtube(yt_query)
    human_pause(3.5, 5.5, "Waiting for YouTube search results to populate")

    # Visible scrolling through video search results
    logger.info("Inspecting search results list visibly...")
    tools.reading_scroll(clicks=-5, stages=2)
    human_pause(2.0, 3.5, "Scanning recommended video titles")
    tools.mouse_scroll(clicks=5)
    human_pause(1.5, 3.0, "Selecting top video result")

    # 5. Play first video
    logger.info(f"Step 5: Clicking and playing the first video for '{yt_query}'...")
    tools.play_youtube_video()

    # 2 to 3 minutes wait time to watch/listen to the video (120 to 180 seconds)
    # While watching, the human worker occasionally moves the mouse and glances at comments
    logger.info("Streaming YouTube video (2 to 3 minutes realistic listening duration)...")
    watch_target = human_pause(120.0, 180.0, reason=f"Streaming: '{yt_query}'", countdown=True)

    # 6. Pause playback
    logger.info("Step 6: Pausing playback (hotkey 'k')...")
    tools.toggle_youtube_playback()
    human_pause(4.0, 8.0, "Contemplating during pause")

    # 7. Resume playback
    logger.info("Step 7: Resuming playback (hotkey 'k')...")
    tools.toggle_youtube_playback()
    human_pause(15.0, 30.0, reason="Enjoying resumed video stream", countdown=True)

    # 8. Skip to next video
    logger.info("Step 8: Skipping to next video (Shift+N)...")
    tools.next_youtube_video()
    human_pause(20.0, 40.0, reason="Listening to the next queued video stream", countdown=True)

    # 9. Scroll through comments and suggested feed with reading intervals
    logger.info("Step 9: Scrolling down visibly to explore comments and related videos...")
    tools.reading_scroll(clicks=-10, stages=3)
    human_pause(3.0, 5.5, "Reading listener comments and feedback")

    # Scroll back up to the video player
    tools.mouse_scroll(clicks=10)
    human_pause(2.0, 4.0, "Preparing to wrap up video session")

    # 10. Close active YouTube tab
    logger.info("Step 10: Closing active YouTube tab (Ctrl+W)...")
    tools.close_tab()
    human_pause(2.5, 4.5, "Reviewing weather tab")

    # 11. Close Chrome application
    logger.info("Step 11: Closing Google Chrome (Alt+F4)...")
    tools.close_app("chrome")
    human_pause(3.0, 6.0, "Taking a break before opening research browser")

    # 12. Reopen Chrome with another site
    logger.info("Step 12: Reopening Chrome to browse Wikipedia...")
    tools.open_url("https://en.wikipedia.org", browser="chrome")
    human_pause(3.5, 6.0, "Waiting for Wikipedia page to render")

    # Visibly scroll Wikipedia with progressive reading stages
    tools.reading_scroll(clicks=-8, stages=3)
    human_pause(3.0, 6.0, "Reading featured Wikipedia article")
    tools.mouse_scroll(clicks=8)
    human_pause(2.0, 4.0, "Finishing Wikipedia review")

    # 13. Close Chrome cleanly
    logger.info("Step 13: Closing Chrome cleanly...")
    tools.close_app("chrome")
    human_pause(1.5, 3.0, "Task complete")

    return "Successfully completed complete browsing routine: weather search, YouTube 2-3 min video watch, play/pause/skip, feed scrolling, tab closure, Chrome exit, and second site navigation with organic random pauses."


def run_code_python_project(tools: DesktopToolSuite) -> str:
    """Execute coding routine: launch VS Code, write code visibly, save file, execute in terminal, and close."""
    console.print(Panel("💻 Starting Coding Routine: VS Code -> Visible Typing -> Save -> Execute -> Close", style="bold green"))

    human_pause(2.0, 4.0, "Preparing coding environment")

    # 1. Launch Visual Studio Code
    logger.info("Step 1: Launching Visual Studio Code...")
    tools.launch_app("vscode")
    human_pause(3.5, 6.0, "Waiting for VS Code workspace to load")

    tools.focus_window("Visual Studio Code")
    tools.hotkey(["win", "up"])
    human_pause(1.5, 3.0, "Maximizing editor window")

    # 2. Open new empty file
    logger.info("Step 2: Opening a new file tab (Ctrl+N)...")
    tools.hotkey(["ctrl", "n"])
    human_pause(2.0, 3.5, "Initializing new file buffer")

    # 3. Write Python code visibly character by character
    code_text = (
        '# AutoMate Autonomous Coding Engine\n'
        'import datetime\n'
        'import math\n'
        '\n'
        'print("=" * 50)\n'
        'print("  AutoMate Autonomous Worker Running in VS Code")\n'
        'print("  Timestamp:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))\n'
        'print("=" * 50)\n'
        '\n'
        'dataset = [15, 30, 45, 60, 75, 90, 105]\n'
        'print(f"Data: {dataset}")\n'
        'print(f"Sum: {sum(dataset)} | Average: {sum(dataset)/len(dataset):.2f}")\n'
        'print(f"Roots: {[round(math.sqrt(x), 2) for x in dataset]}")\n'
        'print("Autonomous coding script executed successfully!")\n'
    )

    logger.info("Step 3: Visually typing Python code character-by-character into VS Code...")
    for line in code_text.splitlines():
        tools.input.human_type(line)
        human_pause(0.15, 0.45)
        tools.press_key("enter")
    human_pause(3.0, 6.0, "Reviewing authored Python code syntax in VS Code")

    # 4. Save file (Ctrl+S)
    logger.info("Step 4: Saving file as 'automate_worker.py'...")
    tools.hotkey(["ctrl", "s"])
    human_pause(1.5, 2.5, "Waiting for Save As dialog")
    tools.input.human_type("automate_worker.py")
    human_pause(0.5, 1.0)
    tools.press_key("enter")
    human_pause(2.0, 3.5, "File saved to disk")

    # 5. Open integrated terminal in VS Code (Ctrl+`)
    logger.info("Step 5: Opening VS Code integrated terminal (Ctrl+`)...")
    tools.hotkey(["ctrl", "`"])
    human_pause(2.5, 4.5, "Waiting for PowerShell integrated terminal to load")

    # 6. Execute Python script in the terminal
    logger.info("Step 6: Executing 'python automate_worker.py' in the terminal...")
    tools.input.human_type("python automate_worker.py")
    human_pause(0.5, 1.0)
    tools.press_key("enter")

    # Observe the terminal execution output
    human_pause(6.0, 12.0, "Observing terminal execution output and calculations")

    # 7. Close the file editor tab
    logger.info("Step 7: Closing editor tab (Ctrl+W)...")
    tools.focus_window("Visual Studio Code")
    tools.hotkey(["ctrl", "w"])
    human_pause(1.5, 3.0, "Editor tab closed")

    # 8. Close VS Code application
    logger.info("Step 8: Gracefully closing Visual Studio Code (Alt+F4)...")
    tools.close_app("visual studio code")
    human_pause(1.5, 3.0, "VS Code closed")

    return "Successfully completed coding routine: opened VS Code, visually typed Python script character-by-character, saved file, executed in integrated terminal, and closed editor with organic contemplation pauses."


def run_file_manager_routine(tools: DesktopToolSuite) -> str:
    """Execute file management routine: visually create folders, organize subfolders, save file, and close."""
    console.print(Panel("📁 Starting File Manager Routine: Visual Explorer -> Folder Creation -> Notepad -> Close", style="bold yellow"))

    human_pause(2.0, 3.5, "Preparing file manager task")
    desktop_dir = os.path.abspath(os.path.expanduser("~/Desktop"))

    # 1. Open File Explorer at Desktop
    logger.info("Step 1: Opening Windows File Explorer at Desktop...")
    tools.open_file_explorer(desktop_dir)
    human_pause(2.0, 4.0, "Waiting for File Explorer to open")

    # 2. Maximize and focus Explorer
    tools.focus_window("Explorer")
    tools.hotkey(["win", "up"])
    human_pause(1.5, 3.0, "Maximizing Explorer window")

    # 3. Visually create main project directory
    logger.info("Step 2: Visually creating 'AutoMate_Showcase' folder...")
    tools.visual_create_folder("AutoMate_Showcase")
    human_pause(2.0, 4.0, "Inspecting newly created folder")

    # 4. Enter folder
    logger.info("Step 3: Entering 'AutoMate_Showcase' directory...")
    tools.press_key("enter")
    human_pause(2.0, 3.5, "Directory opened")

    # 5. Visually create subfolders with pauses between each
    logger.info("Step 4: Visually creating subfolders (Documents, Code_Projects, Media)...")
    tools.visual_create_folder("Documents")
    human_pause(1.5, 3.0, "Created Documents folder")

    tools.visual_create_folder("Code_Projects")
    human_pause(1.5, 3.0, "Created Code_Projects folder")

    tools.visual_create_folder("Media")
    human_pause(2.0, 3.5, "Created Media folder")

    # 6. Visually create and save a document using Notepad
    logger.info("Step 5: Launching Notepad to author file manifest...")
    tools.launch_app("notepad")
    human_pause(2.0, 4.0, "Waiting for Notepad to open")
    tools.focus_window("Notepad")

    manifest_text = (
        "AutoMate Desktop Worker - File Organization Complete!\n"
        "---------------------------------------------------\n"
        "Folders structured in Desktop/AutoMate_Showcase:\n"
        "1. Documents\n"
        "2. Code_Projects\n"
        "3. Media\n"
        "\n"
        "Status: Organized and verified autonomously."
    )
    logger.info("Typing manifest note visibly with human cadence into Notepad...")
    for line in manifest_text.splitlines():
        tools.input.human_type(line)
        human_pause(0.12, 0.35)
        tools.press_key("enter")
    human_pause(2.5, 4.5, "Reviewing typed manifest note")

    # Save manifest
    tools.hotkey(["ctrl", "s"])
    human_pause(1.5, 2.5, "Waiting for Notepad Save dialog")
    tools.input.human_type("Desktop_Manifest.txt")
    human_pause(0.5, 1.0)
    tools.press_key("enter")
    human_pause(1.5, 3.0, "Manifest file saved")

    # Close Notepad
    tools.close_app("notepad")
    human_pause(1.5, 3.0, "Notepad closed")

    # 7. Focus Explorer, refresh, and navigate back up
    logger.info("Step 6: Refreshing Explorer (F5) and navigating up...")
    tools.focus_window("Explorer")
    tools.press_key("f5")
    human_pause(1.5, 3.0, "Refreshed folder view")
    tools.hotkey(["alt", "up"])
    human_pause(1.5, 3.0, "Navigated up to Desktop")

    # 8. Close File Explorer
    logger.info("Step 7: Closing Windows File Explorer...")
    tools.close_app("explorer")
    human_pause(1.5, 2.5, "File management complete")

    return "Successfully completed file management routine: visually organized folders on Desktop, authored manifest file with visible typing, and closed Explorer with organic pauses."


def run_full_human_worker(tools: DesktopToolSuite) -> str:
    """Execute all autonomous capabilities: Browsing & YouTube -> File Manager -> VS Code Coding."""
    console.print(Panel("🤖 Starting Full Human Worker Master Routine (Browsing + Files + Coding)", style="bold magenta"))

    res1 = run_browse_weather_and_youtube(tools)
    human_pause(4.0, 8.0, "Transitioning from browsing to file management")

    res2 = run_file_manager_routine(tools)
    human_pause(4.0, 8.0, "Transitioning from file management to coding")

    res3 = run_code_python_project(tools)

    return f"Master routine finished:\n- {res1}\n- {res2}\n- {res3}"


RECIPES: Dict[str, AutomationRecipe] = {
    "browse-weather-youtube": AutomationRecipe(
        name="browse-weather-youtube",
        description="Complete web browsing routine: weather search, 2-3 min YouTube video streaming, play/pause/skip, scrolling, and tab/app closure.",
        category="Web Browsing",
        execute=run_browse_weather_and_youtube,
    ),
    "code-python-project": AutomationRecipe(
        name="code-python-project",
        description="Complete coding routine: launch VS Code, visually type Python code, save file, execute in terminal, and close.",
        category="Coding & VS Code",
        execute=run_code_python_project,
    ),
    "file-manager-organize": AutomationRecipe(
        name="file-manager-organize",
        description="Visual file management routine: open Explorer, visually create folders/subfolders, write manifest, and close.",
        category="File Management",
        execute=run_file_manager_routine,
    ),
    "full-human-worker": AutomationRecipe(
        name="full-human-worker",
        description="Master autonomous routine combining browsing with YouTube media control, visual file organization, and VS Code coding.",
        category="Full Automation",
        execute=run_full_human_worker,
    ),
}


def get_recipe(name: str) -> AutomationRecipe | None:
    """Retrieve recipe by normalized name."""
    clean = name.strip().lower().replace("_", "-")
    return RECIPES.get(clean)


def list_recipes() -> List[AutomationRecipe]:
    """Return all available recipes."""
    return list(RECIPES.values())
