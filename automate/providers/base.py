"""Base AI Provider interface for AutoMate desktop automation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ProviderAction:
    """Action emitted by an AI model to interact with desktop UI."""

    action_type: str
    coordinate: Optional[Tuple[int, int]] = None
    start_coordinate: Optional[Tuple[int, int]] = None
    text: Optional[str] = None
    key: Optional[str] = None
    keys: Optional[List[str]] = None
    duration: Optional[float] = None
    clicks: Optional[int] = None
    raw_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """Unified response from an AI provider decision tick."""

    thought: str = ""
    actions: List[ProviderAction] = field(default_factory=list)
    is_finished: bool = False
    error: Optional[str] = None
    raw_response: Any = None


class BaseAIProvider(ABC):
    """Abstract base class for vision reasoning engines."""

    @abstractmethod
    def decide_next_step(
        self,
        task: str,
        screenshot_bytes: bytes,
        screenshot_b64: str,
        display_size: Tuple[int, int],
        action_history: List[Dict[str, Any]],
        step_number: int,
    ) -> ModelResponse:
        """Analyze current screen and task context, then return recommended actions.

        Args:
            task: The overall goal or instruction for the agent.
            screenshot_bytes: Raw PNG/JPEG bytes of the current screen capture.
            screenshot_b64: Base64 string of the screen capture.
            display_size: (width, height) in physical pixels.
            action_history: List of prior actions executed in this session.
            step_number: Current cycle count.

        Returns:
            ModelResponse: Parsed decisions including thought and UI actions.
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check whether required API credentials and configs are available."""
        pass
