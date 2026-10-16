"""AutoMate Agent - Core reasoning and execution loop powered by Claude Computer Use API.

Manages perception, multi-turn reasoning with Anthropic Claude, action dispatching,
and recovery mechanisms for Windows desktop automation.
"""

from __future__ import annotations

import base64
import ctypes
import io
import os
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic
from PIL import Image, ImageGrab
import pyautogui
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from automate.logger import ActionLogger, get_logger
from automate.providers import (
    AnthropicProvider,
    BaseAIProvider,
    CloudflareAIProvider,
    ModelResponse,
    ProviderAction,
)
from automate.continuous import ContinuousRunner, ContinuousStats

# Attempt imports from sibling modules with graceful fallbacks
try:
    from automate.config import Config, get_config
except ImportError:
    Config = None  # type: ignore
    get_config = None  # type: ignore

try:
    from automate.screen import ScreenCapture, ensure_windows_desktop_and_dpi
except ImportError:
    ScreenCapture = None  # type: ignore
    def ensure_windows_desktop_and_dpi(): pass

try:
    from automate.input_controller import InputController
except ImportError:
    InputController = None  # type: ignore

try:
    from automate.actions import ActionResult as CoreActionResult
except ImportError:
    CoreActionResult = None  # type: ignore


logger = get_logger("automate.agent")
console = Console()


@dataclass
class ActionResult:
    """Represents the outcome of a single low-level tool execution."""

    success: bool = True
    screenshot: str | None = None  # Base64-encoded PNG/JPEG
    error: str | None = None
    cursor_position: tuple[int, int] | None = None
    output: str | None = None


@dataclass
class AgentResult:
    """Represents the final summary of an AutoMate autonomous task run."""

    success: bool
    steps_taken: int
    action_history: list[dict[str, Any]] = field(default_factory=list)
    final_message: str = ""
    error: str | None = None
    total_duration_seconds: float = 0.0


class FallbackScreenCapture:
    """Resilient screen capture implementation with Windows desktop session attachment."""

    def __init__(self) -> None:
        self._ensure_input_desktop()

    def _ensure_input_desktop(self) -> None:
        """Attach current thread to active Windows input desktop if on Windows."""
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                h_input = user32.OpenInputDesktop(0, False, 0x01FF)
                if h_input:
                    user32.SetThreadDesktop(h_input)
            except Exception as e:
                logger.debug(f"Input desktop attachment notice: {e}")

    def capture(self) -> Image.Image:
        """Capture full primary screen."""
        self._ensure_input_desktop()
        try:
            import mss

            with mss.MSS() as sct:
                # Primary monitor is index 1 in mss
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(mon)
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception:
            try:
                return ImageGrab.grab()
            except Exception as e:
                logger.warning(f"Screen grab fallback to placeholder canvas: {e}")
                # Create a blank fallback canvas if desktop capture is locked
                return Image.new("RGB", (1920, 1080), color=(30, 30, 30))

    def get_screen_size(self) -> tuple[int, int]:
        """Return screen width and height."""
        try:
            w, h = pyautogui.size()
            if w > 0 and h > 0:
                return int(w), int(h)
        except Exception:
            pass
        return 1920, 1080

    def to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """Convert PIL Image to base64 string."""
        buf = io.BytesIO()
        image.save(buf, format=format)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def to_bytes(self, image: Image.Image, format: str = "JPEG", quality: int = 85) -> bytes:
        """Convert PIL Image to encoded JPEG or PNG bytes."""
        buf = io.BytesIO()
        if format.upper() == "JPEG" and image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buf, format=format, quality=quality)
        return buf.getvalue()

    def resize_for_api(
        self, image: Image.Image, max_width: int = 1280, max_height: int = 800
    ) -> tuple[Image.Image, float]:
        """Downscale image preserving aspect ratio if exceeding bounds."""
        orig_w, orig_h = image.size
        scale = min(max_width / orig_w, max_height / orig_h, 1.0)
        if scale < 1.0:
            new_size = (int(orig_w * scale), int(orig_h * scale))
            return image.resize(new_size, Image.Resampling.LANCZOS), scale
        return image, 1.0


class FallbackInputController:
    """Resilient input controller wrapping PyAutoGUI with coordinate validation."""

    def __init__(self, action_delay: float = 0.5) -> None:
        self.action_delay = action_delay
        self.scale_factor = 1.0
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = action_delay

    def set_scale_factor(self, factor: float) -> None:
        """Set scaling factor for API coordinates to screen coordinates."""
        if factor > 0:
            self.scale_factor = factor

    def scale_coordinates(self, x: int | float, y: int | float) -> tuple[int, int]:
        """Convert API coordinates to physical screen coordinates."""
        return int(round(x * self.scale_factor)), int(round(y * self.scale_factor))

    def _validate_coordinates(self, x: int, y: int) -> tuple[int, int]:
        """Clamp coordinates within visible screen boundary."""
        screen_w, screen_h = pyautogui.size()
        clamped_x = max(0, min(x, screen_w - 1))
        clamped_y = max(0, min(y, screen_h - 1))
        return clamped_x, clamped_y

    def click(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        """Click mouse button at given or current coordinates."""
        if x is not None and y is not None:
            sx, sy = self.scale_coordinates(x, y)
            cx, cy = self._validate_coordinates(sx, sy)
            pyautogui.click(cx, cy, button=button)
        else:
            pyautogui.click(button=button)

    def double_click(self, x: int | None = None, y: int | None = None) -> None:
        """Double click primary button."""
        if x is not None and y is not None:
            sx, sy = self.scale_coordinates(x, y)
            cx, cy = self._validate_coordinates(sx, sy)
            pyautogui.doubleClick(cx, cy)
        else:
            pyautogui.doubleClick()

    def right_click(self, x: int | None = None, y: int | None = None) -> None:
        """Right click mouse."""
        self.click(x, y, button="right")

    def middle_click(self, x: int | None = None, y: int | None = None) -> None:
        """Middle click mouse."""
        self.click(x, y, button="middle")

    def triple_click(self, x: int | None = None, y: int | None = None) -> None:
        """Triple click primary button."""
        if x is not None and y is not None:
            sx, sy = self.scale_coordinates(x, y)
            cx, cy = self._validate_coordinates(sx, sy)
            pyautogui.tripleClick(cx, cy)
        else:
            pyautogui.tripleClick()

    def move_to(self, x: int, y: int) -> None:
        """Move cursor to coordinates."""
        sx, sy = self.scale_coordinates(x, y)
        cx, cy = self._validate_coordinates(sx, sy)
        pyautogui.moveTo(cx, cy)

    def drag(self, end_x: int, end_y: int, start_x: int | None = None, start_y: int | None = None) -> None:
        """Drag mouse to destination coordinates."""
        if start_x is not None and start_y is not None:
            sx, sy = self.scale_coordinates(start_x, start_y)
            cx, cy = self._validate_coordinates(sx, sy)
            pyautogui.moveTo(cx, cy)
        ex, ey = self.scale_coordinates(end_x, end_y)
        cex, cey = self._validate_coordinates(ex, ey)
        pyautogui.dragTo(cex, cey, button="left")

    def scroll(self, x: int | None = None, y: int | None = None, clicks: int = 0) -> None:
        """Scroll vertical wheel."""
        if x is not None and y is not None:
            sx, sy = self.scale_coordinates(x, y)
            cx, cy = self._validate_coordinates(sx, sy)
            pyautogui.moveTo(cx, cy)
        pyautogui.scroll(clicks)

    def type_text(self, text: str, interval: float = 0.02) -> None:
        """Type characters with keyboard."""
        if not text:
            return
        norm = text.strip().lower()
        if norm in ("enter", "return"):
            self.press_key("enter")
            return
        if norm in ("tab", "esc", "escape", "backspace", "space", "win", "windows", "up", "down", "left", "right"):
            self.press_key(norm)
            return
        press_enter_at_end = False
        if text.endswith("\n") or text.endswith("\r\n"):
            text = text.rstrip("\r\n")
            press_enter_at_end = True
        pyautogui.write(text, interval=interval)
        if press_enter_at_end:
            self.press_key("enter")

    def press_key(self, key: str) -> None:
        """Press a keyboard key or key combination."""
        # Normalize keys like 'Return' -> 'enter', 'ctrl+c' -> hotkey
        key_lower = key.lower()
        if "+" in key_lower:
            parts = [k.strip() for k in key_lower.split("+")]
            pyautogui.hotkey(*parts)
        else:
            key_map = {
                "return": "enter",
                "backspace": "backspace",
                "escape": "esc",
                "super": "win",
                "meta": "win",
            }
            normalized = key_map.get(key_lower, key_lower)
            pyautogui.press(normalized)

    def hotkey(self, *keys: str) -> None:
        """Press multiple keys concurrently."""
        pyautogui.hotkey(*keys)

    def emergency_stop(self) -> None:
        """Trigger emergency halt by slamming cursor to top-left corner."""
        try:
            pyautogui.moveTo(0, 0)
        except Exception:
            pass


class AutoMateAgent:
    """The central brain orchestrating the desktop automation control loop."""

    def __init__(
        self,
        config: Any = None,
        screen: Any = None,
        controller: Any = None,
        anthropic_client: anthropic.Anthropic | None = None,
        provider: BaseAIProvider | None = None,
    ) -> None:
        ensure_windows_desktop_and_dpi()
        # Load configuration
        if config is not None:
            self.config = config
        elif get_config is not None:
            self.config = get_config()
        else:
            # Fallback simple config
            class SimpleConfig:
                provider = os.environ.get("PROVIDER", "cloudflare")
                cloudflare_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
                cloudflare_api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
                cloudflare_model = os.environ.get("CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-11b-vision-instruct")
                anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
                model = os.environ.get("AUTOMATE_MODEL", "claude-sonnet-4-20250514")
                max_steps = int(os.environ.get("AUTOMATE_MAX_STEPS", 50))
                screenshot_interval = float(os.environ.get("AUTOMATE_SCREENSHOT_INTERVAL", 1.0))
                safety_mode = True
                display_width = 1920
                display_height = 1080
                action_delay = 0.5
                duration_hours = 0.0
                keep_awake = True
                loop_interval = 1.5
                log_level = "INFO"

            self.config = SimpleConfig()

        # Initialize screen capture
        if screen is not None:
            self.screen = screen
        elif ScreenCapture is not None:
            try:
                self.screen = ScreenCapture()
            except Exception as e:
                logger.warning(f"Error initializing primary ScreenCapture: {e}; using fallback")
                self.screen = FallbackScreenCapture()
        else:
            self.screen = FallbackScreenCapture()

        # Initialize input controller
        delay = getattr(self.config, "action_delay", 0.5)
        if controller is not None:
            self.controller = controller
        elif InputController is not None:
            try:
                self.controller = InputController(action_delay=delay)
            except Exception as e:
                logger.warning(f"Error initializing primary InputController: {e}; using fallback")
                self.controller = FallbackInputController(action_delay=delay)
        else:
            self.controller = FallbackInputController(action_delay=delay)

        # Initialize Human Input Engine and Desktop Tools Suite
        try:
            from automate.human_input import HumanInputEngine
            from automate.tools import DesktopToolSuite
            self.human_input = HumanInputEngine(action_delay=delay)
            self.tools = DesktopToolSuite(human_engine=self.human_input)
        except Exception as e:
            logger.debug(f"Notice: HumanInputEngine/ToolsSuite initialized with fallback: {e}")
            self.human_input = None
            self.tools = None

        # Initialize AI Provider
        if provider is not None:
            self.provider = provider
        elif anthropic_client is not None:
            ant_key = str(getattr(self.config, "anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")).strip()
            self.provider = AnthropicProvider(
                api_key=ant_key,
                model=str(getattr(self.config, "model", "claude-sonnet-4-20250514")),
            )
            self.provider.client = anthropic_client
        else:
            chosen_provider = str(getattr(self.config, "provider", "auto")).lower()
            cf_token = str(getattr(self.config, "cloudflare_api_token", "") or os.environ.get("CLOUDFLARE_API_TOKEN", "")).strip()
            ant_key = str(getattr(self.config, "anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")).strip()

            if chosen_provider == "anthropic" or (ant_key and not cf_token):
                self.provider = AnthropicProvider(
                    api_key=ant_key,
                    model=str(getattr(self.config, "model", "claude-sonnet-4-20250514")),
                )
            elif chosen_provider == "cloudflare" or cf_token:
                cf_acc = str(getattr(self.config, "cloudflare_account_id", "") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")).strip()
                cf_mod = str(getattr(self.config, "cloudflare_model", "@cf/meta/llama-3.2-11b-vision-instruct"))
                self.provider = CloudflareAIProvider(
                    account_id=cf_acc,
                    api_token=cf_token,
                    model=cf_mod,
                )
            else:
                # Default fallback when neither key is provided
                self.provider = AnthropicProvider(
                    api_key=ant_key,
                    model=str(getattr(self.config, "model", "claude-sonnet-4-20250514")),
                )

        # Preserve self.client for backwards compatibility with tests / Claude direct mode
        if anthropic_client is not None:
            self.client = anthropic_client
        elif isinstance(self.provider, AnthropicProvider):
            self.client = self.provider.client
        else:
            ant_key = str(getattr(self.config, "anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")).strip()
            self.client = anthropic.Anthropic(api_key=ant_key) if ant_key else None

        # Tracking state
        self.action_history: list[dict[str, Any]] = []
        self.action_logger = ActionLogger()
        self.console = console
        self._stopped = False

    def stop(self) -> None:
        """Trigger emergency stop."""
        self._stopped = True
        logger.warning("Emergency stop signaled to AutoMateAgent.")
        if hasattr(self.controller, "emergency_stop"):
            self.controller.emergency_stop()

    def _get_computer_tool_definition(self) -> dict[str, Any]:
        """Construct the Anthropic Computer Use tool definition."""
        w, h = getattr(self.config, "display_width", 1920), getattr(self.config, "display_height", 1080)
        if hasattr(self.screen, "get_screen_size"):
            try:
                sw, sh = self.screen.get_screen_size()
                if sw > 0 and sh > 0:
                    w, h = sw, sh
            except Exception:
                pass

        # Use latest computer_20250124 tool specification
        model_name = getattr(self.config, "model", "")
        tool_type = "computer_20241022" if "20241022" in model_name else "computer_20250124"

        return {
            "type": tool_type,
            "name": "computer",
            "display_width_px": int(w),
            "display_height_px": int(h),
            "display_number": 1,
        }

    def _get_beta_name(self) -> str:
        """Determine appropriate beta header value based on tool version."""
        tool_def = self._get_computer_tool_definition()
        if tool_def["type"] == "computer_20241022":
            return "computer-use-2024-10-22"
        return "computer-use-2025-01-24"

    def _execute_computer_action(self, tool_name: str, tool_input: dict[str, Any]) -> ActionResult:
        """Route computer tool action to the InputController and ScreenCapture."""
        action = tool_input.get("action", "")
        logger.info(f"Executing computer action: [bold cyan]{action}[/bold cyan] | Input: {tool_input}")

        start_time = time.perf_counter()
        try:
            if action == "screenshot":
                img = self.screen.capture()
                b64 = self.screen.to_base64(img)
                dur = (time.perf_counter() - start_time) * 1000
                return ActionResult(success=True, screenshot=b64)

            elif action in ("left_click", "click"):
                coord = tool_input.get("coordinate")
                if coord:
                    self.controller.click(coord[0], coord[1], button="left")
                else:
                    self.controller.click(button="left")

            elif action == "right_click":
                coord = tool_input.get("coordinate")
                if coord:
                    self.controller.right_click(coord[0], coord[1])
                else:
                    self.controller.right_click()

            elif action == "middle_click":
                coord = tool_input.get("coordinate")
                if coord:
                    self.controller.middle_click(coord[0], coord[1])
                else:
                    self.controller.middle_click()

            elif action == "double_click":
                coord = tool_input.get("coordinate")
                if coord:
                    self.controller.double_click(coord[0], coord[1])
                else:
                    self.controller.double_click()

            elif action == "triple_click":
                coord = tool_input.get("coordinate")
                if coord:
                    if hasattr(self.controller, "triple_click"):
                        self.controller.triple_click(coord[0], coord[1])
                    else:
                        self.controller.click(coord[0], coord[1])
                        self.controller.double_click(coord[0], coord[1])
                else:
                    if hasattr(self.controller, "triple_click"):
                        self.controller.triple_click()
                    else:
                        self.controller.double_click()

            elif action == "mouse_move":
                coord = tool_input.get("coordinate")
                if not coord:
                    raise ValueError("mouse_move requires 'coordinate' [x, y]")
                self.controller.move_to(coord[0], coord[1])

            elif action in ("left_click_drag", "drag"):
                coord = tool_input.get("coordinate")
                if not coord:
                    raise ValueError("drag requires destination 'coordinate' [x, y]")
                start_coord = tool_input.get("start_coordinate")
                start_x = start_coord[0] if start_coord else None
                start_y = start_coord[1] if start_coord else None
                self.controller.drag(coord[0], coord[1], start_x=start_x, start_y=start_y)

            elif action == "type":
                text = tool_input.get("text", "")
                self.controller.type_text(text)

            elif action in ("key", "hotkey"):
                key = tool_input.get("text") or tool_input.get("key")
                if not key:
                    raise ValueError("key action requires 'text' or 'key' parameter")
                self.controller.press_key(key)

            elif action == "cursor_position":
                pos = pyautogui.position()
                dur = (time.perf_counter() - start_time) * 1000
                return ActionResult(
                    success=True,
                    cursor_position=(pos.x, pos.y),
                    output=f"Cursor position: x={pos.x}, y={pos.y}",
                )

            elif action == "wait":
                duration = float(tool_input.get("duration", 1.0))
                time.sleep(duration)

            elif action in ("scroll", "wheel"):
                clicks = tool_input.get("clicks") or tool_input.get("delta_y") or -5
                coord = tool_input.get("coordinate")
                x = coord[0] if coord else None
                y = coord[1] if coord else None
                self.controller.scroll(x=x, y=y, clicks=int(clicks))

            else:
                logger.warning(f"Unknown action '{action}', executing as no-op")

            # Post-action pause and screenshot capture for Claude perception
            delay = getattr(self.config, "action_delay", 0.3)
            time.sleep(delay)
            post_img = self.screen.capture()
            b64_post = self.screen.to_base64(post_img)

            return ActionResult(success=True, screenshot=b64_post)

        except Exception as e:
            logger.error(f"Action execution error: {e}")
            # Try to grab screenshot even on error
            b64_err = None
            try:
                b64_err = self.screen.to_base64(self.screen.capture())
            except Exception:
                pass
            return ActionResult(success=False, error=str(e), screenshot=b64_err)

    def _build_tool_result(self, tool_use_id: str, action_result: ActionResult) -> dict[str, Any]:
        """Build the tool result message payload for Claude Computer Use API."""
        content: list[dict[str, Any]] = []

        if action_result.screenshot:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": action_result.screenshot,
                },
            })

        if action_result.error:
            content.append({
                "type": "text",
                "text": f"Action failed with error: {action_result.error}",
            })
        elif action_result.output:
            content.append({
                "type": "text",
                "text": action_result.output,
            })
        elif not action_result.screenshot:
            content.append({
                "type": "text",
                "text": "Action executed successfully.",
            })

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": not action_result.success,
        }

    def _execute_provider_action(self, action: ProviderAction) -> ActionResult:
        """Execute a normalized ProviderAction on the physical screen."""
        ensure_windows_desktop_and_dpi()
        act_type = action.action_type.lower().strip()
        logger.info(f"Executing action: [bold magenta]{act_type}[/bold magenta] | Params: {action.raw_params}")
        try:
            # 1. Tools suite execution
            if act_type in ("open_url", "browse"):
                url = (action.raw_params.get("url") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.open_url(url)
                else:
                    webbrowser.open(url)

            elif act_type in ("launch", "launch_app", "open_app"):
                app = (action.raw_params.get("app") if action.raw_params else None) or (action.raw_params.get("app_name") if action.raw_params else None) or action.text or ""
                args = (action.raw_params.get("args") if action.raw_params else "") or ""
                if self.tools:
                    self.tools.launch_app(app, args=args)
                else:
                    subprocess.Popen(app, shell=True)

            elif act_type in ("find_and_open_app", "start_menu"):
                query = (action.raw_params.get("query") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.find_and_open_app(query)
                elif self.human_input:
                    self.human_input.press_key("win")
                    time.sleep(0.5)
                    self.human_input.human_type(query)
                    self.human_input.press_key("enter")

            elif act_type in ("run_command", "cmd", "shell"):
                cmd = (action.raw_params.get("command") if action.raw_params else None) or action.text or ""
                if self.tools:
                    out = self.tools.run_command(cmd)
                    logger.info(f"Command output: {out}")
                else:
                    subprocess.run(cmd, shell=True)

            elif act_type in ("focus_window", "focus", "switch_window"):
                kw = (action.raw_params.get("keyword") if action.raw_params else None) or (action.raw_params.get("title") if action.raw_params else None) or action.text or ""
                if self.tools:
                    res = self.tools.focus_window(kw)
                    logger.info(f"Focus window result: {res}")
                time.sleep(0.5)

            elif act_type in ("new_tab", "new_browser_tab"):
                url = (action.raw_params.get("url") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.new_tab(url)
                elif self.human_input:
                    self.human_input.hotkey("ctrl", "t")

            elif act_type in ("close_tab", "close_browser_tab"):
                if self.tools:
                    self.tools.close_tab()
                elif self.human_input:
                    self.human_input.hotkey("ctrl", "w")

            elif act_type in ("switch_tab", "next_tab", "prev_tab"):
                direction = "prev" if "prev" in act_type else ((action.raw_params.get("direction") if action.raw_params else "next") or "next")
                if self.tools:
                    self.tools.switch_tab(direction)
                elif self.human_input:
                    if direction == "prev":
                        self.human_input.hotkey("ctrl", "shift", "tab")
                    else:
                        self.human_input.hotkey("ctrl", "tab")

            elif act_type in ("search_youtube", "youtube"):
                query = (action.raw_params.get("query") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.search_youtube(query)

            elif act_type in ("open_file_explorer", "open_explorer", "explorer"):
                path = (action.raw_params.get("path") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.open_file_explorer(path)

            elif act_type in ("create_directory", "mkdir", "create_folder"):
                path = (action.raw_params.get("path") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.create_directory(path)

            elif act_type in ("create_file", "write_file"):
                fpath = (action.raw_params.get("file_path") if action.raw_params else None) or (action.raw_params.get("path") if action.raw_params else None) or ""
                content = (action.raw_params.get("content") if action.raw_params else "") or action.text or ""
                if self.tools:
                    self.tools.create_file(fpath, content)

            elif act_type in ("open_in_vscode", "open_vscode", "vscode"):
                path = (action.raw_params.get("path") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.open_in_vscode(path)

            elif act_type in ("create_and_edit_python_file", "create_python_file", "code_python"):
                fname = (action.raw_params.get("file_name") if action.raw_params else None) or (action.raw_params.get("filename") if action.raw_params else None) or "script.py"
                content = (action.raw_params.get("code_content") if action.raw_params else None) or (action.raw_params.get("content") if action.raw_params else None) or ""
                directory = (action.raw_params.get("directory") if action.raw_params else "") or ""
                if self.tools:
                    self.tools.create_and_edit_python_file(fname, content, directory=directory)

            elif act_type in ("run_python", "execute_python"):
                fpath = (action.raw_params.get("file_path") if action.raw_params else None) or (action.raw_params.get("path") if action.raw_params else None) or action.text or ""
                if self.tools:
                    out = self.tools.run_python(fpath)
                    logger.info(f"Python script output: {out}")

            elif act_type in ("play_youtube_video", "play_youtube", "youtube_play"):
                video = (action.raw_params.get("video_title") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.play_youtube_video(video)

            elif act_type in ("toggle_youtube_playback", "toggle_playback", "pause_youtube", "resume_youtube"):
                if self.tools:
                    self.tools.toggle_youtube_playback()
                elif self.human_input:
                    self.human_input.press_key("k")

            elif act_type in ("next_youtube_video", "next_video", "skip_video"):
                if self.tools:
                    self.tools.next_youtube_video()
                elif self.human_input:
                    self.human_input.hotkey("shift", "n")

            elif act_type in ("close_app", "close_window", "exit_app"):
                app = (action.raw_params.get("app_name") if action.raw_params else None) or (action.raw_params.get("app") if action.raw_params else None) or action.text or ""
                if self.tools:
                    self.tools.close_app(app)
                elif self.human_input:
                    self.human_input.hotkey("alt", "f4")

            elif act_type in ("visual_create_folder", "create_folder_visual"):
                folder = (action.raw_params.get("folder_name") if action.raw_params else None) or action.text or "New Folder"
                if self.tools:
                    self.tools.visual_create_folder(folder)

            elif act_type in ("visual_code_editor", "write_code_visual"):
                code_text = (action.raw_params.get("code_text") if action.raw_params else None) or (action.raw_params.get("code") if action.raw_params else None) or ""
                fname = (action.raw_params.get("file_name") if action.raw_params else None) or "script.py"
                if self.tools:
                    self.tools.visual_code_editor(code_text, fname)

            # 2. Humanized physical mouse & keyboard actions
            elif act_type in ("left_click", "click"):
                if action.coordinate:
                    if self.human_input:
                        self.human_input.human_click(action.coordinate[0], action.coordinate[1], button="left")
                    else:
                        self.controller.click(action.coordinate[0], action.coordinate[1], button="left")
                else:
                    if self.human_input:
                        self.human_input.human_click(button="left")
                    else:
                        self.controller.click(button="left")

            elif act_type == "right_click":
                if action.coordinate:
                    if self.human_input:
                        self.human_input.human_click(action.coordinate[0], action.coordinate[1], button="right")
                    else:
                        self.controller.right_click(action.coordinate[0], action.coordinate[1])
                else:
                    if self.human_input:
                        self.human_input.human_click(button="right")
                    else:
                        self.controller.right_click()

            elif act_type == "double_click":
                if action.coordinate:
                    if self.human_input:
                        self.human_input.human_click(action.coordinate[0], action.coordinate[1], double=True)
                    else:
                        self.controller.double_click(action.coordinate[0], action.coordinate[1])
                else:
                    if self.human_input:
                        self.human_input.human_click(double=True)
                    else:
                        self.controller.double_click()

            elif act_type == "middle_click":
                if action.coordinate:
                    if self.human_input:
                        self.human_input.human_click(action.coordinate[0], action.coordinate[1], button="middle")
                    else:
                        self.controller.middle_click(action.coordinate[0], action.coordinate[1])
                else:
                    if self.human_input:
                        self.human_input.human_click(button="middle")
                    else:
                        self.controller.middle_click()

            elif act_type in ("drag", "left_click_drag"):
                if not action.coordinate:
                    raise ValueError("drag action requires coordinate")
                sx = action.start_coordinate[0] if action.start_coordinate else None
                sy = action.start_coordinate[1] if action.start_coordinate else None
                if self.human_input and sx is not None and sy is not None:
                    self.human_input.human_drag(sx, sy, action.coordinate[0], action.coordinate[1])
                else:
                    self.controller.drag(action.coordinate[0], action.coordinate[1], start_x=sx, start_y=sy)

            elif act_type in ("mouse_move", "move"):
                if not action.coordinate:
                    raise ValueError("mouse_move requires coordinate")
                if self.human_input:
                    self.human_input.human_move(action.coordinate[0], action.coordinate[1])
                else:
                    self.controller.move_to(action.coordinate[0], action.coordinate[1])

            elif act_type in ("type", "write"):
                text = action.text or ""
                norm = text.strip().lower()
                current_task = getattr(self, "_current_task", "").strip().lower()

                # Guard: if model mistakenly types the entire task instruction (e.g. "Open Chrome and search for...")
                if current_task and (norm == current_task or (norm.startswith("open ") and ("chrome" in norm or "browser" in norm))):
                    logger.warning(f"Detected task repetition hallucination in 'type' action: '{text}'. Redirecting to URL/App launch.")
                    if "weather" in norm or "search" in norm:
                        query = norm
                        for prefix in ("open chrome and search for ", "open chrome and search ", "search for ", "search "):
                            if prefix in query:
                                query = query.split(prefix, 1)[-1].strip()
                                break
                        if self.tools:
                            self.tools.open_url(f"https://www.google.com/search?q={query}")
                        else:
                            webbrowser.open(f"https://www.google.com/search?q={query}")
                        time.sleep(1.0)
                        return ActionResult(success=True)
                    elif "chrome" in norm:
                        if self.tools:
                            self.tools.launch_app("chrome")
                        return ActionResult(success=True)

                if norm in ("enter", "return"):
                    if self.human_input:
                        self.human_input.press_key("enter")
                    else:
                        self.controller.press_key("enter")
                elif norm in ("tab", "esc", "escape", "backspace", "space", "win", "windows", "up", "down", "left", "right"):
                    if self.human_input:
                        self.human_input.press_key(norm)
                    else:
                        self.controller.press_key(norm)
                elif text.endswith("\n") or text.endswith("\r\n"):
                    clean = text.rstrip("\r\n")
                    if self.human_input:
                        self.human_input.human_type(clean)
                        self.human_input.press_key("enter")
                    else:
                        self.controller.type_text(clean)
                        self.controller.press_key("enter")
                else:
                    if self.human_input:
                        self.human_input.human_type(text)
                    else:
                        self.controller.type_text(text)

            elif act_type in ("key", "press", "keypress"):
                k = action.key or action.text
                if k:
                    if self.human_input:
                        self.human_input.press_key(k)
                    else:
                        self.controller.press_key(k)

            elif act_type in ("hotkey", "shortcut"):
                keys = action.keys or ([action.key] if action.key else [])
                if keys:
                    if self.human_input:
                        self.human_input.hotkey(*keys)
                    else:
                        self.controller.hotkey(*keys)

            elif act_type == "scroll":
                clicks = action.clicks if action.clicks is not None else -5
                x = action.coordinate[0] if action.coordinate else None
                y = action.coordinate[1] if action.coordinate else None
                if self.human_input:
                    self.human_input.human_scroll(clicks=int(clicks), x=x, y=y)
                else:
                    self.controller.scroll(x=x, y=y, clicks=int(clicks))

            elif act_type in ("wait", "sleep"):
                time.sleep(action.duration if action.duration is not None else 1.0)

            else:
                logger.warning(f"Unrecognized provider action '{act_type}', skipping.")

            delay = getattr(self.config, "action_delay", 0.3)
            time.sleep(delay)
            return ActionResult(success=True)
        except Exception as e:
            logger.error(f"Error executing provider action: {e}")
            return ActionResult(success=False, error=str(e))

    def run_continuous(
        self,
        task: str,
        duration_hours: float = 0.0,
        max_cycles: Optional[int] = None,
        loop_interval: float = 1.5,
        keep_awake: bool = True,
    ) -> ContinuousStats:
        """Run AutoMate in continuous/overnight mode (e.g. for games, overnight tasks, 24/7)."""
        runner = ContinuousRunner(
            agent=self,
            task=task,
            duration_hours=duration_hours,
            max_cycles=max_cycles,
            loop_interval=loop_interval,
            keep_awake=keep_awake,
        )
        return runner.run()

    def _run_cloudflare(self, task: str) -> AgentResult:
        """Autonomous loop powered by Cloudflare Workers AI."""
        start_time = time.perf_counter()
        self._stopped = False
        self.action_history.clear()
        self.action_logger.clear()

        if not self.provider.is_configured():
            err_msg = (
                "Cloudflare AI is not configured. "
                "Please set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in your environment or .env file."
            )
            logger.error(err_msg)
            return AgentResult(
                success=False,
                steps_taken=0,
                final_message=err_msg,
                error=err_msg,
                total_duration_seconds=0.0,
            )

        max_steps = getattr(self.config, "max_steps", 50)
        cf_model = getattr(self.config, "cloudflare_model", "@cf/meta/llama-3.2-11b-vision-instruct")
        display_size = self.screen.get_screen_size()

        console.print(
            Panel(
                f"[bold green]Task:[/bold green] {task}\n"
                f"[bold magenta]Provider:[/bold magenta] Cloudflare Workers AI\n"
                f"[bold blue]Model:[/bold blue] {cf_model} | [bold blue]Max Steps:[/bold blue] {max_steps}\n"
                f"[bold blue]Display:[/bold blue] {display_size[0]}x{display_size[1]}",
                title="🤖 AutoMate Agent Starting (Cloudflare Workers AI)",
                border_style="magenta",
            )
        )

        self._current_task = task
        steps_taken = 0
        final_message = ""
        empty_action_streak = 0

        for step in range(1, max_steps + 1):
            if self._stopped:
                console.print("[bold red]Emergency stop triggered. Aborting agent loop.[/bold red]")
                return AgentResult(
                    success=False,
                    steps_taken=steps_taken,
                    action_history=self.action_history,
                    final_message="Execution aborted due to emergency stop.",
                    error="Emergency stop triggered.",
                    total_duration_seconds=time.perf_counter() - start_time,
                )

            steps_taken = step
            logger.info(f"--- Step {step}/{max_steps} (Cloudflare AI) ---")

            ensure_windows_desktop_and_dpi()
            # 1. Capture screen
            screen_img = self.screen.capture()
            b64 = self.screen.to_base64(screen_img)
            raw_bytes = self.screen.to_bytes(screen_img) if hasattr(self.screen, "to_bytes") else screen_img.tobytes()

            # 2. Query Cloudflare AI
            model_resp = self.provider.decide_next_step(
                task=task,
                screenshot_bytes=raw_bytes,
                screenshot_b64=b64,
                display_size=display_size,
                action_history=self.action_history,
                step_number=step,
            )

            if model_resp.error:
                err_text = f"Cloudflare AI failed: {model_resp.error}"
                logger.error(err_text)
                return AgentResult(
                    success=False,
                    steps_taken=steps_taken,
                    action_history=self.action_history,
                    final_message=err_text,
                    error=model_resp.error,
                    total_duration_seconds=time.perf_counter() - start_time,
                )

            # Display thought
            if model_resp.thought:
                console.print(
                    Panel(
                        Text(model_resp.thought, style="italic"),
                        title=f"🧠 Cloudflare AI (Step {step})",
                        border_style="magenta",
                    )
                )
                final_message = model_resp.thought

            # If task marked complete
            if model_resp.is_finished:
                logger.info("Task completed: Cloudflare AI signaled completion.")
                return AgentResult(
                    success=True,
                    steps_taken=steps_taken,
                    action_history=self.action_history,
                    final_message=final_message or "Task completed successfully.",
                    total_duration_seconds=time.perf_counter() - start_time,
                )

            # If no actions returned, handle empty streak instead of prematurely quitting
            if not model_resp.actions:
                empty_action_streak += 1
                logger.warning(
                    f"Step {step}: Cloudflare AI returned no actions (streak: {empty_action_streak}/3)."
                )
                if empty_action_streak >= 3:
                    logger.warning("Terminating task after 3 consecutive empty action responses.")
                    break
                time.sleep(1.0)
                continue
            else:
                empty_action_streak = 0

            # Execute actions
            for act in model_resp.actions:
                if self._stopped:
                    break
                act_start = time.perf_counter()
                res = self._execute_provider_action(act)
                dur_ms = (time.perf_counter() - act_start) * 1000

                rec = self.action_logger.log_action(
                    step=step,
                    action_type=act.action_type,
                    params=act.raw_params,
                    success=res.success,
                    error=res.error,
                    duration_ms=dur_ms,
                )
                self.action_history.append(rec.to_dict())

        warn_msg = f"Task reached maximum allowed steps ({max_steps}) without finishing."
        logger.warning(warn_msg)
        return AgentResult(
            success=False,
            steps_taken=steps_taken,
            action_history=self.action_history,
            final_message=final_message or warn_msg,
            error=warn_msg,
            total_duration_seconds=time.perf_counter() - start_time,
        )

    def run(self, task: str) -> AgentResult:
        """Run the main autonomous execution loop for the given task."""
        # Branch to Cloudflare loop if provider is Cloudflare
        if isinstance(self.provider, CloudflareAIProvider):
            return self._run_cloudflare(task)

        start_time = time.perf_counter()
        self._stopped = False
        self.action_history.clear()
        self.action_logger.clear()

        # Validate Anthropic API client
        if self.client is None:
            err_msg = (
                "Anthropic API key is not configured. "
                "Please set ANTHROPIC_API_KEY environment variable or pass it to AutoMateAgent."
            )
            logger.error(err_msg)
            return AgentResult(
                success=False,
                steps_taken=0,
                final_message=err_msg,
                error=err_msg,
                total_duration_seconds=0.0,
            )

        max_steps = getattr(self.config, "max_steps", 50)
        model = getattr(self.config, "model", "claude-sonnet-4-20250514")
        tool_definition = self._get_computer_tool_definition()
        beta_name = self._get_beta_name()

        console.print(
            Panel(
                f"[bold green]Task:[/bold green] {task}\n"
                f"[bold blue]Model:[/bold blue] {model} | [bold blue]Max Steps:[/bold blue] {max_steps}\n"
                f"[bold blue]Display:[/bold blue] {tool_definition['display_width_px']}x{tool_definition['display_height_px']}",
                title="🤖 AutoMate Agent Starting",
                border_style="cyan",
            )
        )

        # 1. Take initial screenshot
        logger.info("Capturing initial desktop screenshot...")
        initial_image = self.screen.capture()
        initial_b64 = self.screen.to_base64(initial_image)

        # 2. Setup initial conversation
        system_prompt = (
            "You are AutoMate, an intelligent Windows desktop automation agent. "
            "You perceive the screen through screenshots and accomplish tasks using the 'computer' tool. "
            "Always inspect the visual context carefully before taking action. "
            "When the task is completely finished, provide a concise summary of what was accomplished "
            "without calling any more tools."
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Task: {task}\n\nHere is the initial screenshot of the desktop. Please proceed.",
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": initial_b64,
                        },
                    },
                ],
            }
        ]

        steps_taken = 0
        final_message = ""

        # 3. Main Agent Loop
        for step in range(1, max_steps + 1):
            if self._stopped:
                console.print("[bold red]Emergency stop triggered. Aborting agent loop.[/bold red]")
                return AgentResult(
                    success=False,
                    steps_taken=steps_taken,
                    action_history=self.action_history,
                    final_message="Execution aborted due to emergency stop.",
                    error="Emergency stop triggered.",
                    total_duration_seconds=time.perf_counter() - start_time,
                )

            steps_taken = step
            logger.info(f"--- Step {step}/{max_steps} ---")

            # Call Claude with computer use tool
            try:
                response = self._call_claude(
                    messages=messages,
                    system=system_prompt,
                    tools=[tool_definition],
                    model=model,
                    beta_name=beta_name,
                )
            except Exception as e:
                err_text = f"Anthropic API call failed: {e}"
                logger.error(err_text)
                return AgentResult(
                    success=False,
                    steps_taken=steps_taken,
                    action_history=self.action_history,
                    final_message=err_text,
                    error=str(e),
                    total_duration_seconds=time.perf_counter() - start_time,
                )

            # Record assistant turn in messages
            # Convert response content to serializable block dicts or keep response objects
            messages.append({"role": "assistant", "content": response.content})

            # Check assistant content blocks
            tool_use_blocks = []
            text_blocks = []

            for block in response.content:
                if block.type == "text":
                    text_blocks.append(block.text)
                elif block.type == "tool_use":
                    tool_use_blocks.append(block)

            # Display agent thoughts/plan
            if text_blocks:
                thought = "\n".join(text_blocks).strip()
                if thought:
                    console.print(Panel(Text(thought, style="italic"), title=f"🧠 Claude (Step {step})", border_style="blue"))
                    final_message = thought

            # If no tools called, Claude considers the task done (or reached an end turn)
            if not tool_use_blocks:
                logger.info("Task completed: Claude completed turn without requesting tools.")
                return AgentResult(
                    success=True,
                    steps_taken=steps_taken,
                    action_history=self.action_history,
                    final_message=final_message,
                    total_duration_seconds=time.perf_counter() - start_time,
                )

            # Process tool uses
            tool_results = []
            for tool_use in tool_use_blocks:
                tool_name = tool_use.name
                tool_input = tool_use.input
                tool_id = tool_use.id

                act_start = time.perf_counter()
                action_res = self._execute_computer_action(tool_name, tool_input)
                dur_ms = (time.perf_counter() - act_start) * 1000

                # Log and store
                rec = self.action_logger.log_action(
                    step=step,
                    action_type=tool_input.get("action", tool_name),
                    params=tool_input,
                    success=action_res.success,
                    error=action_res.error,
                    duration_ms=dur_ms,
                )
                self.action_history.append(rec.to_dict())

                # Build tool result payload
                tool_result_payload = self._build_tool_result(tool_id, action_res)
                tool_results.append(tool_result_payload)

            # Append user response with all tool results for this step
            messages.append({
                "role": "user",
                "content": tool_results,
            })

        # Max steps exceeded
        warn_msg = f"Task reached maximum allowed steps ({max_steps}) without finishing."
        logger.warning(warn_msg)
        return AgentResult(
            success=False,
            steps_taken=steps_taken,
            action_history=self.action_history,
            final_message=final_message or warn_msg,
            error=warn_msg,
            total_duration_seconds=time.perf_counter() - start_time,
        )

    def _call_claude(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
        model: str,
        beta_name: str,
    ) -> Any:
        """Helper to invoke Claude messages API supporting both beta client and extra headers."""
        try:
            # First try the official beta endpoint
            return self.client.beta.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
                betas=[beta_name],
            )
        except (AttributeError, TypeError):
            # Fallback to standard messages with extra_headers
            return self.client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
                extra_headers={"anthropic-beta": beta_name},
            )
