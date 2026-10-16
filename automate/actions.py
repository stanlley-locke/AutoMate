"""Action definitions and tool use parser for AutoMate.

Defines the core Action schema, ActionType enumeration, ActionResult payload,
and translation logic from Anthropic Claude Computer Use tool use blocks
into executable AutoMate Action objects.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Enumeration of actions supported by AutoMate and Claude Computer Use."""

    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    DRAG = "drag"
    SCROLL = "scroll"
    TYPE = "type"
    KEY = "key"
    HOTKEY = "hotkey"
    SCREENSHOT = "screenshot"
    WAIT = "wait"
    CURSOR_POSITION = "cursor_position"
    MOUSE_MOVE = "mouse_move"
    OPEN_URL = "open_url"
    LAUNCH_APP = "launch_app"
    FIND_AND_OPEN_APP = "find_and_open_app"
    RUN_COMMAND = "run_command"
    FOCUS_WINDOW = "focus_window"
    NEW_TAB = "new_tab"
    CLOSE_TAB = "close_tab"
    SWITCH_TAB = "switch_tab"
    OPEN_EXPLORER = "open_explorer"
    CREATE_DIRECTORY = "create_directory"
    CREATE_FILE = "create_file"
    OPEN_IN_VSCODE = "open_in_vscode"
    RUN_PYTHON = "run_python"
    PLAY_YOUTUBE = "play_youtube"
    TOGGLE_PLAYBACK = "toggle_playback"
    NEXT_VIDEO = "next_video"
    CLOSE_APP = "close_app"


class Action(BaseModel):
    """Normalized executable action request parsed from Claude's response."""

    type: ActionType = Field(description="The category of action to execute")
    coordinates: Optional[Tuple[int, int]] = Field(
        default=None,
        description="Target (x, y) coordinates on the display/image",
    )
    text: Optional[str] = Field(
        default=None,
        description="Text content to type into active control",
    )
    key: Optional[str] = Field(
        default=None,
        description="Single keyboard key identifier to press",
    )
    keys: Optional[List[str]] = Field(
        default=None,
        description="Ordered list of keys for hotkey combinations",
    )
    scroll_amount: Optional[int] = Field(
        default=None,
        description="Number of scroll wheel clicks (positive=up, negative=down)",
    )
    drag_end: Optional[Tuple[int, int]] = Field(
        default=None,
        description="Ending (x, y) coordinates for drag operations",
    )
    duration: Optional[float] = Field(
        default=None,
        description="Optional duration in seconds (e.g. for wait or drag)",
    )


class ActionResult(BaseModel):
    """Outcome payload generated after attempting an action execution."""

    success: bool = Field(default=True, description="Whether the action completed without errors")
    screenshot: Optional[str] = Field(
        default=None,
        description="Base64-encoded PNG image of the screen following action execution",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error description if action execution failed",
    )
    cursor_position: Optional[Tuple[int, int]] = Field(
        default=None,
        description="Current (x, y) cursor coordinates after execution",
    )

    def to_tool_result(self, tool_use_id: str) -> Dict[str, Any]:
        """Convert this ActionResult into Anthropic's tool_result block format.

        Args:
            tool_use_id: The identifier of the original tool_use request.

        Returns:
            Dict[str, Any]: Formatted Anthropic tool_result message dictionary.
        """
        content: List[Dict[str, Any]] = []

        if self.screenshot:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": self.screenshot,
                },
            })

        if self.error:
            content.append({
                "type": "text",
                "text": f"Error: {self.error}",
            })
        elif self.cursor_position is not None:
            content.append({
                "type": "text",
                "text": f"Cursor position: ({self.cursor_position[0]}, {self.cursor_position[1]})",
            })
        elif not self.screenshot:
            content.append({
                "type": "text",
                "text": "Action executed successfully.",
            })

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "is_error": not self.success,
            "content": content,
        }


def _extract_coordinates(raw_coord: Any) -> Optional[Tuple[int, int]]:
    """Helper to convert list, tuple, or dict coordinate formats into (x, y)."""
    if raw_coord is None:
        return None
    if isinstance(raw_coord, (list, tuple)) and len(raw_coord) >= 2:
        return int(raw_coord[0]), int(raw_coord[1])
    if isinstance(raw_coord, dict) and "x" in raw_coord and "y" in raw_coord:
        return int(raw_coord["x"]), int(raw_coord["y"])
    return None


def parse_tool_use(tool_use_block: Union[Dict[str, Any], Any]) -> Action:
    """Parse Claude's computer tool use response block into an AutoMate Action.

    Accepts either raw dicts or Anthropic BetaToolUseBlock / ToolUseBlock objects.

    Supported Claude actions:
        - "left_click", "click" -> ActionType.CLICK
        - "right_click" -> ActionType.RIGHT_CLICK
        - "double_click" -> ActionType.DOUBLE_CLICK
        - "triple_click" -> ActionType.CLICK
        - "middle_click" -> ActionType.CLICK
        - "mouse_move" -> ActionType.MOUSE_MOVE
        - "left_click_drag" -> ActionType.DRAG
        - "type" -> ActionType.TYPE
        - "key" -> ActionType.KEY (or ActionType.HOTKEY if '+' combo detected)
        - "hotkey" -> ActionType.HOTKEY
        - "screenshot" -> ActionType.SCREENSHOT
        - "wait" -> ActionType.WAIT
        - "cursor_position" -> ActionType.CURSOR_POSITION
        - "scroll" -> ActionType.SCROLL

    Args:
        tool_use_block: Claude tool use object or dictionary.

    Returns:
        Action: Normalized AutoMate Action instance.

    Raises:
        ValueError: If the input block cannot be parsed or lacks an action field.
    """
    # Extract tool input dictionary
    if isinstance(tool_use_block, dict):
        tool_input = tool_use_block.get("input", {})
    elif hasattr(tool_use_block, "input"):
        tool_input = getattr(tool_use_block, "input")
        if not isinstance(tool_input, dict) and hasattr(tool_input, "model_dump"):
            tool_input = tool_input.model_dump()
    else:
        raise ValueError(f"Unrecognized tool use block format: {type(tool_use_block)}")

    raw_action = tool_input.get("action", "")
    if not raw_action:
        raise ValueError(f"Tool use block missing 'action' property in input: {tool_input}")

    action_name = str(raw_action).strip().lower()

    # Extract primary coordinates if present
    coords = _extract_coordinates(
        tool_input.get("coordinate")
        or tool_input.get("coordinates")
        or tool_input.get("start_coordinate")
    )

    # 1. Click variants
    if action_name in ("left_click", "click"):
        return Action(type=ActionType.CLICK, coordinates=coords)

    if action_name == "double_click":
        return Action(type=ActionType.DOUBLE_CLICK, coordinates=coords)

    if action_name == "right_click":
        return Action(type=ActionType.RIGHT_CLICK, coordinates=coords)

    if action_name in ("triple_click", "middle_click"):
        return Action(type=ActionType.CLICK, coordinates=coords)

    if action_name == "mouse_move":
        return Action(type=ActionType.MOUSE_MOVE, coordinates=coords)

    # 2. Drag
    if action_name in ("left_click_drag", "drag"):
        drag_end = _extract_coordinates(
            tool_input.get("drag_end")
            or tool_input.get("end_coordinate")
            or tool_input.get("destination")
        )
        return Action(
            type=ActionType.DRAG,
            coordinates=coords,
            drag_end=drag_end,
            duration=tool_input.get("duration", 0.5),
        )

    # 3. Typing
    if action_name == "type":
        return Action(
            type=ActionType.TYPE,
            text=str(tool_input.get("text", "")),
        )

    # 4. Key and Hotkey
    if action_name == "key":
        key_text = str(tool_input.get("text", "")).strip()
        # If combo like "ctrl+c" or "ctrl+alt+delete", parse as HOTKEY
        if "+" in key_text:
            keys = [k.strip() for k in key_text.split("+") if k.strip()]
            return Action(type=ActionType.HOTKEY, keys=keys)
        return Action(type=ActionType.KEY, key=key_text)

    if action_name == "hotkey":
        keys_val = tool_input.get("keys")
        if isinstance(keys_val, list):
            keys = [str(k).strip() for k in keys_val]
        elif isinstance(keys_val, str) and "+" in keys_val:
            keys = [k.strip() for k in keys_val.split("+")]
        elif "text" in tool_input:
            keys = [k.strip() for k in str(tool_input["text"]).split("+")]
        else:
            keys = []
        return Action(type=ActionType.HOTKEY, keys=keys)

    # 5. Screenshot
    if action_name == "screenshot":
        return Action(type=ActionType.SCREENSHOT)

    # 6. Cursor position
    if action_name == "cursor_position":
        return Action(type=ActionType.CURSOR_POSITION)

    # 7. Wait
    if action_name == "wait":
        duration = float(tool_input.get("duration", 1.0))
        return Action(type=ActionType.WAIT, duration=duration)

    # 8. Scroll
    if action_name in ("scroll", "wheel"):
        direction = str(tool_input.get("direction", tool_input.get("scroll_direction", "down"))).lower()
        amount = tool_input.get("amount") or tool_input.get("scroll_amount") or 3
        clicks = int(amount)

        # Standard Windows wheel: positive is UP, negative is DOWN
        if direction in ("down", "bottom"):
            clicks = -abs(clicks)
        elif direction in ("up", "top"):
            clicks = abs(clicks)

        return Action(
            type=ActionType.SCROLL,
            coordinates=coords,
            scroll_amount=clicks,
        )

    # Fallback directly to matching ActionType enum if passed verbatim
    try:
        matched_enum = ActionType(action_name)
        return Action(
            type=matched_enum,
            coordinates=coords,
            text=tool_input.get("text"),
            key=tool_input.get("key"),
            keys=tool_input.get("keys"),
            scroll_amount=tool_input.get("scroll_amount"),
            drag_end=_extract_coordinates(tool_input.get("drag_end")),
            duration=tool_input.get("duration"),
        )
    except ValueError:
        raise ValueError(f"Unsupported action: '{action_name}' in tool_input: {tool_input}")
