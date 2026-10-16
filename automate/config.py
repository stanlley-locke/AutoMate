"""Configuration management for AutoMate desktop automation agent.

Provides application-wide settings using Pydantic Settings with automatic
environment variable loading, display resolution auto-detection, and singleton access.
"""

from __future__ import annotations

import ctypes
import os
import sys
from functools import lru_cache
from typing import Optional, Tuple

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def detect_screen_size() -> Tuple[int, int]:
    """Auto-detect the primary display resolution on Windows with DPI awareness.

    Falls back to a standard 1920x1080 resolution if detection fails or when running
    on unsupported platforms.

    Returns:
        Tuple[int, int]: (display_width, display_height) in physical pixels.
    """
    if sys.platform == "win32":
        try:
            # Enable per-monitor DPI awareness to retrieve true physical pixels
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

            width = int(ctypes.windll.user32.GetSystemMetrics(0))   # SM_CXSCREEN
            height = int(ctypes.windll.user32.GetSystemMetrics(1))  # SM_CYSCREEN
            if width > 0 and height > 0:
                return width, height
        except Exception:
            pass

    return 1920, 1080


class Config(BaseSettings):
    """AutoMate application configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    provider: str = Field(
        default="auto",
        description="AI vision provider: 'auto', 'cloudflare', or 'anthropic'",
        validation_alias=AliasChoices("PROVIDER", "provider"),
    )
    cloudflare_account_id: str = Field(
        default="",
        description="Cloudflare Account ID for Workers AI",
        validation_alias=AliasChoices("CLOUDFLARE_ACCOUNT_ID", "cloudflare_account_id"),
    )
    cloudflare_api_token: str = Field(
        default="",
        description="Cloudflare API Token with Workers AI read/write permission",
        validation_alias=AliasChoices("CLOUDFLARE_API_TOKEN", "cloudflare_api_token"),
    )
    cloudflare_model: str = Field(
        default="@cf/meta/llama-3.2-11b-vision-instruct",
        description="Cloudflare Workers AI vision model identifier",
        validation_alias=AliasChoices("CLOUDFLARE_MODEL", "cloudflare_model"),
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude API calls",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"),
    )
    model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Anthropic Claude model identifier",
        validation_alias=AliasChoices("MODEL", "model"),
    )
    screenshot_interval: float = Field(
        default=1.0,
        ge=0.1,
        description="Interval in seconds between autonomous screenshots",
        validation_alias=AliasChoices("SCREENSHOT_INTERVAL", "screenshot_interval"),
    )
    max_steps: int = Field(
        default=50,
        ge=1,
        description="Maximum execution steps per agent session",
        validation_alias=AliasChoices("MAX_STEPS", "max_steps"),
    )
    safety_mode: bool = Field(
        default=True,
        description="Whether safety mode and boundary failsafes are enabled",
        validation_alias=AliasChoices("SAFETY_MODE", "safety_mode"),
    )
    display_width: int = Field(
        default_factory=lambda: detect_screen_size()[0],
        ge=320,
        description="Physical display width in pixels (auto-detected by default)",
        validation_alias=AliasChoices("DISPLAY_WIDTH", "display_width"),
    )
    display_height: int = Field(
        default_factory=lambda: detect_screen_size()[1],
        ge=240,
        description="Physical display height in pixels (auto-detected by default)",
        validation_alias=AliasChoices("DISPLAY_HEIGHT", "display_height"),
    )
    log_level: str = Field(
        default="INFO",
        description="Application logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level"),
    )
    action_delay: float = Field(
        default=0.5,
        ge=0.0,
        description="Safety pause in seconds between automated mouse and keyboard actions",
        validation_alias=AliasChoices("ACTION_DELAY", "action_delay"),
    )
    duration_hours: float = Field(
        default=0.0,
        ge=0.0,
        description="Duration in hours for continuous/overnight run (0.0 = unlimited)",
        validation_alias=AliasChoices("DURATION_HOURS", "duration_hours"),
    )
    keep_awake: bool = Field(
        default=True,
        description="Prevent Windows sleep and display shutoff during runs",
        validation_alias=AliasChoices("KEEP_AWAKE", "keep_awake"),
    )
    loop_interval: float = Field(
        default=1.5,
        ge=0.2,
        description="Delay in seconds between perception/decision cycles in continuous mode",
        validation_alias=AliasChoices("LOOP_INTERVAL", "loop_interval"),
    )
    anti_stuck_threshold: int = Field(
        default=5,
        ge=2,
        description="Number of identical cycles before triggering anti-stuck recovery",
        validation_alias=AliasChoices("ANTI_STUCK_THRESHOLD", "anti_stuck_threshold"),
    )


_config_instance: Optional[Config] = None


def get_config(reload: bool = False) -> Config:
    """Retrieve the singleton configuration instance.

    Args:
        reload: If True, reloads configuration from environment/.env.

    Returns:
        Config: The configured AutoMate settings instance.
    """
    global _config_instance
    if _config_instance is None or reload:
        _config_instance = Config()
    return _config_instance
