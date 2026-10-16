"""Mouse and keyboard input controller for AutoMate.

Executes low-level input operations via PyAutoGUI with failsafe protection,
coordinate scaling between API representations and physical displays,
safety boundary validation, and Rich console audit logging.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import pyautogui
import pyperclip
from rich.console import Console

from automate.screen import ensure_windows_desktop_and_dpi

console = Console()


class CoordinateOutOfBoundsError(ValueError):
    """Raised when coordinates fall outside the physical screen boundaries."""


# Standardize key naming between Anthropic / web conventions and PyAutoGUI
KEY_MAPPING: Dict[str, str] = {
    "return": "enter",
    "enter": "enter",
    "backspace": "backspace",
    "tab": "tab",
    "escape": "esc",
    "esc": "esc",
    "control": "ctrl",
    "ctrl": "ctrl",
    "control_l": "ctrlleft",
    "control_r": "ctrlright",
    "shift": "shift",
    "shift_l": "shiftleft",
    "shift_r": "shiftright",
    "alt": "alt",
    "alt_l": "altleft",
    "alt_r": "altright",
    "cmd": "win",
    "command": "win",
    "super": "win",
    "win": "win",
    "windows": "win",
    "page_down": "pagedown",
    "pagedown": "pagedown",
    "page_up": "pageup",
    "pageup": "pageup",
    "arrow_up": "up",
    "up": "up",
    "arrow_down": "down",
    "down": "down",
    "arrow_left": "left",
    "left": "left",
    "arrow_right": "right",
    "right": "right",
    "delete": "delete",
    "del": "delete",
    "space": "space",
    "spacebar": "space",
    "home": "home",
    "end": "end",
    "insert": "insert",
    "caps_lock": "capslock",
    "capslock": "capslock",
}


class InputController:
    """Controls mouse and keyboard inputs with safety guardrails and coordinate scaling."""

    def __init__(
        self,
        action_delay: float = 0.5,
        safety_mode: bool = True,
        scale_factor: float = 1.0,
    ) -> None:
        """Initialize InputController.

        Args:
            action_delay: Delay in seconds to pause after each action.
            safety_mode: If True, enforces strict coordinate checks and PyAutoGUI failsafe.
            scale_factor: Coordinate scale factor for scaling API coordinates to screen.
        """
        ensure_windows_desktop_and_dpi()

        self.action_delay = max(0.0, action_delay)
        self.safety_mode = safety_mode
        self.scale_factor = scale_factor if scale_factor > 0 else 1.0

        # PyAutoGUI configurations
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05

        # Check if cursor is currently parked at (0, 0), which would trip FailSafeException
        try:
            pos = pyautogui.position()
            if pos.x == 0 and pos.y == 0:
                pyautogui.FAILSAFE = False
                pyautogui.moveTo(200, 200, duration=0)
                pyautogui.FAILSAFE = True
        except Exception:
            pass

        console.log(
            f"[bold cyan][InputController][/bold cyan] Initialized "
            f"(scale_factor={self.scale_factor:.4f}, safety_mode={self.safety_mode}, delay={self.action_delay}s)"
        )

    def set_scale_factor(self, factor: float) -> None:
        """Set scale factor used to map API image coordinates to real screen coordinates.

        Args:
            factor: Positive scale factor (e.g. 0.6667 if API image is scaled to 2/3).
        """
        if factor <= 0:
            raise ValueError(f"Scale factor must be positive, got {factor}")
        self.scale_factor = factor
        console.log(f"[bold cyan][InputController][/bold cyan] Scale factor updated to {factor:.4f}")

    def get_screen_bounds(self) -> Tuple[int, int]:
        """Get the current screen dimensions (width, height) in physical pixels."""
        size = pyautogui.size()
        return size.width, size.height

    def _validate_coordinates(self, x: int, y: int, clamp: bool = False) -> Tuple[int, int]:
        """Validate that coordinates reside within the physical display bounds.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            clamp: If True and safety_mode is False, clamp rather than raise.

        Returns:
            Tuple[int, int]: Validated (and optionally clamped) (x, y) coordinates.

        Raises:
            CoordinateOutOfBoundsError: If coordinates exceed display bounds and cannot be clamped.
        """
        width, height = self.get_screen_bounds()

        if 0 <= x < width and 0 <= y < height:
            return x, y

        if clamp or not self.safety_mode:
            clamped_x = max(0, min(x, width - 1))
            clamped_y = max(0, min(y, height - 1))
            console.log(
                f"[yellow][InputController][/yellow] Clamped out-of-bounds coords ({x}, {y}) to ({clamped_x}, {clamped_y})"
            )
            return clamped_x, clamped_y

        raise CoordinateOutOfBoundsError(
            f"Coordinates ({x}, {y}) fall outside physical screen boundaries ({width}x{height})"
        )

    def scale_coordinates(self, x: int, y: int) -> Tuple[int, int]:
        """Map API coordinates back to physical screen coordinates.

        Formula: real_coord = round(api_coord / scale_factor)

        Args:
            x: API X coordinate.
            y: API Y coordinate.

        Returns:
            Tuple[int, int]: Screen (x, y) coordinates.
        """
        real_x = int(round(x / self.scale_factor))
        real_y = int(round(y / self.scale_factor))
        return self._validate_coordinates(real_x, real_y)

    def emergency_stop(self) -> None:
        """Trigger emergency stop failsafe by moving cursor to top-left corner."""
        console.log("[bold red]*** EMERGENCY STOP TRIGGERED: Slamming mouse to corner (0,0) ***[/bold red]")
        try:
            pyautogui.moveTo(0, 0, duration=0)
        except pyautogui.FailSafeException:
            console.log("[bold red]PyAutoGUI FailSafeException successfully tripped.[/bold red]")
            raise

    # -------------------------------------------------------------------------
    # Mouse Operations
    # -------------------------------------------------------------------------

    def get_cursor_position(self) -> Tuple[int, int]:
        """Return the current cursor position in physical screen coordinates."""
        pos = pyautogui.position()
        return pos.x, pos.y

    def move_to(self, x: int, y: int, duration: float = 0.1) -> Tuple[int, int]:
        """Move cursor to API coordinates (x, y).

        Args:
            x: Target API X coordinate.
            y: Target API Y coordinate.
            duration: Movement duration in seconds.

        Returns:
            Tuple[int, int]: Target physical coordinates (x, y).
        """
        real_x, real_y = self.scale_coordinates(x, y)
        console.log(f"[bold cyan][InputController][/bold cyan] Move to API ({x}, {y}) -> Screen ({real_x}, {real_y})")
        pyautogui.moveTo(real_x, real_y, duration=duration)
        time.sleep(self.action_delay)
        return real_x, real_y

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
    ) -> Tuple[int, int]:
        """Perform a mouse click at target coordinates or current position.

        Args:
            x: Optional API X coordinate.
            y: Optional API Y coordinate.
            button: 'left', 'right', or 'middle'.

        Returns:
            Tuple[int, int]: Coordinates clicked in physical pixels.
        """
        if x is not None and y is not None:
            real_x, real_y = self.scale_coordinates(x, y)
            console.log(
                f"[bold cyan][InputController][/bold cyan] [green]CLICK[/green] "
                f"button='{button}' at API ({x}, {y}) -> Screen ({real_x}, {real_y})"
            )
            pyautogui.click(real_x, real_y, button=button)
        else:
            real_x, real_y = self.get_cursor_position()
            console.log(
                f"[bold cyan][InputController][/bold cyan] [green]CLICK[/green] "
                f"button='{button}' at current pos Screen ({real_x}, {real_y})"
            )
            pyautogui.click(button=button)

        time.sleep(self.action_delay)
        return real_x, real_y

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Tuple[int, int]:
        """Perform a left double-click at target coordinates or current position."""
        if x is not None and y is not None:
            real_x, real_y = self.scale_coordinates(x, y)
            console.log(
                f"[bold cyan][InputController][/bold cyan] [green]DOUBLE CLICK[/green] "
                f"at API ({x}, {y}) -> Screen ({real_x}, {real_y})"
            )
            pyautogui.doubleClick(real_x, real_y)
        else:
            real_x, real_y = self.get_cursor_position()
            console.log(
                f"[bold cyan][InputController][/bold cyan] [green]DOUBLE CLICK[/green] "
                f"at current pos Screen ({real_x}, {real_y})"
            )
            pyautogui.doubleClick()

        time.sleep(self.action_delay)
        return real_x, real_y

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Tuple[int, int]:
        """Perform a right-click at target coordinates or current position."""
        return self.click(x, y, button="right")

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
        button: str = "left",
    ) -> None:
        """Drag from start coordinates to end coordinates.

        Args:
            start_x: API start X coordinate.
            start_y: API start Y coordinate.
            end_x: API end X coordinate.
            end_y: API end Y coordinate.
            duration: Drag duration in seconds.
            button: Mouse button to hold while dragging.
        """
        s_real_x, s_real_y = self.scale_coordinates(start_x, start_y)
        e_real_x, e_real_y = self.scale_coordinates(end_x, end_y)

        console.log(
            f"[bold cyan][InputController][/bold cyan] [yellow]DRAG[/yellow] "
            f"Screen ({s_real_x}, {s_real_y}) -> ({e_real_x}, {e_real_y}) button='{button}'"
        )
        pyautogui.moveTo(s_real_x, s_real_y)
        pyautogui.dragTo(e_real_x, e_real_y, duration=duration, button=button)
        time.sleep(self.action_delay)

    def scroll(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        clicks: int = 1,
    ) -> None:
        """Scroll vertical wheel clicks at optional coordinates.

        Positive clicks scroll up; negative clicks scroll down.

        Args:
            x: Optional API X coordinate to place cursor before scrolling.
            y: Optional API Y coordinate to place cursor before scrolling.
            clicks: Number of scroll ticks (positive=up, negative=down).
        """
        if x is not None and y is not None:
            real_x, real_y = self.scale_coordinates(x, y)
            pyautogui.moveTo(real_x, real_y)
            console.log(
                f"[bold cyan][InputController][/bold cyan] [blue]SCROLL[/blue] "
                f"ticks={clicks} at Screen ({real_x}, {real_y})"
            )
        else:
            console.log(f"[bold cyan][InputController][/bold cyan] [blue]SCROLL[/blue] ticks={clicks}")

        pyautogui.scroll(clicks)
        time.sleep(self.action_delay)

    # -------------------------------------------------------------------------
    # Keyboard Operations
    # -------------------------------------------------------------------------

    def _normalize_key(self, key: str) -> str:
        """Normalize key string to PyAutoGUI key names."""
        clean = key.strip().lower()
        return KEY_MAPPING.get(clean, clean)

    def type_text(self, text: str, interval: float = 0.02) -> None:
        """Type text string with typing interval.

        Handles Unicode/non-ASCII characters by pasting from clipboard when necessary.
        Also safely routes special keys (e.g. 'enter', 'tab', 'esc') to press_key if emitted as type.

        Args:
            text: String to type.
            interval: Delay in seconds between key presses.
        """
        if not text:
            return

        norm_text = text.strip().lower()
        if norm_text in ("enter", "return"):
            self.press_key("enter")
            return
        if norm_text in (
            "tab", "esc", "escape", "backspace", "space", "win", "windows", "up", "down", "left", "right"
        ):
            self.press_key(norm_text)
            return

        press_enter_at_end = False
        if text.endswith("\n") or text.endswith("\r\n"):
            text = text.rstrip("\r\n")
            press_enter_at_end = True

        console.log(f"[bold cyan][InputController][/bold cyan] [magenta]TYPE[/magenta] '{text}'")

        # Check if text contains non-ASCII or multi-byte characters
        is_ascii = all(ord(ch) < 128 for ch in text)

        if is_ascii:
            try:
                pyautogui.write(text, interval=interval)
            except Exception:
                pyperclip.copy(text)
                self.hotkey("ctrl", "v")
        else:
            # Use clipboard paste for unicode/emojis/special chars
            old_clip = None
            try:
                old_clip = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(text)
            self.hotkey("ctrl", "v")

            # Restore previous clipboard if possible
            if old_clip is not None:
                try:
                    time.sleep(0.05)
                    pyperclip.copy(old_clip)
                except Exception:
                    pass

        time.sleep(self.action_delay)

        if press_enter_at_end:
            self.press_key("enter")

    def press_key(self, key: str) -> None:
        """Press and release a single keyboard key.

        Args:
            key: Name of the key (e.g. 'enter', 'tab', 'backspace').
        """
        norm_key = self._normalize_key(key)
        console.log(f"[bold cyan][InputController][/bold cyan] [magenta]PRESS KEY[/magenta] '{norm_key}'")
        pyautogui.press(norm_key)
        time.sleep(self.action_delay)

    def hotkey(self, *keys: str) -> None:
        """Press a combination of keys together (e.g. 'ctrl', 'c').

        Args:
            *keys: Sequence of keys to press simultaneously.
        """
        norm_keys = [self._normalize_key(k) for k in keys if k]
        if not norm_keys:
            return
        console.log(f"[bold cyan][InputController][/bold cyan] [magenta]HOTKEY[/magenta] {' + '.join(norm_keys)}")
        pyautogui.hotkey(*norm_keys)
        time.sleep(self.action_delay)

    def key_down(self, key: str) -> None:
        """Hold down a keyboard key without releasing.

        Args:
            key: Name of the key.
        """
        norm_key = self._normalize_key(key)
        console.log(f"[bold cyan][InputController][/bold cyan] [dim]KEY DOWN[/dim] '{norm_key}'")
        pyautogui.keyDown(norm_key)

    def key_up(self, key: str) -> None:
        """Release a currently held keyboard key.

        Args:
            key: Name of the key.
        """
        norm_key = self._normalize_key(key)
        console.log(f"[bold cyan][InputController][/bold cyan] [dim]KEY UP[/dim] '{norm_key}'")
        pyautogui.keyUp(norm_key)
