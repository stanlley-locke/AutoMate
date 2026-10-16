"""Windows System Keep-Awake Manager.

Prevents the Windows operating system from sleeping, hibernating,
or turning off the display during unattended long-running or overnight tasks.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Optional

from automate.logger import get_logger

logger = get_logger("automate.keep_awake")

# Windows SetThreadExecutionState flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
ES_AWAYMODE_REQUIRED = 0x00000040


class KeepAwake:
    """Context manager and utility to prevent Windows sleep and display shutoff."""

    def __init__(self, keep_display_on: bool = True, away_mode: bool = False) -> None:
        self.keep_display_on = keep_display_on
        self.away_mode = away_mode
        self._active = False

    def start(self) -> bool:
        """Enable keep-awake state on Windows.

        Returns:
            bool: True if keep-awake was successfully engaged, False otherwise.
        """
        if sys.platform != "win32":
            logger.debug("KeepAwake is only active on Windows.")
            return False

        try:
            flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            if self.keep_display_on:
                flags |= ES_DISPLAY_REQUIRED
            if self.away_mode:
                flags |= ES_AWAYMODE_REQUIRED

            prev_state = ctypes.windll.kernel32.SetThreadExecutionState(flags)
            if prev_state != 0:
                self._active = True
                logger.info(
                    "Keep-Awake engaged: Windows sleep and display-off prevented "
                    f"(flags=0x{flags:08X})"
                )
                return True
            else:
                logger.warning("SetThreadExecutionState returned 0 (failed to engage).")
                return False
        except Exception as e:
            logger.error(f"Failed to engage Keep-Awake: {e}")
            return False

    def stop(self) -> None:
        """Release keep-awake state, allowing normal Windows power management."""
        if not self._active or sys.platform != "win32":
            return

        try:
            # Setting ES_CONTINUOUS without other flags restores normal power policy
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            self._active = False
            logger.info("Keep-Awake released: Normal Windows sleep schedule restored.")
        except Exception as e:
            logger.error(f"Error restoring normal sleep state: {e}")

    @property
    def is_active(self) -> bool:
        """Check whether keep-awake is actively asserted."""
        return self._active

    def __enter__(self) -> KeepAwake:
        self.start()
        return self

    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[object]) -> None:
        self.stop()
