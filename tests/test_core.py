"""Comprehensive test suite for AutoMate core engine modules."""

import base64
import os
import sys

import pytest
from PIL import Image

# Ensure AutoMate package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from automate.actions import (
    Action,
    ActionResult,
    ActionType,
    parse_tool_use,
)
from automate.config import (
    Config,
    detect_screen_size,
    get_config,
)
from automate.input_controller import (
    CoordinateOutOfBoundsError,
    InputController,
)
from automate.screen import (
    ScreenCapture,
)


class TestConfig:
    def test_default_config(self):
        cfg = Config()
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.screenshot_interval == 1.0
        assert cfg.max_steps == 50
        assert cfg.safety_mode is True
        assert cfg.display_width > 0
        assert cfg.display_height > 0
        assert cfg.log_level == "INFO"
        assert cfg.action_delay == 0.5

    def test_singleton_get_config(self):
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

        c3 = get_config(reload=True)
        assert c3 is not None

    def test_detect_screen_size(self):
        w, h = detect_screen_size()
        assert isinstance(w, int) and w >= 320
        assert isinstance(h, int) and h >= 240


class TestScreenCapture:
    def test_screen_capture_lifecycle(self):
        with ScreenCapture() as sc:
            w, h = sc.get_screen_size()
            assert w > 0 and h > 0

            img = sc.capture()
            assert isinstance(img, Image.Image)
            assert img.mode == "RGB"
            assert img.size == (w, h)

    def test_capture_region(self):
        with ScreenCapture() as sc:
            reg = sc.capture_region(50, 50, 120, 80)
            assert isinstance(reg, Image.Image)
            assert reg.size == (120, 80)

    def test_resize_for_api_and_base64(self):
        with ScreenCapture() as sc:
            full = sc.capture()
            resized, scale = sc.resize_for_api(full, max_width=1280, max_height=800)
            assert resized.size[0] <= 1280
            assert resized.size[1] <= 800
            assert 0.0 < scale <= 1.0

            b64_str = sc.to_base64(resized)
            assert isinstance(b64_str, str)
            # Verify valid base64
            decoded = base64.b64decode(b64_str)
            assert len(decoded) > 0


class TestInputController:
    def test_initialization_and_scale(self):
        ic = InputController(action_delay=0.0, safety_mode=True, scale_factor=0.5)
        assert ic.scale_factor == 0.5

        # (100, 100) / 0.5 = (200, 200)
        mapped = ic.scale_coordinates(100, 100)
        assert mapped == (200, 200)

        ic.set_scale_factor(1.0)
        assert ic.scale_coordinates(150, 250) == (150, 250)

    def test_invalid_scale_factor(self):
        ic = InputController()
        with pytest.raises(ValueError):
            ic.set_scale_factor(0)
        with pytest.raises(ValueError):
            ic.set_scale_factor(-1.5)

    def test_bounds_validation(self):
        ic = InputController(safety_mode=True)
        w, h = ic.get_screen_bounds()

        # Valid coords
        assert ic._validate_coordinates(10, 10) == (10, 10)

        # Out of bounds raises CoordinateOutOfBoundsError
        with pytest.raises(CoordinateOutOfBoundsError):
            ic._validate_coordinates(w + 100, h + 100)

        # Clamping
        clamped = ic._validate_coordinates(w + 100, h + 100, clamp=True)
        assert clamped == (w - 1, h - 1)

    def test_normalize_key(self):
        ic = InputController()
        assert ic._normalize_key("Return") == "enter"
        assert ic._normalize_key("enter") == "enter"
        assert ic._normalize_key("Control_L") == "ctrlleft"
        assert ic._normalize_key("backspace") == "backspace"
        assert ic._normalize_key("Page_Down") == "pagedown"


class TestActionsAndParser:
    def test_parse_click(self):
        block = {
            "type": "tool_use",
            "name": "computer",
            "input": {"action": "left_click", "coordinate": [500, 300]},
        }
        act = parse_tool_use(block)
        assert act.type == ActionType.CLICK
        assert act.coordinates == (500, 300)

    def test_parse_double_and_right_click(self):
        block1 = {"input": {"action": "double_click", "coordinate": [10, 20]}}
        assert parse_tool_use(block1).type == ActionType.DOUBLE_CLICK

        block2 = {"input": {"action": "right_click", "coordinate": [30, 40]}}
        assert parse_tool_use(block2).type == ActionType.RIGHT_CLICK

    def test_parse_drag(self):
        block = {
            "input": {
                "action": "left_click_drag",
                "coordinate": [100, 100],
                "drag_end": [300, 400],
                "duration": 0.8,
            }
        }
        act = parse_tool_use(block)
        assert act.type == ActionType.DRAG
        assert act.coordinates == (100, 100)
        assert act.drag_end == (300, 400)
        assert act.duration == 0.8

    def test_parse_type(self):
        block = {"input": {"action": "type", "text": "Hello AutoMate!"}}
        act = parse_tool_use(block)
        assert act.type == ActionType.TYPE
        assert act.text == "Hello AutoMate!"

    def test_parse_key_and_hotkey(self):
        # Single key
        b1 = {"input": {"action": "key", "text": "Return"}}
        a1 = parse_tool_use(b1)
        assert a1.type == ActionType.KEY
        assert a1.key == "Return"

        # Hotkey combo in 'key' text
        b2 = {"input": {"action": "key", "text": "ctrl + shift + esc"}}
        a2 = parse_tool_use(b2)
        assert a2.type == ActionType.HOTKEY
        assert a2.keys == ["ctrl", "shift", "esc"]

        # Hotkey explicit
        b3 = {"input": {"action": "hotkey", "keys": ["ctrl", "c"]}}
        a3 = parse_tool_use(b3)
        assert a3.type == ActionType.HOTKEY
        assert a3.keys == ["ctrl", "c"]

    def test_parse_scroll(self):
        # Scroll down
        b_down = {"input": {"action": "scroll", "direction": "down", "amount": 5}}
        a_down = parse_tool_use(b_down)
        assert a_down.type == ActionType.SCROLL
        assert a_down.scroll_amount == -5

        # Scroll up
        b_up = {"input": {"action": "scroll", "direction": "up", "amount": 3}}
        a_up = parse_tool_use(b_up)
        assert a_up.type == ActionType.SCROLL
        assert a_up.scroll_amount == 3

    def test_parse_screenshot_and_cursor(self):
        assert parse_tool_use({"input": {"action": "screenshot"}}).type == ActionType.SCREENSHOT
        assert parse_tool_use({"input": {"action": "cursor_position"}}).type == ActionType.CURSOR_POSITION

    def test_action_result_to_tool_result(self):
        res_ok = ActionResult(success=True, screenshot="dummy_base64")
        tool_res = res_ok.to_tool_result(tool_use_id="tool_123")
        assert tool_res["tool_use_id"] == "tool_123"
        assert tool_res["is_error"] is False
        assert tool_res["content"][0]["type"] == "image"
        assert tool_res["content"][0]["source"]["data"] == "dummy_base64"

        res_err = ActionResult(success=False, error="Window not found")
        tool_err = res_err.to_tool_result(tool_use_id="tool_456")
        assert tool_err["is_error"] is True
        assert "Window not found" in tool_err["content"][0]["text"]
