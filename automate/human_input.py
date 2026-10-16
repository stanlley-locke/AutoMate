"""Human-like input engine for AutoMate.

Generates natural, humanized mouse movements using cubic Bézier curves,
ease-in/ease-out deceleration, micro-jitters, realistic click timing,
and human typing cadence with randomized inter-keystroke intervals.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import random
import sys
import time
from typing import List, Optional, Tuple

import pyautogui
import pyperclip
from rich.console import Console

from automate.screen import ensure_windows_desktop_and_dpi

console = Console()


def _bezier_point(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    """Calculate point on cubic Bézier curve at factor t (0 <= t <= 1)."""
    u = 1.0 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t

    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return x, y


def _ease_out_cubic(t: float) -> float:
    """Smooth deceleration curve mimicking human arm reaching target."""
    return 1.0 - math.pow(1.0 - t, 3)


class HumanInputEngine:
    """Delivers natural, organic human-like mouse movements and keyboard inputs."""

    def __init__(
        self,
        speed_factor: float = 1.0,
        enable_failsafe: bool = True,
        action_delay: float = 0.2,
    ) -> None:
        """Initialize HumanInputEngine.

        Args:
            speed_factor: Multiplier for movement speed (1.0 = normal human speed).
            enable_failsafe: Whether PyAutoGUI emergency stop is active.
            action_delay: Base delay after actions in seconds.
        """
        self.speed_factor = max(0.2, speed_factor)
        self.action_delay = max(0.0, action_delay)
        self.enable_failsafe = enable_failsafe

        ensure_windows_desktop_and_dpi()

        # Configure PyAutoGUI
        pyautogui.FAILSAFE = enable_failsafe
        pyautogui.PAUSE = 0.02

        # Nudge away from (0,0) corner if parked there
        self._prevent_initial_failsafe_lockout()

    def _prevent_initial_failsafe_lockout(self) -> None:
        """Move cursor away from (0,0) if parked there to avoid false failsafe trips."""
        try:
            pos = pyautogui.position()
            if pos.x == 0 and pos.y == 0:
                pyautogui.FAILSAFE = False
                self._win32_set_cursor(200, 200)
                pyautogui.FAILSAFE = self.enable_failsafe
        except Exception:
            pass

    def _win32_set_cursor(self, x: int, y: int) -> None:
        """Directly position hardware cursor via Win32 user32."""
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
            except Exception:
                pass

    def get_cursor_position(self) -> Tuple[int, int]:
        """Return current physical cursor position."""
        ensure_windows_desktop_and_dpi()
        pos = pyautogui.position()
        return int(pos.x), int(pos.y)

    def human_move(
        self,
        target_x: int,
        target_y: int,
        duration: Optional[float] = None,
        steps: int = 40,
    ) -> Tuple[int, int]:
        """Move mouse to target coordinates along a realistic human curved trajectory.

        Args:
            target_x: Target X coordinate in pixels.
            target_y: Target Y coordinate in pixels.
            duration: Total duration in seconds (computed organically if None).
            steps: Number of intermediate trajectory steps.

        Returns:
            Tuple[int, int]: Final cursor coordinates reached.
        """
        ensure_windows_desktop_and_dpi()
        start_x, start_y = self.get_cursor_position()

        # Distance calculation
        dist = math.hypot(target_x - start_x, target_y - start_y)
        if dist < 4:
            self._win32_set_cursor(target_x, target_y)
            return target_x, target_y

        # Organic human duration based on Fitts's law
        if duration is None:
            # 250ms - 600ms depending on distance
            duration = min(0.7, max(0.18, (dist / 1400.0) * 0.45)) / self.speed_factor

        # Generate human control points for Bézier curve
        # Humans arc slightly to the side due to wrist/arm pivot
        mid_x = (start_x + target_x) / 2.0
        mid_y = (start_y + target_y) / 2.0

        # Normal vector perpendicular to the line of motion
        dx = target_x - start_x
        dy = target_y - start_y
        norm_len = math.hypot(dx, dy)
        if norm_len > 0:
            nx = -dy / norm_len
            ny = dx / norm_len
        else:
            nx, ny = 0.0, 0.0

        # Random arc deviation
        arc_deviation = random.uniform(-0.15, 0.15) * dist
        ctrl1_x = start_x + dx * 0.25 + nx * arc_deviation + random.uniform(-10, 10)
        ctrl1_y = start_y + dy * 0.25 + ny * arc_deviation + random.uniform(-10, 10)
        ctrl2_x = start_x + dx * 0.75 + nx * (arc_deviation * 0.6) + random.uniform(-10, 10)
        ctrl2_y = start_y + dy * 0.75 + ny * (arc_deviation * 0.6) + random.uniform(-10, 10)

        p0 = (float(start_x), float(start_y))
        p1 = (ctrl1_x, ctrl1_y)
        p2 = (ctrl2_x, ctrl2_y)
        p3 = (float(target_x), float(target_y))

        num_steps = max(15, min(60, int(steps * (dist / 500.0))))
        step_sleep = duration / float(num_steps)

        for i in range(1, num_steps + 1):
            t_linear = i / float(num_steps)
            t_eased = _ease_out_cubic(t_linear)
            bx, by = _bezier_point(p0, p1, p2, p3, t_eased)

            # Tiny organic jitter (0.5px) in mid-flight
            if 0.2 < t_linear < 0.8:
                bx += random.uniform(-0.8, 0.8)
                by += random.uniform(-0.8, 0.8)

            self._win32_set_cursor(int(bx), int(by))
            time.sleep(step_sleep)

        # Snap to exact target point
        self._win32_set_cursor(target_x, target_y)
        # Small settling pause (human visual verification)
        time.sleep(random.uniform(0.03, 0.08))
        return target_x, target_y

    def human_click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        double: bool = False,
    ) -> Tuple[int, int]:
        """Move humanly to target and execute a realistic click.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            button: 'left', 'right', or 'middle'.
            double: If True, executes human double-click.

        Returns:
            Tuple[int, int]: Clicked coordinates.
        """
        ensure_windows_desktop_and_dpi()

        if x is not None and y is not None:
            self.human_move(x, y)
        else:
            x, y = self.get_cursor_position()

        # Human pre-click micro pause (30ms - 80ms)
        time.sleep(random.uniform(0.03, 0.08))

        if double:
            pyautogui.doubleClick(x, y, button=button)
        else:
            # Human down-hold-up cadence
            pyautogui.mouseDown(x, y, button=button)
            time.sleep(random.uniform(0.04, 0.09))
            pyautogui.mouseUp(x, y, button=button)

        time.sleep(self.action_delay)
        return x, y

    def human_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: str = "left",
    ) -> None:
        """Drag mouse smoothly from start to destination coordinates."""
        ensure_windows_desktop_and_dpi()
        self.human_move(start_x, start_y)
        time.sleep(0.08)

        pyautogui.mouseDown(start_x, start_y, button=button)
        time.sleep(0.05)

        self.human_move(end_x, end_y, duration=0.6)
        time.sleep(0.06)

        pyautogui.mouseUp(end_x, end_y, button=button)
        time.sleep(self.action_delay)

    def human_scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None, smooth: bool = True) -> None:
        """Scroll vertical mouse wheel with visible, organic human pauses."""
        ensure_windows_desktop_and_dpi()
        if x is not None and y is not None:
            self.human_move(x, y)

        step_sign = 1 if clicks > 0 else -1
        total_clicks = abs(clicks)

        # Humans scroll in visible bursts of 1-2 ticks with reading pauses
        while total_clicks > 0:
            chunk = min(total_clicks, random.randint(1, 2) if smooth else random.randint(2, 4))
            pyautogui.scroll(chunk * step_sign)
            total_clicks -= chunk
            if total_clicks > 0:
                # Visible pause so user can see page move and settle
                delay = random.uniform(0.18, 0.38) if smooth else random.uniform(0.04, 0.10)
                time.sleep(delay)

        time.sleep(self.action_delay)

    def reading_scroll(self, total_clicks: int, x: Optional[int] = None, y: Optional[int] = None, stages: int = 3) -> None:
        """Scroll progressively with realistic human reading pauses and occasional micro-reverse adjustments."""
        ensure_windows_desktop_and_dpi()
        if x is not None and y is not None:
            self.human_move(x, y)

        step_sign = 1 if total_clicks > 0 else -1
        remaining = abs(total_clicks)
        stage_count = max(1, min(stages, remaining))

        for i in range(stage_count):
            if remaining <= 0:
                break
            portion = max(1, remaining // (stage_count - i))
            self.human_scroll(portion * step_sign, smooth=True)
            remaining -= portion

            if remaining > 0 or i < stage_count - 1:
                # 30% chance human slightly back-scrolls 1 click to re-read
                if random.random() < 0.30 and abs(portion) >= 2:
                    time.sleep(random.uniform(0.2, 0.4))
                    pyautogui.scroll(-1 * step_sign)
                    time.sleep(random.uniform(0.3, 0.6))
                    pyautogui.scroll(1 * step_sign)

                time.sleep(random.uniform(1.0, 2.2))

    def human_type(self, text: str, wpm: int = 75, force_visual: bool = True) -> None:
        """Type characters with visible organic human cadence and inter-keystroke variance.

        Args:
            text: Text to type.
            wpm: Target words per minute typing speed (60-80 WPM = natural human speed).
            force_visual: If True, always type visibly on screen character by character.
        """
        if not text:
            return

        ensure_windows_desktop_and_dpi()

        # Check for special key aliases
        clean = text.strip().lower()
        if clean in ("enter", "return"):
            self.press_key("enter")
            return
        if clean in ("tab", "esc", "escape", "backspace", "space", "win", "windows", "up", "down", "left", "right"):
            self.press_key(clean)
            return

        # Check for trailing newline
        press_enter_at_end = False
        if text.endswith("\n") or text.endswith("\r\n"):
            text = text.rstrip("\r\n")
            press_enter_at_end = True

        # Base delay between keystrokes derived from WPM (5 chars per word)
        base_delay = 60.0 / (max(20, wpm) * 5.0)

        # Visible character-by-character typing
        if force_visual:
            for char in text:
                if char == "\n":
                    self.press_key("enter")
                    time.sleep(random.uniform(0.12, 0.28))
                elif char == "\t":
                    self.press_key("tab")
                    time.sleep(random.uniform(0.08, 0.15))
                else:
                    try:
                        pyautogui.write(char)
                    except Exception:
                        # Fallback for exotic unicode char
                        try:
                            pyperclip.copy(char)
                            self.hotkey("ctrl", "v")
                        except Exception:
                            pass

                    # Human keystroke rhythm: spaces and vowels faster, punctuation slower
                    if char == " ":
                        time.sleep(max(0.02, base_delay * random.uniform(0.6, 0.9)))
                    elif char in (".", ",", ";", ":", "!", "?"):
                        time.sleep(max(0.04, base_delay * random.uniform(1.8, 2.8)))
                    elif char in ("(", ")", "[", "]", "{", "}", "=", "+", "-", "_", "/", "\\", '"', "'"):
                        time.sleep(max(0.03, base_delay * random.uniform(1.3, 2.0)))
                    else:
                        jitter = random.uniform(-0.015, 0.025)
                        time.sleep(max(0.018, base_delay + jitter))
        else:
            old_clip = None
            try:
                old_clip = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(text)
            self.hotkey("ctrl", "v")

            if old_clip is not None:
                try:
                    time.sleep(0.05)
                    pyperclip.copy(old_clip)
                except Exception:
                    pass

        if press_enter_at_end:
            time.sleep(random.uniform(0.08, 0.18))
            self.press_key("enter")

        time.sleep(self.action_delay)

    def press_key(self, key: str) -> None:
        """Press and release a keyboard key with realistic key-down duration."""
        ensure_windows_desktop_and_dpi()
        key_map = {
            "return": "enter",
            "enter": "enter",
            "backspace": "backspace",
            "tab": "tab",
            "escape": "esc",
            "esc": "esc",
            "win": "win",
            "windows": "win",
            "super": "win",
            "space": "space",
            "spacebar": "space",
        }
        normalized = key_map.get(key.strip().lower(), key.strip().lower())
        pyautogui.keyDown(normalized)
        time.sleep(random.uniform(0.04, 0.08))
        pyautogui.keyUp(normalized)
        time.sleep(self.action_delay)

    def hotkey(self, *keys: str) -> None:
        """Press a key combination simultaneously with human timing."""
        ensure_windows_desktop_and_dpi()
        key_map = {
            "return": "enter",
            "win": "win",
            "windows": "win",
            "cmd": "win",
            "super": "win",
            "ctrl": "ctrl",
            "alt": "alt",
            "shift": "shift",
        }
        norm_keys = [key_map.get(k.strip().lower(), k.strip().lower()) for k in keys if k]
        if not norm_keys:
            return

        pyautogui.hotkey(*norm_keys)
        time.sleep(self.action_delay)
