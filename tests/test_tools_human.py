"""Unit tests for HumanInputEngine and DesktopToolSuite."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from automate.human_input import HumanInputEngine, _bezier_point, _ease_out_cubic
from automate.tools import DesktopToolSuite, COMMON_APPS


class TestHumanInput:
    def test_bezier_and_easing(self):
        # Start and end bounds
        p0 = (0.0, 0.0)
        p1 = (20.0, 50.0)
        p2 = (80.0, 50.0)
        p3 = (100.0, 100.0)

        bx0, by0 = _bezier_point(p0, p1, p2, p3, 0.0)
        assert bx0 == 0.0 and by0 == 0.0

        bx1, by1 = _bezier_point(p0, p1, p2, p3, 1.0)
        assert bx1 == 100.0 and by1 == 100.0

        # Easing function bounds
        assert _ease_out_cubic(0.0) == 0.0
        assert _ease_out_cubic(1.0) == 1.0

    @patch("ctypes.windll.user32.SetCursorPos")
    @patch("pyautogui.position")
    def test_human_move(self, mock_pos, mock_set_cursor):
        mock_pos.return_value = MagicMock(x=100, y=100)
        engine = HumanInputEngine(action_delay=0.0)

        rx, ry = engine.human_move(400, 300, duration=0.01, steps=5)
        assert rx == 400
        assert ry == 300
        assert mock_set_cursor.called

    @patch("pyautogui.mouseDown")
    @patch("pyautogui.mouseUp")
    @patch("pyautogui.position")
    def test_human_click(self, mock_pos, mock_up, mock_down):
        mock_pos.return_value = MagicMock(x=250, y=250)
        engine = HumanInputEngine(action_delay=0.0)

        engine.human_click(x=250, y=250, button="left")
        mock_down.assert_called_with(250, 250, button="left")
        mock_up.assert_called_with(250, 250, button="left")

    @patch("pyautogui.keyDown")
    @patch("pyautogui.keyUp")
    @patch("pyautogui.write")
    def test_human_type_special_key(self, mock_write, mock_up, mock_down):
        engine = HumanInputEngine(action_delay=0.0)
        engine.human_type("enter")
        mock_down.assert_called_with("enter")
        mock_up.assert_called_with("enter")
        mock_write.assert_not_called()


class TestDesktopToolSuite:
    def test_tools_registration(self):
        suite = DesktopToolSuite()
        tools = suite.list_tool_names()
        assert "launch_app" in tools
        assert "open_url" in tools
        assert "mouse_click" in tools
        assert "mouse_move" in tools
        assert "type_text" in tools
        assert "press_key" in tools
        assert "hotkey" in tools
        assert "find_and_open_app" in tools
        assert "run_command" in tools
        assert "wait" in tools
        assert "focus_window" in tools

    @patch("os.startfile")
    @patch("subprocess.Popen")
    def test_launch_app_chrome(self, mock_popen, mock_startfile):
        suite = DesktopToolSuite()
        with patch.object(suite, "focus_window", return_value="Focused Chrome"):
            res = suite.launch_app("chrome")
            assert "chrome" in res.lower()
            assert mock_popen.called or mock_startfile.called

    @patch("subprocess.Popen")
    @patch("webbrowser.open")
    def test_open_url_chrome(self, mock_browser, mock_popen):
        suite = DesktopToolSuite()
        with patch.object(suite, "focus_window", return_value="Focused Chrome"):
            res = suite.open_url("https://www.google.com/search?q=weather+Nairobi", browser="chrome")
            assert "weather" in res.lower()
            assert mock_popen.called or mock_browser.called

    def test_focus_window_nonexistent(self):
        suite = DesktopToolSuite()
        res = suite.focus_window("nonexistent_random_window_xyz")
        assert "no visible window found" in res.lower()

    def test_run_command_echo(self):
        suite = DesktopToolSuite()
        res = suite.run_command("python -c \"print('AutoMate-OK')\"")
        assert "AutoMate-OK" in res

    def test_tools_summary_prompt(self):
        suite = DesktopToolSuite()
        prompt = suite.get_tools_summary_prompt()
        assert "launch_app" in prompt
        assert "open_url" in prompt
        assert "mouse_click" in prompt
        assert "focus_window" in prompt
        assert "new_tab" in prompt
        assert "search_youtube" in prompt
        assert "create_and_edit_python_file" in prompt

    @patch("automate.human_input.HumanInputEngine.hotkey")
    def test_tab_operations(self, mock_hotkey):
        suite = DesktopToolSuite()
        with patch.object(suite, "focus_window"):
            res_new = suite.new_tab()
            assert "opened new browser tab" in res_new.lower()
            res_close = suite.close_tab()
            assert "closed active tab" in res_close.lower()
            res_switch = suite.switch_tab("prev")
            assert "previous tab" in res_switch.lower()

    def test_file_and_directory_creation(self, tmp_path):
        suite = DesktopToolSuite()
        test_dir = str(tmp_path / "test_folder")
        res_dir = suite.create_directory(test_dir)
        assert "successfully created directory" in res_dir.lower()
        assert os.path.exists(test_dir)

        test_file = str(tmp_path / "test_folder" / "sample.py")
        res_file = suite.create_file(test_file, "print('Hello AutoMate')")
        assert "successfully created file" in res_file.lower()
        assert os.path.exists(test_file)

        res_py = suite.run_python(test_file)
        assert "Hello AutoMate" in res_py

    @patch("subprocess.Popen")
    def test_open_in_vscode(self, mock_popen, tmp_path):
        suite = DesktopToolSuite()
        with patch.object(suite, "focus_window"):
            res = suite.open_in_vscode(str(tmp_path))
            assert "visual studio code" in res.lower() or "code" in res.lower()

    def test_recipes_registry(self):
        from automate.recipes import list_recipes, get_recipe
        recipes = list_recipes()
        assert len(recipes) >= 4
        names = [r.name for r in recipes]
        assert "browse-weather-youtube" in names
        assert "code-python-project" in names
        assert "file-manager-organize" in names
        assert "full-human-worker" in names

        r = get_recipe("browse-weather-youtube")
        assert r is not None
        assert r.category == "Web Browsing"

        master = get_recipe("full-human-worker")
        assert master is not None
        assert master.category == "Full Automation"

    def test_youtube_tools(self):
        suite = DesktopToolSuite()
        with patch.object(suite, "focus_window"), \
             patch.object(suite.input, "human_click"), \
             patch.object(suite.input, "press_key"), \
             patch.object(suite.input, "hotkey"):
            res_play = suite.play_youtube_video()
            assert "playback" in res_play.lower()

            res_toggle = suite.toggle_youtube_playback()
            assert "playback" in res_toggle.lower()

            res_next = suite.next_youtube_video()
            assert "next" in res_next.lower()

    def test_close_app_and_visual_tools(self):
        suite = DesktopToolSuite()
        with patch.object(suite, "focus_window"), \
             patch.object(suite.input, "hotkey"), \
             patch.object(suite.input, "human_type"), \
             patch.object(suite.input, "press_key"), \
             patch.object(suite.input, "human_click"):
            res_close = suite.close_app("chrome")
            assert "closed" in res_close.lower()

            res_folder = suite.visual_create_folder("TestFolder")
            assert "testfolder" in res_folder.lower()

            res_code = suite.visual_code_editor("print('hi')", "test.py")
            assert "test.py" in res_code.lower()

    def test_cli_repeat_and_duration_help(self):
        from click.testing import CliRunner
        from automate.cli import automate

        runner = CliRunner()
        result = runner.invoke(automate, ["run", "--help"])
        assert result.exit_code == 0
        assert "--repeat" in result.output
        assert "-r" in result.output
        assert "--duration" in result.output
        assert "-d" in result.output
        assert "--watch-mins" in result.output
        assert "--fast" in result.output

        recipe_help = runner.invoke(automate, ["recipe", "--help"])
        assert recipe_help.exit_code == 0
        assert "--repeat" in recipe_help.output
        assert "--duration" in recipe_help.output
        assert "--watch-mins" in recipe_help.output

    def test_reading_scroll_and_dynamic_topics(self):
        suite = DesktopToolSuite()
        with patch.object(suite.input, "human_scroll"):
            res = suite.reading_scroll(clicks=-6, stages=2)
            assert "reading stages" in res.lower()

        from automate.recipes import fetch_dynamic_youtube_query, RANDOM_YOUTUBE_TOPICS
        topic = fetch_dynamic_youtube_query()
        assert isinstance(topic, str)
        assert len(topic) > 0

