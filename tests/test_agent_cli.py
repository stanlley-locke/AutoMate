"""Tests for AutoMate agent, CLI, and logger modules."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import pytest

from automate.agent import ActionResult, AgentResult, AutoMateAgent
from automate.cli import automate
from automate.config import Config
from automate.logger import ActionLogger, ActionRecord, get_logger


class TestLogger:
    def test_action_record_to_dict(self):
        rec = ActionRecord(
            step=1,
            action_type="left_click",
            params={"coordinate": [100, 200]},
            success=True,
            duration_ms=45.2,
        )
        d = rec.to_dict()
        assert d["step"] == 1
        assert d["action_type"] == "left_click"
        assert d["params"] == {"coordinate": [100, 200]}
        assert d["success"] is True
        assert d["duration_ms"] == 45.2
        assert "timestamp" in d

    def test_action_logger_tracking_and_json(self, tmp_path: Path):
        log_file = tmp_path / "actions.json"
        al = ActionLogger(log_file=log_file)

        al.log_action(1, "left_click", {"coordinate": [10, 20]}, success=True, duration_ms=12.0)
        al.log_action(2, "type", {"text": "hello"}, success=True, duration_ms=30.0)

        history = al.get_history()
        assert len(history) == 2
        assert history[0].action_type == "left_click"
        assert history[1].action_type == "type"

        # Check export
        al.export_json(log_file)
        assert log_file.exists()
        loaded = json.loads(log_file.read_text(encoding="utf-8"))
        assert len(loaded) == 2
        assert loaded[0]["step"] == 1
        assert loaded[1]["params"]["text"] == "hello"

        # Check summary table generation
        table = al.build_summary_table()
        assert table is not None
        assert table.row_count == 2

    def test_get_logger(self, tmp_path: Path):
        log_file = tmp_path / "test.log"
        logger = get_logger("test_module", level="DEBUG", log_file=log_file)
        assert logger is not None
        logger.info("Test message")


class TestAgent:
    def test_agent_initialization(self):
        cfg = Config(anthropic_api_key="mock-key", max_steps=10)
        agent = AutoMateAgent(config=cfg)
        assert agent.config.max_steps == 10
        assert agent.client is not None

        tool_def = agent._get_computer_tool_definition()
        assert tool_def["name"] == "computer"
        assert tool_def["type"] in ("computer_20250124", "computer_20241022")
        assert "display_width_px" in tool_def
        assert "display_height_px" in tool_def

    def test_build_tool_result_format(self):
        agent = AutoMateAgent(config=Config(anthropic_api_key="mock-key"))
        res = ActionResult(
            success=True,
            screenshot="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            output="Done",
        )
        tool_payload = agent._build_tool_result("tool_call_123", res)

        assert tool_payload["type"] == "tool_result"
        assert tool_payload["tool_use_id"] == "tool_call_123"
        assert tool_payload["is_error"] is False
        assert len(tool_payload["content"]) == 2
        assert tool_payload["content"][0]["type"] == "image"
        assert tool_payload["content"][0]["source"]["type"] == "base64"
        assert tool_payload["content"][1]["type"] == "text"
        assert tool_payload["content"][1]["text"] == "Done"

    def test_build_tool_result_error(self):
        agent = AutoMateAgent(config=Config(anthropic_api_key="mock-key"))
        res = ActionResult(success=False, error="Coordinate out of bounds")
        tool_payload = agent._build_tool_result("tool_call_456", res)

        assert tool_payload["type"] == "tool_result"
        assert tool_payload["tool_use_id"] == "tool_call_456"
        assert tool_payload["is_error"] is True
        assert tool_payload["content"][0]["type"] == "text"
        assert "Coordinate out of bounds" in tool_payload["content"][0]["text"]

    def test_run_missing_api_key(self):
        agent = AutoMateAgent(config=Config(provider="anthropic", anthropic_api_key=""))
        agent.client = None
        result = agent.run("Open calculator")
        assert result.success is False
        assert "Anthropic API key is not configured" in result.error

    def test_mock_successful_run(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(type="text", text="The task is already complete!"),
        ]
        mock_client.beta.messages.create.return_value = mock_response

        cfg = Config(provider="anthropic", anthropic_api_key="mock-key", max_steps=5)
        agent = AutoMateAgent(config=cfg, anthropic_client=mock_client)

        result = agent.run("Verify desktop is ready")
        assert result.success is True
        assert result.steps_taken == 1
        assert "complete" in result.final_message.lower()


class TestCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_cli_help(self):
        res = self.runner.invoke(automate, ["--help"])
        assert res.exit_code == 0
        assert "AutoMate" in res.output

    def test_cli_config(self):
        res = self.runner.invoke(automate, ["config"])
        assert res.exit_code == 0
        assert "Active AutoMate Configuration" in res.output

    def test_cli_run_missing_key(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            res = self.runner.invoke(automate, ["run", "Open Notepad", "--provider", "anthropic", "--api-key", ""])
            assert res.exit_code != 0
            assert "Anthropic API Key not found" in res.output
