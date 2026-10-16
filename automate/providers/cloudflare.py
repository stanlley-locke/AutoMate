"""Cloudflare Workers AI vision provider for AutoMate.

Connects to Cloudflare Workers AI edge models (such as @cf/meta/llama-3.2-11b-vision-instruct,
@cf/meta/llama-3.2-90b-vision-instruct, and @cf/llava-1.5-7b-hf) for screen perception
and desktop automation decisions without relying on proprietary cloud APIs.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image

from automate.logger import get_logger
from automate.providers.base import BaseAIProvider, ModelResponse, ProviderAction

logger = get_logger("automate.providers.cloudflare")

DEFAULT_CLOUDFLARE_MODEL = "@cf/meta/llama-3.2-11b-vision-instruct"


class ModelAgreementRequiredError(RuntimeError):
    """Raised when Cloudflare requires submitting the 'agree' prompt for Meta model license."""
    pass


def _parse_coordinate(coord_val: Any) -> Optional[Tuple[int, int]]:
    """Robustly extract (x, y) integer coordinate tuple from list, tuple, dict, or string."""
    if coord_val is None:
        return None

    if isinstance(coord_val, (list, tuple)) and len(coord_val) >= 2:
        try:
            x = int(round(float(str(coord_val[0]).strip("[](), "))))
            y = int(round(float(str(coord_val[1]).strip("[](), "))))
            return (x, y)
        except (ValueError, TypeError):
            pass

    if isinstance(coord_val, dict):
        x = coord_val.get("x", coord_val.get("X"))
        y = coord_val.get("y", coord_val.get("Y"))
        if x is not None and y is not None:
            try:
                return (int(round(float(x))), int(round(float(y))))
            except (ValueError, TypeError):
                pass

    if isinstance(coord_val, str):
        nums = re.findall(r"[-+]?\d*\.?\d+", coord_val)
        if len(nums) >= 2:
            try:
                return (int(round(float(nums[0]))), int(round(float(nums[1]))))
            except (ValueError, TypeError):
                pass

    return None


class CloudflareAIProvider(BaseAIProvider):
    """Integrates with Cloudflare Workers AI to analyze screenshots and return UI actions."""

    def __init__(
        self,
        account_id: str,
        api_token: str,
        model: str = DEFAULT_CLOUDFLARE_MODEL,
        max_retries: int = 3,
        request_timeout: float = 45.0,
        use_openai_compat: bool = False,
    ) -> None:
        self.account_id = account_id.strip() if account_id else ""
        self.api_token = api_token.strip() if api_token else ""
        self.model = model.strip() if model else DEFAULT_CLOUDFLARE_MODEL
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        self.use_openai_compat = use_openai_compat
        self._agreement_accepted = False

    def is_configured(self) -> bool:
        """Check if account credentials exist."""
        return bool(self.account_id and self.api_token)

    @property
    def direct_url(self) -> str:
        """REST direct endpoint for Workers AI model execution."""
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"

    @property
    def openai_compat_url(self) -> str:
        """OpenAI-compatible chat completions endpoint on Cloudflare."""
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/v1/chat/completions"

    def _accept_model_agreement(self) -> bool:
        """Submit the required Meta license agreement prompt ('agree') to Cloudflare Workers AI."""
        logger.info(
            f"Submitting Meta model license agreement ('agree') to Cloudflare for {self.model}..."
        )
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        success = False

        # 1. Direct REST endpoint agreement submit
        try:
            resp = requests.post(
                self.direct_url,
                headers=headers,
                json={"prompt": "agree"},
                timeout=15.0,
            )
            if resp.status_code == 200:
                logger.info("Successfully accepted model license agreement via direct REST endpoint.")
                success = True
        except Exception as e:
            logger.debug(f"Direct agreement attempt notice: {e}")

        # 2. OpenAI-compatible endpoint agreement submit
        try:
            resp2 = requests.post(
                self.openai_compat_url,
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "agree"}],
                },
                timeout=15.0,
            )
            if resp2.status_code == 200:
                logger.info("Successfully accepted model license agreement via chat completions endpoint.")
                success = True
        except Exception as e:
            logger.debug(f"OpenAI-compat agreement attempt notice: {e}")

        self._agreement_accepted = success
        return success

    def _build_system_prompt(self, display_size: Tuple[int, int]) -> str:
        """Generate structured instructions for UI perception and action formatting."""
        w, h = display_size
        return (
            "You are AutoMate, an intelligent autonomous desktop human worker controlling a Windows 11 PC.\n"
            f"The user screen display resolution is {w}x{h} pixels.\n"
            "You have access to a full suite of desktop tools and human-grade mouse and keyboard controls.\n"
            "When performing mouse actions, the agent moves the cursor smoothly like a human hand.\n\n"
            "AVAILABLE DESKTOP ACTIONS & TOOLS:\n"
            "1. 'open_url': {'action': 'open_url', 'url': 'https://www.google.com/search?q=...'}\n"
            "   -> RECOMMENDED: Directly opens Chrome with the requested webpage or Google search.\n"
            "2. 'search_youtube': {'action': 'search_youtube', 'query': 'lofi beats'}\n"
            "   -> Opens YouTube in Chrome and searches for videos or music.\n"
            "3. 'new_tab': {'action': 'new_tab', 'url': 'https://...'}\n"
            "   -> Opens a new browser tab (Ctrl+T) and optionally navigates to URL.\n"
            "4. 'close_tab': {'action': 'close_tab'}\n"
            "   -> Closes current tab (Ctrl+W).\n"
            "5. 'switch_tab': {'action': 'switch_tab', 'direction': 'next' | 'prev'}\n"
            "   -> Cycles between open browser tabs.\n"
            "6. 'launch_app': {'action': 'launch_app', 'app_name': 'chrome' | 'notepad' | 'calc' | 'vscode' | 'vectorcraft'}\n"
            "   -> Starts a desktop application and brings it to the foreground.\n"
            "7. 'find_and_open_app': {'action': 'find_and_open_app', 'query': 'chrome'}\n"
            "   -> Opens Windows Start Menu, types the app name, and presses Enter like a human.\n"
            "8. 'focus_window': {'action': 'focus_window', 'keyword': 'Chrome' | 'Code' | 'Notepad' | 'Explorer'}\n"
            "   -> Brings an already open application window into the active foreground.\n"
            "9. 'open_in_vscode': {'action': 'open_in_vscode', 'path': '~/Desktop/MyProject'}\n"
            "   -> Opens a project directory or code file in Visual Studio Code.\n"
            "10. 'create_and_edit_python_file': {'action': 'create_and_edit_python_file', 'file_name': 'main.py', 'code_content': 'print(\"Hello\")', 'directory': '~/Desktop/MyProject'}\n"
            "   -> Creates a complete Python file and immediately opens it in VS Code.\n"
            "11. 'open_file_explorer': {'action': 'open_file_explorer', 'path': '~/Desktop'}\n"
            "   -> Opens Windows File Explorer at the specified folder.\n"
            "12. 'create_directory': {'action': 'create_directory', 'path': '~/Desktop/MyNewFolder'}\n"
            "   -> Creates a new folder on the desktop or filesystem.\n"
            "13. 'create_file': {'action': 'create_file', 'file_path': '~/Desktop/notes.txt', 'content': '...'}\n"
            "   -> Writes or creates any text or code file.\n"
            "14. 'run_python': {'action': 'run_python', 'file_path': '~/Desktop/MyProject/main.py'}\n"
            "   -> Executes a python script and returns the terminal output.\n"
            "15. 'click': {'action': 'click', 'coordinate': [x, y], 'button': 'left' | 'right'}\n"
            "   -> Smoothly glides the mouse to [x, y] and clicks.\n"
            "16. 'double_click': {'action': 'double_click', 'coordinate': [x, y]}\n"
            "17. 'right_click': {'action': 'right_click', 'coordinate': [x, y]}\n"
            "18. 'mouse_move': {'action': 'mouse_move', 'coordinate': [x, y]}\n"
            "19. 'drag': {'action': 'drag', 'start_coordinate': [x1, y1], 'coordinate': [x2, y2]}\n"
            "20. 'scroll': {'action': 'scroll', 'clicks': -5} (negative=down to read/browse, positive=up)\n"
            "21. 'type': {'action': 'type', 'text': '...'}\n"
            "    -> Types text into the currently active input field.\n"
            "22. 'key': {'action': 'key', 'key': 'enter' | 'win' | 'esc' | 'tab' | 'space' | 'backspace' | 'up' | 'down'}\n"
            "    -> Press a single keyboard key.\n"
            "23. 'hotkey': {'action': 'hotkey', 'keys': ['ctrl', 't'] | ['ctrl', 's'] | ['ctrl', 'w'] | ['alt', 'tab']}\n"
            "24. 'run_command': {'action': 'run_command', 'command': '...'}\n"
            "25. 'wait': {'action': 'wait', 'duration': 1.5}\n\n"
            "EXAMPLES:\n"
            "- Browsing & Search:\n"
            '  {"thought": "Opening Google search for weather in Nairobi in Chrome", "status": "in_progress", "actions": [{"action": "open_url", "url": "https://www.google.com/search?q=weather+in+Nairobi"}]}\n'
            "- Browse YouTube:\n"
            '  {"thought": "Searching YouTube for relaxing music", "status": "in_progress", "actions": [{"action": "search_youtube", "query": "relaxing coding music"}]}\n'
            "- Scroll down page to read results/comments:\n"
            '  {"thought": "Scrolling down to view search results", "status": "in_progress", "actions": [{"action": "scroll", "clicks": -6}]}\n'
            "- Open new tab:\n"
            '  {"thought": "Opening a new tab for next search", "status": "in_progress", "actions": [{"action": "new_tab", "url": "https://www.google.com"}]}\n'
            "- Close active tab:\n"
            '  {"thought": "Finished viewing, closing tab", "status": "in_progress", "actions": [{"action": "close_tab"}]}\n'
            "- Coding in VS Code:\n"
            "  {\"thought\": \"Writing Python code and opening in VS Code\", \"status\": \"in_progress\", \"actions\": [{\"action\": \"create_and_edit_python_file\", \"file_name\": \"app.py\", \"code_content\": \"def main():\\n    print('AutoMate Running')\\nif __name__ == '__main__':\\n    main()\", \"directory\": \"~/Desktop/AutoMate_Projects\"}]}\n"
            "- Open Windows File Explorer:\n"
            "  {\"thought\": \"Opening Desktop in File Explorer\", \"status\": \"in_progress\", \"actions\": [{\"action\": \"open_file_explorer\", \"path\": \"~/Desktop\"}]}\n\n"
            "CRITICAL RULES:\n"
            "1. NEVER type high-level tasks directly into the desktop without an active focused input field.\n"
            "2. For web search or browsing, ALWAYS use 'open_url' or 'search_youtube'.\n"
            "3. For tabs, ALWAYS use 'new_tab', 'close_tab', or 'switch_tab'.\n"
            "4. For coding or file creation, use 'create_and_edit_python_file' or 'open_in_vscode'.\n"
            "5. For file management, use 'open_file_explorer' or 'create_directory'.\n"
            "6. Output ONLY a valid JSON object matching the schema:\n"
            "{\n"
            '  "thought": "Brief explanation of what you see on screen and what action you are taking",\n'
            '  "status": "in_progress" | "complete",\n'
            '  "actions": [\n'
            '    {"action": "open_url", "url": "https://..."}\n'
            "  ]\n"
            "}\n"
            "Do NOT include any text outside the JSON object.\n"
            "If the task is already completely finished, set status to \"complete\" and actions to []."
        )

    def _prepare_jpeg_bytes(
        self, screenshot_bytes: bytes, screenshot_b64: str = "", max_dim: int = 1280
    ) -> bytes:
        """Ensure screenshot is optimized JPEG format and appropriately sized."""
        img = None
        if screenshot_bytes:
            try:
                img = Image.open(io.BytesIO(screenshot_bytes))
            except Exception:
                img = None

        if img is None and screenshot_b64:
            try:
                img = Image.open(io.BytesIO(base64.b64decode(screenshot_b64)))
            except Exception:
                img = None

        if img is not None:
            try:
                img = img.convert("RGB")
                w, h = img.size
                if max(w, h) > max_dim:
                    scale = max_dim / float(max(w, h))
                    new_size = (int(w * scale), int(h * scale))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return buf.getvalue()
            except Exception as e:
                logger.warning(f"Error optimizing screenshot for Cloudflare: {e}; using raw bytes")

        return screenshot_bytes

    def _check_for_agreement_error(self, text: str) -> None:
        """Raise ModelAgreementRequiredError if error text indicates license acceptance is needed."""
        if (
            "5016" in text
            or "Model Agreement" in text
            or "submit the prompt 'agree'" in text
            or "submit the prompt ‘agree’" in text
        ):
            raise ModelAgreementRequiredError(
                "Cloudflare Meta Llama 3.2 license agreement prompt required."
            )

    def _call_direct_rest(
        self, prompt: str, system_prompt: str, image_bytes: bytes
    ) -> Dict[str, Any]:
        """Call Cloudflare /ai/run/{model} REST endpoint with byte array image."""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        # Cloudflare Workers AI expects the image as an array of integer byte values (0-255)
        byte_list = list(image_bytes)

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "image": byte_list,
        }

        response = requests.post(
            self.direct_url,
            headers=headers,
            json=payload,
            timeout=self.request_timeout,
        )

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 10))
            logger.warning(f"Cloudflare rate limit encountered (429). Backing off {retry_after}s...")
            time.sleep(retry_after)
            raise RuntimeError(f"Cloudflare 429 Rate Limit: Retry after {retry_after}s")

        self._check_for_agreement_error(response.text)

        if response.status_code != 200:
            raise RuntimeError(
                f"Cloudflare API returned HTTP {response.status_code}: {response.text}"
            )

        data = response.json()
        if not data.get("success", False):
            errors = data.get("errors", [])
            self._check_for_agreement_error(str(errors))
            raise RuntimeError(f"Cloudflare AI execution error: {errors}")

        return data

    def _call_openai_compat(
        self, prompt: str, system_prompt: str, screenshot_b64: str
    ) -> Dict[str, Any]:
        """Call Cloudflare OpenAI-compatible endpoint with Base64 data URI."""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"},
                        },
                    ],
                },
            ],
        }

        response = requests.post(
            self.openai_compat_url,
            headers=headers,
            json=payload,
            timeout=self.request_timeout,
        )

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 10))
            logger.warning(f"Cloudflare rate limit encountered (429). Backing off {retry_after}s...")
            time.sleep(retry_after)
            raise RuntimeError(f"Cloudflare 429 Rate Limit: Retry after {retry_after}s")

        self._check_for_agreement_error(response.text)

        if response.status_code != 200:
            raise RuntimeError(
                f"Cloudflare OpenAI-compat API returned HTTP {response.status_code}: {response.text}"
            )

        return response.json()

    def _extract_text_content(self, api_response: Dict[str, Any]) -> str:
        """Extract text content from either direct REST or OpenAI-compatible responses."""
        if "result" in api_response:
            res = api_response["result"]
            if isinstance(res, dict):
                return str(res.get("response") or res.get("description") or res.get("text") or "")
            if isinstance(res, str):
                return res

        if "choices" in api_response and len(api_response["choices"]) > 0:
            choice = api_response["choices"][0]
            if isinstance(choice, dict):
                msg = choice.get("message", {})
                return str(msg.get("content", ""))

        return str(api_response)

    def _parse_model_json(self, raw_text: str) -> Dict[str, Any]:
        """Extract and parse JSON object from model's response string with multiple fallbacks."""
        cleaned = raw_text.strip()

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            val = json.loads(cleaned)
            if isinstance(val, dict):
                return val
            if isinstance(val, list):
                return {"thought": "Executing actions list", "status": "in_progress", "actions": val}
        except json.JSONDecodeError:
            pass

        import ast
        try:
            val = ast.literal_eval(cleaned)
            if isinstance(val, dict):
                return val
            if isinstance(val, list):
                return {"thought": "Executing actions list", "status": "in_progress", "actions": val}
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            candidate = match.group(0)
            try:
                val = json.loads(candidate)
                if isinstance(val, dict):
                    return val
            except json.JSONDecodeError:
                pass
            try:
                val = ast.literal_eval(candidate)
                if isinstance(val, dict):
                    return val
            except Exception:
                pass

        array_match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", cleaned)
        if array_match:
            candidate = array_match.group(0)
            try:
                val = json.loads(candidate)
                if isinstance(val, list):
                    return {"thought": "Executing actions list", "status": "in_progress", "actions": val}
            except Exception:
                pass

        logger.warning(f"Failed to parse strict JSON from model output: {raw_text[:200]}...")
        return {
            "thought": cleaned,
            "status": "in_progress",
            "actions": [],
        }

    def decide_next_step(
        self,
        task: str,
        screenshot_bytes: bytes,
        screenshot_b64: str,
        display_size: Tuple[int, int],
        action_history: List[Dict[str, Any]],
        step_number: int,
    ) -> ModelResponse:
        """Send screen observation to Cloudflare Workers AI and return parsed actions."""
        if not self.is_configured():
            return ModelResponse(
                error=(
                    "Cloudflare AI is not configured. Please set CLOUDFLARE_ACCOUNT_ID and "
                    "CLOUDFLARE_API_TOKEN in your environment or .env file."
                )
            )

        system_prompt = self._build_system_prompt(display_size)
        recent_history = ""
        if action_history:
            last_few = action_history[-4:]
            recent_history = f"\nRecent actions taken: {json.dumps(last_few)}"

        prompt = (
            f"Step {step_number}.\n"
            f"Target Task: {task}\n"
            f"{recent_history}\n"
            "Inspect the current screenshot and output the required actions as JSON."
        )

        jpeg_bytes = self._prepare_jpeg_bytes(screenshot_bytes, screenshot_b64=screenshot_b64)

        last_error = ""
        attempt = 1
        max_attempts = self.max_retries + 1  # Allowance for license agreement step

        while attempt <= max_attempts:
            try:
                if self.use_openai_compat:
                    api_resp = self._call_openai_compat(prompt, system_prompt, screenshot_b64)
                else:
                    try:
                        api_resp = self._call_direct_rest(prompt, system_prompt, jpeg_bytes)
                    except ModelAgreementRequiredError:
                        raise
                    except Exception as rest_err:
                        logger.debug(
                            f"Direct REST call attempt failed ({rest_err}), trying OpenAI-compat endpoint..."
                        )
                        api_resp = self._call_openai_compat(prompt, system_prompt, screenshot_b64)

                raw_text = self._extract_text_content(api_resp)
                parsed = self._parse_model_json(raw_text)

                thought = parsed.get("thought", "")
                status = str(parsed.get("status", "in_progress")).lower()
                is_finished = status in ("complete", "finished", "done")

                raw_actions = parsed.get("actions", [])
                if not raw_actions and ("action" in parsed or "url" in parsed or "coordinate" in parsed):
                    raw_actions = [parsed]

                provider_actions: List[ProviderAction] = []

                for act in raw_actions:
                    if not isinstance(act, dict):
                        continue

                    act_type = (act.get("action") or act.get("type") or act.get("tool") or act.get("name") or "").lower().strip()
                    if act_type == "type" and ("url" in act or act.get("text", "").startswith(("http://", "https://"))):
                        act_type = "open_url"
                        if "url" not in act and "text" in act:
                            act["url"] = act["text"]

                    c_tuple = _parse_coordinate(act.get("coordinate"))
                    sc_tuple = _parse_coordinate(act.get("start_coordinate"))

                    provider_actions.append(
                        ProviderAction(
                            action_type=act_type,
                            coordinate=c_tuple,
                            start_coordinate=sc_tuple,
                            text=act.get("text"),
                            key=act.get("key"),
                            keys=act.get("keys"),
                            duration=act.get("duration"),
                            clicks=act.get("clicks"),
                            raw_params=act,
                        )
                    )

                return ModelResponse(
                    thought=thought,
                    actions=provider_actions,
                    is_finished=is_finished,
                    raw_response=api_resp,
                )

            except ModelAgreementRequiredError:
                logger.info(
                    "Meta Llama license agreement required by Cloudflare. Automatically submitting 'agree'..."
                )
                self._accept_model_agreement()
                time.sleep(1.0)
                # Retry immediately
                attempt += 1
                continue

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Cloudflare AI attempt {attempt}/{self.max_retries} failed: {e}"
                )
                if attempt < max_attempts:
                    backoff = min(8.0, attempt * 2.0)
                    time.sleep(backoff)
                attempt += 1

        return ModelResponse(
            error=f"Cloudflare AI request failed after attempts: {last_error}"
        )

    def generate_random_youtube_topic(self) -> Optional[str]:
        """Ask Cloudflare Workers AI to suggest a random, creative YouTube search topic."""
        if not self.is_configured():
            return None

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        prompt = (
            "Suggest one single fascinating, creative, and specific YouTube search query. "
            "Examples: relaxing ambient soundscapes, coding tutorials, science documentaries, "
            "space exploration, mechanical keyboard build, 4K nature drone films, game speedruns, "
            "or vintage electronics restoration. "
            "Output ONLY the search query string, under 50 characters, with no quotes or extra text."
        )

        candidates = [
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/@cf/meta/llama-3.1-8b-instruct",
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/@cf/meta/llama-3.2-3b-instruct",
            self.openai_compat_url,
        ]

        for url in candidates:
            try:
                if "chat/completions" in url:
                    payload = {
                        "model": "@cf/meta/llama-3.1-8b-instruct",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 40,
                    }
                else:
                    payload = {"prompt": prompt}

                resp = requests.post(url, headers=headers, json=payload, timeout=8.0)
                if resp.status_code == 200:
                    data = resp.json()
                    res_text = ""
                    if "result" in data:
                        res = data["result"]
                        res_text = res.get("response", "") if isinstance(res, dict) else str(res)
                    elif "choices" in data and len(data["choices"]) > 0:
                        res_text = data["choices"][0].get("message", {}).get("content", "")

                    clean = res_text.strip().strip('"\'`').split("\n")[0].strip()
                    if clean and len(clean) >= 4:
                        logger.info(f"Cloudflare AI generated creative YouTube topic: '{clean}'")
                        return clean
            except Exception as e:
                logger.debug(f"Cloudflare topic generation attempt failed ({url}): {e}")

        return None
