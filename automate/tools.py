"""Comprehensive desktop automation tools suite for AutoMate.

Provides high-level, human-grade desktop operations:
- Application launching (Chrome, Notepad, VS Code, Discord, games, VectorCraft, etc.)
- Web navigation & browser control
- Human-grade mouse movements, clicks, drags, and scrolling
- Keyboard typing with human cadence and hotkey combinations
- Shell command execution (coding, file ops, scripts)
- Clipboard inspection and modification
- Desktop perception helpers
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from rich.console import Console

from automate.human_input import HumanInputEngine
from automate.logger import get_logger
from automate.screen import ScreenCapture, ensure_windows_desktop_and_dpi

logger = get_logger("automate.tools")
console = Console()

# Standard Windows application executable mapping
COMMON_APPS: Dict[str, List[str]] = {
    "chrome": [
        os.path.expanduser(r"~\Desktop\Stanley - Chrome.lnk"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "chrome.exe",
    ],
    "google chrome": [
        os.path.expanduser(r"~\Desktop\Stanley - Chrome.lnk"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "chrome.exe",
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "msedge.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        "firefox.exe",
    ],
    "notepad": ["notepad.exe"],
    "calc": ["calc.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "terminal": ["wt.exe", "powershell.exe"],
    "vscode": [
        os.path.expanduser(r"~\Desktop\Visual Studio Code.lnk"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        "code.cmd",
    ],
    "code": [
        os.path.expanduser(r"~\Desktop\Visual Studio Code.lnk"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        "code.cmd",
    ],
    "visual studio code": [
        os.path.expanduser(r"~\Desktop\Visual Studio Code.lnk"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        "code.cmd",
    ],
    "spotify": [
        os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
        "spotify.exe",
    ],
    "vectorcraft": ["vectorcraft.exe"],
}


@dataclass
class ToolDefinition:
    """Specification of an available desktop tool for AI agents."""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]


class DesktopToolSuite:
    """Orchestrates all human and system-level desktop automation tools."""

    def __init__(self, human_engine: Optional[HumanInputEngine] = None) -> None:
        self.input = human_engine or HumanInputEngine()
        self.screen = ScreenCapture()
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_all_tools()

    def _register_all_tools(self) -> None:
        """Register the comprehensive suite of desktop tools."""

        # 1. launch_app
        self.register(
            name="launch_app",
            description="Launch a desktop application by name or executable path (e.g. 'chrome', 'notepad', 'vscode', 'calc', or a game).",
            parameters={
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Name or executable path of the application (e.g. 'chrome', 'notepad')"},
                    "args": {"type": "string", "description": "Optional command line arguments to pass to the app"},
                },
                "required": ["app_name"],
            },
            handler=self.launch_app,
        )

        # 2. open_url
        self.register(
            name="open_url",
            description="Open a web page or search query URL directly in Google Chrome or default browser.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL or search query link to open (e.g. 'https://www.google.com/search?q=weather+Nairobi')"},
                    "browser": {"type": "string", "description": "Browser to use ('chrome', 'edge', or 'default')", "default": "chrome"},
                },
                "required": ["url"],
            },
            handler=self.open_url,
        )

        # 3. mouse_click
        self.register(
            name="mouse_click",
            description="Smoothly move the mouse to coordinates (x, y) like a human and click.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Target X pixel coordinate"},
                    "y": {"type": "integer", "description": "Target Y pixel coordinate"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "double": {"type": "boolean", "description": "Whether to perform a double-click", "default": False},
                },
                "required": ["x", "y"],
            },
            handler=self.mouse_click,
        )

        # 4. mouse_move
        self.register(
            name="mouse_move",
            description="Smoothly glide the mouse cursor to (x, y) along a natural curved trajectory.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Target X pixel coordinate"},
                    "y": {"type": "integer", "description": "Target Y pixel coordinate"},
                },
                "required": ["x", "y"],
            },
            handler=self.mouse_move,
        )

        # 5. mouse_drag
        self.register(
            name="mouse_drag",
            description="Drag from start coordinates to destination coordinates with human resistance.",
            parameters={
                "type": "object",
                "properties": {
                    "start_x": {"type": "integer", "description": "Starting X coordinate"},
                    "start_y": {"type": "integer", "description": "Starting Y coordinate"},
                    "end_x": {"type": "integer", "description": "Destination X coordinate"},
                    "end_y": {"type": "integer", "description": "Destination Y coordinate"},
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
            handler=self.mouse_drag,
        )

        # 6. mouse_scroll
        self.register(
            name="mouse_scroll",
            description="Scroll vertical wheel up (positive) or down (negative).",
            parameters={
                "type": "object",
                "properties": {
                    "clicks": {"type": "integer", "description": "Scroll amount (positive=up, negative=down)"},
                    "x": {"type": "integer", "description": "Optional X coordinate to hover over before scrolling"},
                    "y": {"type": "integer", "description": "Optional Y coordinate to hover over before scrolling"},
                },
                "required": ["clicks"],
            },
            handler=self.mouse_scroll,
        )

        # 6b. reading_scroll
        self.register(
            name="reading_scroll",
            description="Scroll progressively with human reading pauses between increments.",
            parameters={
                "type": "object",
                "properties": {
                    "clicks": {"type": "integer", "description": "Total scroll clicks (negative=down, positive=up)"},
                    "stages": {"type": "integer", "description": "Number of reading pauses", "default": 3},
                },
                "required": ["clicks"],
            },
            handler=self.reading_scroll,
        )

        # 7. type_text
        self.register(
            name="type_text",
            description="Type a string with natural human cadence into the currently focused window.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                },
                "required": ["text"],
            },
            handler=self.type_text,
        )

        # 8. press_key
        self.register(
            name="press_key",
            description="Press and release a keyboard key (e.g. 'enter', 'win', 'esc', 'tab', 'space', 'backspace', 'up', 'down').",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key identifier to press"},
                },
                "required": ["key"],
            },
            handler=self.press_key,
        )

        # 9. hotkey
        self.register(
            name="hotkey",
            description="Press a keyboard shortcut combination simultaneously (e.g. ['ctrl', 't'], ['win', 'r'], ['alt', 'tab']).",
            parameters={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keys to press together",
                    },
                },
                "required": ["keys"],
            },
            handler=self.hotkey,
        )

        # 10. find_and_open_app
        self.register(
            name="find_and_open_app",
            description="Open the Windows Start Menu, type the app search query, and press Enter to launch it.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Name of the app to search and launch via Start Menu"},
                },
                "required": ["query"],
            },
            handler=self.find_and_open_app,
        )

        # 11. run_command
        self.register(
            name="run_command",
            description="Run a shell or PowerShell command and return its console output.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command string to execute"},
                },
                "required": ["command"],
            },
            handler=self.run_command,
        )

        # 12. wait
        self.register(
            name="wait",
            description="Pause execution to allow animations, apps, or web pages to load.",
            parameters={
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "Duration in seconds to wait"},
                },
                "required": ["seconds"],
            },
            handler=self.wait,
        )

        # 13. focus_window
        self.register(
            name="focus_window",
            description="Bring an open application window to the active foreground by partial title or app name (e.g. 'chrome', 'visual studio code', 'notepad', 'edge'). Run this before typing or clicking in that app.",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Keyword matching window title or app name (e.g. 'chrome', 'code', 'notepad')"},
                },
                "required": ["keyword"],
            },
            handler=self.focus_window,
        )

        # 14. new_tab
        self.register(
            name="new_tab",
            description="Open a new tab in Google Chrome or active browser (Ctrl+T) and optionally navigate to URL.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Optional URL to navigate to in the new tab"},
                },
            },
            handler=self.new_tab,
        )

        # 15. close_tab
        self.register(
            name="close_tab",
            description="Close the currently active browser or editor tab (Ctrl+W).",
            parameters={"type": "object", "properties": {}},
            handler=self.close_tab,
        )

        # 16. switch_tab
        self.register(
            name="switch_tab",
            description="Switch between open tabs in browser or editor (next=Ctrl+Tab, prev=Ctrl+Shift+Tab).",
            parameters={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["next", "prev"], "default": "next"},
                },
            },
            handler=self.switch_tab,
        )

        # 17. search_youtube
        self.register(
            name="search_youtube",
            description="Search YouTube directly in Chrome for videos, music, or tutorials.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term or video title"},
                },
                "required": ["query"],
            },
            handler=self.search_youtube,
        )

        # 18. open_file_explorer
        self.register(
            name="open_file_explorer",
            description="Open Windows File Explorer at a specific directory (defaults to Desktop).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to open (e.g. '~/Desktop', 'C:/Users/stanl/Desktop/MyProjects')"},
                },
            },
            handler=self.open_file_explorer,
        )

        # 19. create_directory
        self.register(
            name="create_directory",
            description="Create a directory or folder on the Windows desktop or filesystem.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Folder path to create (e.g. '~/Desktop/AutoMate_Projects')"},
                },
                "required": ["path"],
            },
            handler=self.create_directory,
        )

        # 20. create_file
        self.register(
            name="create_file",
            description="Create or overwrite a file with given text/code content.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute or relative file path"},
                    "content": {"type": "string", "description": "Content to write into the file"},
                },
                "required": ["file_path"],
            },
            handler=self.create_file,
        )

        # 21. open_in_vscode
        self.register(
            name="open_in_vscode",
            description="Open a file or project folder in Visual Studio Code and bring editor to the foreground.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or folder path to open in VS Code"},
                },
                "required": ["path"],
            },
            handler=self.open_in_vscode,
        )

        # 22. create_and_edit_python_file
        self.register(
            name="create_and_edit_python_file",
            description="Create a Python file with code content in a desktop directory and open it in VS Code.",
            parameters={
                "type": "object",
                "properties": {
                    "file_name": {"type": "string", "description": "Python file name (e.g. 'script.py')"},
                    "code_content": {"type": "string", "description": "Python code to write into the file"},
                    "directory": {"type": "string", "description": "Target folder (default: '~/Desktop/AutoMate_Projects')"},
                },
                "required": ["file_name", "code_content"],
            },
            handler=self.create_and_edit_python_file,
        )

        # 23. run_python
        self.register(
            name="run_python",
            description="Execute a Python script using the local Python interpreter and return console output.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the python script to run"},
                },
                "required": ["file_path"],
            },
            handler=self.run_python,
        )

        # 24. play_youtube_video
        self.register(
            name="play_youtube_video",
            description="Click and play a video on YouTube (clicks first search result or starts playback).",
            parameters={
                "type": "object",
                "properties": {
                    "video_title": {"type": "string", "description": "Optional specific video title to search and play"},
                },
            },
            handler=self.play_youtube_video,
        )

        # 25. toggle_youtube_playback
        self.register(
            name="toggle_youtube_playback",
            description="Toggle video playback (play / pause) on YouTube or browser media player.",
            parameters={"type": "object", "properties": {}},
            handler=self.toggle_youtube_playback,
        )

        # 26. next_youtube_video
        self.register(
            name="next_youtube_video",
            description="Skip to the next video in the YouTube queue (Shift+N).",
            parameters={"type": "object", "properties": {}},
            handler=self.next_youtube_video,
        )

        # 27. close_app
        self.register(
            name="close_app",
            description="Gracefully close an application window by name (e.g. 'chrome', 'vscode', 'explorer', 'notepad').",
            parameters={
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Application to close ('chrome', 'vscode', 'explorer', 'notepad')"},
                },
                "required": ["app_name"],
            },
            handler=self.close_app,
        )

        # 28. visual_create_folder
        self.register(
            name="visual_create_folder",
            description="Visually create a new folder inside active File Explorer using native Windows shortcuts and human typing.",
            parameters={
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string", "description": "Name for the new folder"},
                },
                "required": ["folder_name"],
            },
            handler=self.visual_create_folder,
        )

        # 29. visual_code_editor
        self.register(
            name="visual_code_editor",
            description="Visually write Python code character-by-character into VS Code, save it (Ctrl+S), and name the file.",
            parameters={
                "type": "object",
                "properties": {
                    "code_text": {"type": "string", "description": "Code string to type into editor"},
                    "file_name": {"type": "string", "description": "File name to save as (e.g. 'main.py')"},
                },
                "required": ["code_text"],
            },
            handler=self.visual_code_editor,
        )

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """Register a new tool definition."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Retrieve tool definition by name."""
        return self._tools.get(name.lower().strip())

    def list_tool_names(self) -> List[str]:
        """Return list of all registered tool names."""
        return list(self._tools.keys())

    def get_tools_summary_prompt(self) -> str:
        """Generate human-readable summary of tools for system prompt injection."""
        lines = ["AVAILABLE DESKTOP TOOLS:"]
        for tool in self._tools.values():
            params_desc = ", ".join(
                f"{k}: {v.get('type', 'any')}"
                for k, v in tool.parameters.get("properties", {}).items()
            )
            lines.append(f"- {tool.name}({params_desc}): {tool.description}")
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Tool Implementations
    # -------------------------------------------------------------------------

    def focus_window(self, keyword: str) -> str:
        """Bring an open window matching keyword to the foreground using Windows API."""
        ensure_windows_desktop_and_dpi()
        clean = keyword.lower().strip()
        if not clean:
            return "No keyword provided to focus_window"

        try:
            import win32gui
            import win32con
            import win32process
            import ctypes
        except ImportError:
            return "pywin32 not available for window management"

        alias_map = {
            "vscode": "visual studio code",
            "code": "visual studio code",
            "vs code": "visual studio code",
            "chrome": "chrome",
            "google chrome": "chrome",
            "explorer": "explorer",
            "file explorer": "explorer",
            "notepad": "notepad",
            "terminal": "terminal",
        }
        search_kw = alias_map.get(clean, clean)

        matches: List[Tuple[int, str]] = []

        def _enum(hwnd: int, _: Any) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                try:
                    classname = win32gui.GetClassName(hwnd)
                except Exception:
                    classname = ""
                if (title and search_kw in title.lower()) or (clean == "explorer" and classname == "CabinetWClass"):
                    matches.append((hwnd, title or "File Explorer"))
            return True

        try:
            win32gui.EnumWindows(_enum, None)
        except Exception as e:
            logger.debug(f"EnumWindows error: {e}")

        if not matches:
            return f"No visible window found matching '{keyword}'"

        target_hwnd, title = matches[0]
        try:
            if win32gui.IsIconic(target_hwnd):
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(target_hwnd, win32con.SW_SHOW)

            fore_hwnd = win32gui.GetForegroundWindow()
            fore_thread_id, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
            curr_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

            ctypes.windll.user32.AllowSetForegroundWindow(-1)
            if fore_thread_id != curr_thread_id:
                ctypes.windll.user32.AttachThreadInput(fore_thread_id, curr_thread_id, True)

            try:
                win32gui.BringWindowToTop(target_hwnd)
                win32gui.SetForegroundWindow(target_hwnd)
            finally:
                if fore_thread_id != curr_thread_id:
                    ctypes.windll.user32.AttachThreadInput(fore_thread_id, curr_thread_id, False)

            time.sleep(0.5)
            logger.info(f"Successfully focused window: '{title}' ({target_hwnd})")
            return f"Brought window '{title}' to active foreground"
        except Exception as e:
            err = f"Failed to focus window '{title}': {e}"
            logger.warning(err)
            return err

    def launch_app(self, app_name: str, args: str = "") -> str:
        """Launch an application on Windows and ensure it comes to the foreground."""
        ensure_windows_desktop_and_dpi()
        clean_name = app_name.strip().lower()

        # 1. Check Desktop shortcuts (.lnk files)
        desktop_dir = os.path.expanduser("~/Desktop")
        if os.path.exists(desktop_dir):
            try:
                for fname in os.listdir(desktop_dir):
                    if fname.lower().endswith(".lnk") and (clean_name in fname.lower() or fname.lower().startswith(clean_name)):
                        shortcut_path = os.path.join(desktop_dir, fname)
                        os.startfile(shortcut_path)
                        logger.info(f"Launched application via Desktop shortcut: {shortcut_path}")
                        time.sleep(1.5)
                        self.focus_window(clean_name)
                        return f"Successfully opened {app_name} via desktop shortcut ({shortcut_path})"
            except Exception as e:
                logger.debug(f"Desktop shortcut launch check failed: {e}")

        # 2. Check in COMMON_APPS aliases
        candidates = COMMON_APPS.get(clean_name, [app_name])

        for candidate in candidates:
            # If candidate is a shortcut file that exists
            if candidate.lower().endswith(".lnk") and os.path.exists(candidate):
                try:
                    os.startfile(candidate)
                    logger.info(f"Launched application shortcut: {candidate}")
                    time.sleep(1.5)
                    self.focus_window(clean_name)
                    return f"Successfully launched {app_name} ({candidate})"
                except Exception as e:
                    logger.debug(f"Failed to launch shortcut {candidate}: {e}")

            resolved = shutil.which(candidate) if not os.path.isabs(candidate) else candidate
            if resolved and os.path.exists(resolved):
                try:
                    cmd = [resolved]
                    if args:
                        cmd.extend(args.split())
                    subprocess.Popen(cmd)
                    logger.info(f"Launched application: {resolved} {' ' + args if args else ''}")
                    time.sleep(1.5)
                    self.focus_window(clean_name)
                    return f"Successfully launched {app_name} ({resolved})"
                except Exception as e:
                    logger.debug(f"Failed to launch via path {resolved}: {e}")

        # 3. Fallback to os.startfile or ShellExecute
        try:
            os.startfile(app_name)
            logger.info(f"Launched application via os.startfile: {app_name}")
            time.sleep(1.5)
            self.focus_window(clean_name)
            return f"Successfully opened {app_name}"
        except Exception as e:
            # Last ditch: try powershell Start-Process
            try:
                subprocess.Popen(["powershell", "-c", f"Start-Process '{app_name}'"])
                time.sleep(1.5)
                self.focus_window(clean_name)
                return f"Started process {app_name} via PowerShell"
            except Exception as e2:
                err_msg = f"Failed to launch application '{app_name}': {e} / {e2}"
                logger.error(err_msg)
                return err_msg

    def open_url(self, url: str, browser: str = "chrome") -> str:
        """Open a URL in Chrome or default browser and focus the window."""
        ensure_windows_desktop_and_dpi()
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = "https://" + clean_url

        if browser.lower() == "chrome":
            chrome_candidates = COMMON_APPS.get("chrome", [])
            for c in chrome_candidates:
                if c.endswith(".exe") and os.path.exists(c):
                    try:
                        subprocess.Popen([c, clean_url])
                        logger.info(f"Opened URL in Google Chrome: {clean_url}")
                        time.sleep(1.5)
                        self.focus_window("Chrome")
                        return f"Opened {clean_url} in Chrome"
                    except Exception:
                        pass

        # Default web browser fallback
        try:
            webbrowser.open(clean_url)
            logger.info(f"Opened URL in default browser: {clean_url}")
            time.sleep(1.5)
            self.focus_window("Chrome")
            return f"Opened {clean_url} in browser"
        except Exception as e:
            err = f"Failed to open URL '{clean_url}': {e}"
            logger.error(err)
            return err

    def mouse_click(
        self,
        x: int,
        y: int,
        button: str = "left",
        double: bool = False,
    ) -> str:
        """Move humanly and click mouse."""
        rx, ry = self.input.human_click(x=x, y=y, button=button, double=double)
        return f"Clicked ({rx}, {ry}) button={button} double={double}"

    def mouse_move(self, x: int, y: int) -> str:
        """Glide mouse to coordinates."""
        rx, ry = self.input.human_move(x, y)
        return f"Moved cursor to ({rx}, {ry})"

    def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> str:
        """Drag mouse from start to end."""
        self.input.human_drag(start_x, start_y, end_x, end_y)
        return f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"

    def mouse_scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> str:
        """Scroll vertical wheel."""
        self.input.human_scroll(clicks=clicks, x=x, y=y)
        return f"Scrolled {clicks} clicks"

    def reading_scroll(self, clicks: int, stages: int = 3) -> str:
        """Scroll progressively in stages with human reading pauses."""
        self.input.reading_scroll(total_clicks=clicks, stages=stages)
        return f"Scrolled {clicks} clicks in {stages} reading stages"

    def type_text(self, text: str) -> str:
        """Type string with human cadence."""
        self.input.human_type(text)
        return f"Typed '{text}'"

    def press_key(self, key: str) -> str:
        """Press single keyboard key."""
        self.input.press_key(key)
        return f"Pressed key '{key}'"

    def hotkey(self, keys: List[str]) -> str:
        """Execute key combo."""
        self.input.hotkey(*keys)
        return f"Executed hotkey {'+'.join(keys)}"

    def find_and_open_app(self, query: str) -> str:
        """Open Start menu and launch app via typing search query."""
        ensure_windows_desktop_and_dpi()
        logger.info(f"Finding and launching app '{query}' via Windows Start Menu...")
        self.input.press_key("win")
        time.sleep(0.6)
        self.input.human_type(query)
        time.sleep(0.6)
        self.input.press_key("enter")
        time.sleep(1.5)
        return f"Searched Start Menu for '{query}' and pressed Enter"

    def run_command(self, command: str) -> str:
        """Run terminal command."""
        try:
            res = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = res.stdout.strip() or res.stderr.strip() or "Command completed with no output."
            return out[:500]
        except Exception as e:
            return f"Command execution error: {e}"

    def wait(self, seconds: float) -> str:
        """Wait for specified seconds."""
        time.sleep(max(0.0, seconds))
        return f"Waited {seconds}s"

    def new_tab(self, url: str = "") -> str:
        """Open a new browser tab (Ctrl+T) and optionally navigate to URL."""
        ensure_windows_desktop_and_dpi()
        self.focus_window("Chrome")
        self.input.hotkey("ctrl", "t")
        time.sleep(0.8)
        if url:
            clean_url = url.strip()
            if not clean_url.startswith(("http://", "https://")):
                clean_url = "https://" + clean_url
            self.input.human_type(clean_url)
            time.sleep(0.3)
            self.input.press_key("enter")
            time.sleep(1.5)
            return f"Opened new tab and navigated to {clean_url}"
        return "Opened new browser tab"

    def close_tab(self) -> str:
        """Close current active tab (Ctrl+W)."""
        ensure_windows_desktop_and_dpi()
        self.input.hotkey("ctrl", "w")
        time.sleep(0.5)
        return "Closed active tab (Ctrl+W)"

    def switch_tab(self, direction: str = "next") -> str:
        """Switch to next or previous tab."""
        ensure_windows_desktop_and_dpi()
        if direction.lower() == "prev":
            self.input.hotkey("ctrl", "shift", "tab")
            action_desc = "previous tab (Ctrl+Shift+Tab)"
        else:
            self.input.hotkey("ctrl", "tab")
            action_desc = "next tab (Ctrl+Tab)"
        time.sleep(0.4)
        return f"Switched to {action_desc}"

    def search_youtube(self, query: str) -> str:
        """Search YouTube directly in Google Chrome."""
        clean_query = urllib.parse.quote_plus(query.strip())
        yt_url = f"https://www.youtube.com/results?search_query={clean_query}"
        return self.open_url(yt_url, browser="chrome")

    def open_file_explorer(self, path: str = "") -> str:
        """Open Windows File Explorer at specified directory."""
        ensure_windows_desktop_and_dpi()
        target = os.path.abspath(os.path.expanduser(path)) if path else os.path.abspath(os.path.expanduser("~/Desktop"))
        os.makedirs(target, exist_ok=True)
        try:
            subprocess.Popen(["explorer.exe", target])
            time.sleep(1.2)
            self.focus_window("Explorer")
            return f"Opened File Explorer at {target}"
        except Exception as e:
            err = f"Failed to open File Explorer: {e}"
            logger.error(err)
            return err

    def create_directory(self, path: str) -> str:
        """Create a directory on the filesystem."""
        target = os.path.abspath(os.path.expanduser(path))
        try:
            os.makedirs(target, exist_ok=True)
            logger.info(f"Created directory: {target}")
            return f"Successfully created directory: {target}"
        except Exception as e:
            err = f"Failed to create directory '{path}': {e}"
            logger.error(err)
            return err

    def create_file(self, file_path: str, content: str = "") -> str:
        """Create or overwrite a file with content."""
        target = os.path.abspath(os.path.expanduser(file_path))
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Created file: {target} ({len(content)} chars)")
            return f"Successfully created file: {target}"
        except Exception as e:
            err = f"Failed to write file '{file_path}': {e}"
            logger.error(err)
            return err

    def open_in_vscode(self, path: str) -> str:
        """Open a file or directory in Visual Studio Code."""
        ensure_windows_desktop_and_dpi()
        target = os.path.abspath(os.path.expanduser(path))
        code_candidates = COMMON_APPS.get("vscode", ["code.cmd"])

        for candidate in code_candidates:
            if candidate.endswith(".lnk") and os.path.exists(candidate):
                try:
                    os.startfile(candidate)
                    time.sleep(2.0)
                    self.focus_window("Visual Studio Code")
                    return f"Opened VS Code via shortcut for {target}"
                except Exception:
                    pass

            resolved = shutil.which(candidate) if not os.path.isabs(candidate) else candidate
            if resolved and os.path.exists(resolved):
                try:
                    subprocess.Popen([resolved, target])
                    time.sleep(2.0)
                    self.focus_window("Visual Studio Code")
                    return f"Opened {target} in Visual Studio Code ({resolved})"
                except Exception as e:
                    logger.debug(f"Failed to launch VS Code via {resolved}: {e}")

        # Fallback to code command
        try:
            subprocess.Popen(["code", target], shell=True)
            time.sleep(2.0)
            self.focus_window("Visual Studio Code")
            return f"Launched 'code {target}'"
        except Exception as e:
            return f"Failed to open in VS Code: {e}"

    def create_and_edit_python_file(self, file_name: str, code_content: str, directory: str = "") -> str:
        """Create a python script in desktop project folder and open in VS Code."""
        dir_path = os.path.abspath(os.path.expanduser(directory)) if directory else os.path.abspath(os.path.expanduser("~/Desktop/AutoMate_Projects"))
        os.makedirs(dir_path, exist_ok=True)

        if not file_name.endswith(".py"):
            file_name += ".py"
        target_file = os.path.join(dir_path, file_name)

        self.create_file(target_file, code_content)
        self.open_in_vscode(target_file)
        return f"Created Python file '{target_file}' and opened in VS Code"

    def run_python(self, file_path: str) -> str:
        """Execute a Python script using local Python interpreter and return output."""
        target = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(target):
            return f"File not found: {target}"
        try:
            res = subprocess.run(
                [sys.executable, target],
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = res.stdout.strip()
            err = res.stderr.strip()
            combined = f"STDOUT:\n{out}" if out else ""
            if err:
                combined += f"\nSTDERR:\n{err}"
            return combined or "Script executed with no console output."
        except Exception as e:
            return f"Failed to execute Python script: {e}"

    def play_youtube_video(self, video_title: str = "") -> str:
        """Click and play the first video on YouTube search results page."""
        ensure_windows_desktop_and_dpi()
        self.focus_window("Chrome")
        time.sleep(0.8)
        self.input.hotkey("win", "up")
        time.sleep(0.5)

        if video_title:
            self.search_youtube(video_title)
            time.sleep(3.5)

        # Move mouse smoothly to the first search result thumbnail (standard 1080p layout: ~500, 320)
        logger.info("Clicking first YouTube video in search results...")
        self.input.human_click(500, 320, button="left")
        time.sleep(4.0)

        # Guarantee focus on the video player and ensure playback starts
        self.focus_window("Chrome")
        time.sleep(0.5)
        # In case autoplay requires an explicit toggle, send 'k' to start playing
        self.input.press_key("k")
        time.sleep(0.5)
        return "Clicked first video in YouTube results and started playback"

    def toggle_youtube_playback(self) -> str:
        """Toggle video playback (play / pause) on YouTube via 'k' hotkey."""
        ensure_windows_desktop_and_dpi()
        self.focus_window("Chrome")
        time.sleep(0.5)
        # 'k' is the universal YouTube shortcut to play/pause
        self.input.press_key("k")
        time.sleep(0.5)
        return "Toggled YouTube playback (Play/Pause)"

    def next_youtube_video(self) -> str:
        """Skip to next video on YouTube via Shift+N."""
        ensure_windows_desktop_and_dpi()
        self.focus_window("Chrome")
        time.sleep(0.5)
        self.input.hotkey("shift", "n")
        time.sleep(3.5)
        return "Skipped to next YouTube video (Shift+N)"

    def close_app(self, app_name: str) -> str:
        """Close an application window gracefully."""
        ensure_windows_desktop_and_dpi()
        clean = app_name.strip().lower()
        if not clean:
            return "No app_name specified"

        self.focus_window(clean)
        time.sleep(0.6)
        self.input.hotkey("alt", "f4")
        time.sleep(1.2)
        logger.info(f"Closed application '{app_name}' via Alt+F4")
        return f"Closed application: {app_name}"

    def visual_create_folder(self, folder_name: str) -> str:
        """Visually create a folder inside active File Explorer."""
        ensure_windows_desktop_and_dpi()
        self.focus_window("Explorer")
        time.sleep(0.8)

        # Maximize File Explorer so folder pane is clearly visible
        self.input.hotkey("win", "up")
        time.sleep(0.5)

        # Click inside folder canvas to focus item view
        self.input.human_click(650, 400, button="left")
        time.sleep(0.5)

        # Windows native shortcut to create new folder
        self.input.hotkey("ctrl", "shift", "n")
        time.sleep(0.8)

        # Type folder name with human cadence and press Enter
        self.input.human_type(folder_name)
        time.sleep(0.3)
        self.input.press_key("enter")
        time.sleep(0.8)
        logger.info(f"Visually created folder '{folder_name}' in File Explorer")
        return f"Created folder '{folder_name}' in File Explorer"

    def visual_code_editor(self, code_text: str, file_name: str = "app.py") -> str:
        """Visually type code into VS Code, save it, name it, and execute in terminal."""
        ensure_windows_desktop_and_dpi()
        self.focus_window("Visual Studio Code")
        time.sleep(1.0)

        # Maximize VS Code
        self.input.hotkey("win", "up")
        time.sleep(0.5)

        # 1. New file in VS Code
        self.input.hotkey("ctrl", "n")
        time.sleep(1.0)

        # 2. Type code line by line with human cadence
        for line in code_text.splitlines():
            self.input.human_type(line)
            time.sleep(0.04)
            self.input.press_key("enter")
        time.sleep(1.0)

        # 3. Save file (Ctrl+S)
        self.input.hotkey("ctrl", "s")
        time.sleep(1.5)

        # 4. Type file name and save
        self.input.human_type(file_name)
        time.sleep(0.5)
        self.input.press_key("enter")
        time.sleep(1.5)

        # 5. Open integrated terminal in VS Code (Ctrl+`)
        self.input.hotkey("ctrl", "`")
        time.sleep(1.5)

        # 6. Run the script in the terminal
        self.input.human_type(f"python {file_name}")
        time.sleep(0.3)
        self.input.press_key("enter")
        time.sleep(2.0)

        logger.info(f"Visually typed, saved, and executed '{file_name}' in VS Code")
        return f"Visually typed, saved, and executed '{file_name}' in VS Code"

