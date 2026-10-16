"""Screen capture module for AutoMate desktop automation agent.

Provides full-screen, region, and application window capture using mss
with Pillow post-processing, Windows DPI scaling support, and image preparation
for Claude Computer Use API.
"""

from __future__ import annotations

import base64
import ctypes
import io
import sys
from typing import Any, Dict, List, Optional, Tuple

import mss
from PIL import Image, ImageGrab
from rich.console import Console

console = Console()


class WindowNotFoundError(Exception):
    """Raised when an application window cannot be located by title."""


def ensure_windows_desktop_and_dpi() -> None:
    """Ensure Windows Per-Monitor DPI awareness and attach to the active input desktop.

    This ensures accurate pixel mapping and allows background runners or services
    to capture the interactive desktop screen buffer.
    """
    if sys.platform != "win32":
        return

    # Enable Per-Monitor DPI awareness (DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # Attach thread to interactive desktop if running in non-default thread context
    try:
        h_desk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x01FF)
        if h_desk:
            ctypes.windll.user32.SetThreadDesktop(h_desk)
    except Exception:
        pass


class ScreenCapture:
    """High-performance screen capture manager leveraging mss and Pillow."""

    def __init__(self, monitor_index: int = 1) -> None:
        """Initialize ScreenCapture.

        Args:
            monitor_index: Monitor index to capture.
                0 represents the virtual desktop spanning all monitors.
                1 represents the primary display.
                2+ represents secondary displays.
        """
        ensure_windows_desktop_and_dpi()
        self.monitor_index = monitor_index
        self._sct: Optional[mss.MSS] = None

    @property
    def sct(self) -> mss.MSS:
        """Lazily instantiate or reuse the MSS screen capture context."""
        if self._sct is None:
            ensure_windows_desktop_and_dpi()
            self._sct = mss.MSS()
        return self._sct

    def close(self) -> None:
        """Release underlying MSS resources."""
        if self._sct is not None:
            self._sct.close()
            self._sct = None

    def __enter__(self) -> ScreenCapture:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def get_monitors(self) -> List[Dict[str, Any]]:
        """Return information on all connected monitors.

        Returns:
            List[Dict[str, Any]]: List of monitor geometry dictionaries.
        """
        return list(self.sct.monitors)

    def get_screen_size(self) -> Tuple[int, int]:
        """Get the resolution (width, height) of the active monitor.

        Returns:
            Tuple[int, int]: (width, height) in physical pixels.
        """
        monitors = self.sct.monitors
        if 0 <= self.monitor_index < len(monitors):
            mon = monitors[self.monitor_index]
            return mon["width"], mon["height"]
        if len(monitors) > 1:
            return monitors[1]["width"], monitors[1]["height"]
        return monitors[0]["width"], monitors[0]["height"]

    def capture(self) -> Image.Image:
        """Capture the full screen of the active monitor.

        Returns:
            PIL.Image.Image: Captured full-screen image in RGB mode.
        """
        ensure_windows_desktop_and_dpi()
        monitors = self.sct.monitors
        idx = self.monitor_index if self.monitor_index < len(monitors) else 1
        monitor_rect = monitors[idx]

        try:
            raw_shot = self.sct.grab(monitor_rect)
            return Image.frombytes("RGB", raw_shot.size, raw_shot.bgra, "raw", "BGRX")
        except Exception as exc:
            console.log(f"[yellow]MSS capture encountered issue: {exc}. Falling back to ImageGrab.[/yellow]")
            return ImageGrab.grab(all_screens=(self.monitor_index == 0))

    def capture_region(self, x: int, y: int, w: int, h: int) -> Image.Image:
        """Capture a specific rectangular region of the screen.

        Args:
            x: Top-left X coordinate.
            y: Top-left Y coordinate.
            w: Width of the region.
            h: Height of the region.

        Returns:
            PIL.Image.Image: Captured region image in RGB mode.
        """
        ensure_windows_desktop_and_dpi()
        if w <= 0 or h <= 0:
            raise ValueError(f"Region dimensions must be positive, got w={w}, h={h}")

        region_dict = {
            "left": int(x),
            "top": int(y),
            "width": int(w),
            "height": int(h),
        }

        try:
            raw_shot = self.sct.grab(region_dict)
            return Image.frombytes("RGB", raw_shot.size, raw_shot.bgra, "raw", "BGRX")
        except Exception as exc:
            console.log(f"[yellow]MSS region grab encountered issue: {exc}. Falling back to ImageGrab.[/yellow]")
            return ImageGrab.grab(bbox=(x, y, x + w, y + h))

    def capture_window(self, title: str) -> Image.Image:
        """Capture a specific application window identified by title.

        Args:
            title: Case-insensitive window title or substring to match.

        Returns:
            PIL.Image.Image: Captured window image.

        Raises:
            WindowNotFoundError: If no matching visible window was located.
        """
        ensure_windows_desktop_and_dpi()

        if sys.platform != "win32":
            raise NotImplementedError("Window-specific capture is currently implemented for Windows.")

        import win32con
        import win32gui

        matched_hwnds: List[Tuple[int, str]] = []

        def enum_handler(hwnd: int, _: Any) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                w_title = win32gui.GetWindowText(hwnd)
                if w_title and title.lower() in w_title.lower():
                    matched_hwnds.append((hwnd, w_title))
            return True

        win32gui.EnumWindows(enum_handler, None)

        if not matched_hwnds:
            raise WindowNotFoundError(f"No visible window found matching title: '{title}'")

        target_hwnd, found_title = matched_hwnds[0]
        console.log(f"[cyan]Capturing window: '{found_title}' (HWND: {target_hwnd})[/cyan]")

        # Restore window if minimized
        if win32gui.IsIconic(target_hwnd):
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)

        # Bring window to foreground
        try:
            win32gui.SetForegroundWindow(target_hwnd)
        except Exception:
            pass

        # Retrieve accurate window frame bounds using DWM API (excludes invisible shadow borders)
        rect = ctypes.wintypes.RECT()
        dwm_extended_frame_bounds = 9
        dwm_res = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            target_hwnd,
            dwm_extended_frame_bounds,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )

        if dwm_res == 0:
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        else:
            left, top, right, bottom = win32gui.GetWindowRect(target_hwnd)

        w = max(1, right - left)
        h = max(1, bottom - top)

        return self.capture_region(left, top, w, h)

    def to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """Convert a PIL Image to a Base64-encoded string for API transmission.

        Args:
            image: PIL Image object.
            format: Target format ('PNG' or 'JPEG').

        Returns:
            str: Base64-encoded UTF-8 string representation of the image.
        """
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def to_bytes(self, image: Image.Image, format: str = "JPEG", quality: int = 85) -> bytes:
        """Convert a PIL Image to encoded bytes (JPEG or PNG).

        Args:
            image: PIL Image object.
            format: Target format ('JPEG' or 'PNG').
            quality: Compression quality for JPEG (1-100).

        Returns:
            bytes: Encoded image file bytes.
        """
        buffer = io.BytesIO()
        if format.upper() == "JPEG" and image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffer, format=format, quality=quality)
        return buffer.getvalue()

    def resize_for_api(
        self,
        image: Image.Image,
        max_width: int = 1280,
        max_height: int = 800,
    ) -> Tuple[Image.Image, float]:
        """Resize an image to fit within API constraints while preserving aspect ratio.

        Returns both the resized PIL Image and the scale factor used.
        The scale factor is required to project Claude's coordinates back to physical screen space:
            real_x = round(api_x / scale_factor)
            real_y = round(api_y / scale_factor)

        Args:
            image: Original PIL Image.
            max_width: Maximum allowed pixel width.
            max_height: Maximum allowed pixel height.

        Returns:
            Tuple[PIL.Image.Image, float]: (resized_image, scale_factor)
        """
        orig_w, orig_h = image.size
        scale = min(max_width / orig_w, max_height / orig_h)

        if scale < 1.0:
            new_w = max(1, int(round(orig_w * scale)))
            new_h = max(1, int(round(orig_h * scale)))
            resized_image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            return resized_image, scale

        return image.copy(), 1.0
