"""AutoMate - Windows Desktop Automation Agent powered by Anthropic Claude Computer Use.

Provides computer perception, mouse & keyboard control, action parsing, robust
configuration management, agent loop, and CLI interface.
"""

from automate.actions import (
    Action,
    ActionResult,
    ActionType,
    parse_tool_use,
)
from automate.agent import (
    AgentResult,
    AutoMateAgent,
)
from automate.cli import automate
from automate.config import (
    Config,
    detect_screen_size,
    get_config,
)
from automate.continuous import (
    ContinuousRunner,
    ContinuousStats,
)
from automate.input_controller import (
    CoordinateOutOfBoundsError,
    InputController,
)
from automate.keep_awake import (
    KeepAwake,
)
from automate.logger import (
    ActionLogger,
    get_logger,
)
from automate.providers import (
    AnthropicProvider,
    BaseAIProvider,
    CloudflareAIProvider,
    ModelResponse,
    ProviderAction,
)
from automate.screen import (
    ScreenCapture,
    WindowNotFoundError,
    ensure_windows_desktop_and_dpi,
)

__version__ = "0.2.0"

__all__ = [
    # Version
    "__version__",
    # Agent & Continuous
    "AutoMateAgent",
    "AgentResult",
    "ContinuousRunner",
    "ContinuousStats",
    "KeepAwake",
    # Providers
    "BaseAIProvider",
    "CloudflareAIProvider",
    "AnthropicProvider",
    "ModelResponse",
    "ProviderAction",
    # CLI
    "automate",
    # Config
    "Config",
    "get_config",
    "detect_screen_size",
    # Screen Capture
    "ScreenCapture",
    "WindowNotFoundError",
    "ensure_windows_desktop_and_dpi",
    # Input Control
    "InputController",
    "CoordinateOutOfBoundsError",
    # Actions & Parsing
    "Action",
    "ActionResult",
    "ActionType",
    "parse_tool_use",
    # Logging
    "ActionLogger",
    "get_logger",
]
