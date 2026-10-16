"""Unit tests for Cloudflare Workers AI provider and Continuous / Overnight engine."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import pytest
from PIL import Image

from automate.cli import automate
from automate.config import Config
from automate.continuous import ContinuousRunner, ContinuousStats
from automate.keep_awake import KeepAwake
from automate.providers.base import ModelResponse, ProviderAction
from automate.providers.cloudflare import (
    CloudflareAIProvider,
    DEFAULT_CLOUDFLARE_MODEL,
    _parse_coordinate,
)


class TestCloudflareAIProvider:
    def test_configuration_check(self):
        # Empty credentials
        prov_empty = CloudflareAIProvider(account_id="", api_token="")
        assert prov_empty.is_configured() is False

        # Configured credentials
        prov_valid = CloudflareAIProvider(
            account_id="test_acc_123",
            api_token="test_tok_456",
            model="@cf/meta/llama-3.2-11b-vision-instruct",
        )
        assert prov_valid.is_configured() is True
        assert "test_acc_123" in prov_valid.direct_url
        assert "@cf/meta/llama-3.2-11b-vision-instruct" in prov_valid.direct_url
        assert "chat/completions" in prov_valid.openai_compat_url

    def test_parse_model_json_strict(self):
        prov = CloudflareAIProvider("acc", "tok")
        raw = json.dumps({
            "thought": "I see the play button, clicking it.",
            "status": "in_progress",
            "actions": [{"action": "click", "coordinate": [500, 300]}],
        })
        parsed = prov._parse_model_json(raw)
        assert parsed["thought"] == "I see the play button, clicking it."
        assert parsed["status"] == "in_progress"
        assert len(parsed["actions"]) == 1
        assert parsed["actions"][0]["coordinate"] == [500, 300]

    def test_parse_model_json_markdown_wrapped(self):
        prov = CloudflareAIProvider("acc", "tok")
        raw = (
            "Here is my analysis:\n"
            "```json\n"
            "{\n"
            '  "thought": "Typing username",\n'
            '  "status": "in_progress",\n'
            '  "actions": [\n'
            '    {"action": "type", "text": "stanlley"},\n'
            '    {"action": "key", "key": "enter"}\n'
            "  ]\n"
            "}\n"
            "```\n"
            "Done."
        )
        parsed = prov._parse_model_json(raw)
        assert parsed["thought"] == "Typing username"
        assert len(parsed["actions"]) == 2
        assert parsed["actions"][0]["text"] == "stanlley"
        assert parsed["actions"][1]["key"] == "enter"

    @patch("automate.providers.cloudflare.requests.post")
    def test_decide_next_step_mock_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "result": {
                "response": json.dumps({
                    "thought": "Navigating to inventory",
                    "status": "in_progress",
                    "actions": [
                        {"action": "click", "coordinate": [200, 400]},
                        {"action": "wait", "duration": 1.5},
                    ],
                })
            },
        }
        mock_post.return_value = mock_resp

        prov = CloudflareAIProvider("test_acc", "test_tok")
        # Dummy 10x10 image bytes
        img = Image.new("RGB", (10, 10), color="blue")
        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        resp = prov.decide_next_step(
            task="Open inventory in game",
            screenshot_bytes=raw_bytes,
            screenshot_b64="dummy_b64",
            display_size=(1920, 1080),
            action_history=[],
            step_number=1,
        )

        assert resp.error is None
        assert resp.thought == "Navigating to inventory"
        assert len(resp.actions) == 2
        assert resp.actions[0].action_type == "click"
        assert resp.actions[0].coordinate == (200, 400)
        assert resp.actions[1].action_type == "wait"
        assert resp.actions[1].duration == 1.5
        assert resp.is_finished is False


class TestKeepAwake:
    def test_keep_awake_lifecycle(self):
        mgr = KeepAwake(keep_display_on=True)
        # Testing on Windows will engage ctypes, on other platforms it safely returns False
        with patch("ctypes.windll.kernel32.SetThreadExecutionState", return_value=1) as mock_win:
            with patch("sys.platform", "win32"):
                assert mgr.start() is True
                assert mgr.is_active is True
                mgr.stop()
                assert mgr.is_active is False
                assert mock_win.call_count == 2

    def test_keep_awake_context_manager(self):
        with patch("ctypes.windll.kernel32.SetThreadExecutionState", return_value=1):
            with patch("sys.platform", "win32"):
                with KeepAwake() as ka:
                    assert ka.is_active is True
                assert ka.is_active is False


class TestContinuousRunner:
    def test_continuous_stats_formatting(self):
        stats = ContinuousStats()
        assert "00h 00m" in stats.elapsed_formatted

    def test_runner_max_cycles_termination(self):
        mock_agent = MagicMock()
        mock_agent.screen.capture.return_value = Image.new("RGB", (10, 10), color="red")
        mock_agent.screen.get_screen_size.return_value = (1920, 1080)
        mock_agent.screen.to_base64.return_value = "b64"
        mock_agent.action_history = []
        mock_agent.provider.decide_next_step.return_value = ModelResponse(
            thought="Thinking",
            actions=[ProviderAction(action_type="wait", duration=0.01)],
            is_finished=False,
        )

        runner = ContinuousRunner(
            agent=mock_agent,
            task="Play game",
            duration_hours=0.0,
            max_cycles=3,  # Run exactly 3 cycles
            loop_interval=0.01,
            keep_awake=False,
        )

        stats = runner.run()
        assert stats.total_cycles == 3
        assert stats.actions_executed == 3
        assert mock_agent._execute_provider_action.call_count == 3

    def test_anti_stuck_recovery(self):
        mock_agent = MagicMock()
        static_img = Image.new("RGB", (10, 10), color="green")
        mock_agent.screen.capture.return_value = static_img
        mock_agent.screen.get_screen_size.return_value = (1920, 1080)
        mock_agent.screen.to_base64.return_value = "b64"
        mock_agent.action_history = []
        mock_agent.provider.decide_next_step.return_value = ModelResponse(
            thought="Idle",
            actions=[],
            is_finished=False,
        )

        runner = ContinuousRunner(
            agent=mock_agent,
            task="Monitor game",
            duration_hours=0.0,
            max_cycles=4,
            loop_interval=0.01,
            keep_awake=False,
            anti_stuck_threshold=2,  # Trigger recovery after 2 static frames
        )

        stats = runner.run()
        assert stats.stuck_detections >= 1
        assert stats.recoveries_performed >= 1
        # Recovery calls press_key('esc') and click(center)
        mock_agent.controller.press_key.assert_called_with("esc")


class TestCLICommands:
    def test_cli_config_display(self):
        runner = CliRunner()
        result = runner.invoke(automate, ["config"])
        assert result.exit_code == 0
        assert "Active AutoMate Configuration" in result.output
        assert "CLOUDFLARE" in result.output.upper()
        assert "PROVIDER" in result.output.upper()

    def test_cli_overnight_help(self):
        runner = CliRunner()
        result = runner.invoke(automate, ["overnight", "--help"])
        assert result.exit_code == 0
        assert "--hours" in result.output
        assert "--provider" in result.output
        assert "--loop-interval" in result.output

    def test_cli_keep_awake_help(self):
        runner = CliRunner()
        result = runner.invoke(automate, ["keep-awake", "--help"])
        assert result.exit_code == 0
        assert "--minutes" in result.output


class TestCoordinateParserAndKeyHandling:
    def test_parse_coordinate_formats(self):
        # List of ints
        assert _parse_coordinate([816, 646]) == (816, 646)
        # String representing list
        assert _parse_coordinate("[816, 646]") == (816, 646)
        # Comma separated string
        assert _parse_coordinate("816, 646") == (816, 646)
        # Dict format
        assert _parse_coordinate({"x": 816, "y": 646}) == (816, 646)
        # List of strings
        assert _parse_coordinate(["816", "646"]) == (816, 646)
        # Floats
        assert _parse_coordinate([816.4, 646.6]) == (816, 647)
        # Invalid / None
        assert _parse_coordinate(None) is None
        assert _parse_coordinate("invalid") is None

    @patch("pyautogui.press")
    @patch("pyautogui.write")
    def test_type_text_enter_routing(self, mock_write, mock_press):
        from automate.input_controller import InputController
        controller = InputController(action_delay=0.0)

        # Typing 'enter' should call press('enter'), not write('enter')
        controller.type_text("enter")
        mock_press.assert_called_with("enter")
        mock_write.assert_not_called()

    @patch("pyautogui.press")
    @patch("pyautogui.write")
    def test_type_text_with_newline(self, mock_write, mock_press):
        from automate.input_controller import InputController
        controller = InputController(action_delay=0.0)

        # Typing 'hello\n' should write 'hello' and press 'enter'
        controller.type_text("hello\n")
        mock_write.assert_called_with("hello", interval=0.02)
        mock_press.assert_called_with("enter")
