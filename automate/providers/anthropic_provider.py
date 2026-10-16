"""Anthropic Claude Computer Use provider for AutoMate."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import anthropic

from automate.logger import get_logger
from automate.providers.base import BaseAIProvider, ModelResponse, ProviderAction

logger = get_logger("automate.providers.anthropic")


class AnthropicProvider(BaseAIProvider):
    """Integrates with Anthropic Claude Computer Use API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.api_key = api_key.strip() if api_key else ""
        self.model = model.strip() if model else "claude-sonnet-4-20250514"
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_tool_def(self, display_size: Tuple[int, int]) -> Dict[str, Any]:
        tool_type = "computer_20241022" if "20241022" in self.model else "computer_20250124"
        return {
            "type": tool_type,
            "name": "computer",
            "display_width_px": display_size[0],
            "display_height_px": display_size[1],
            "display_number": 1,
        }

    def _get_beta_name(self) -> str:
        if "20241022" in self.model:
            return "computer-use-2024-10-22"
        return "computer-use-2025-01-24"

    def decide_next_step(
        self,
        task: str,
        screenshot_bytes: bytes,
        screenshot_b64: str,
        display_size: Tuple[int, int],
        action_history: List[Dict[str, Any]],
        step_number: int,
    ) -> ModelResponse:
        if not self.is_configured() or not self.client:
            return ModelResponse(error="Anthropic API key is not configured.")

        system_prompt = (
            "You are AutoMate, an intelligent Windows desktop automation agent. "
            "You perceive the screen through screenshots and accomplish tasks using the 'computer' tool. "
            "Always inspect the visual context carefully before taking action. "
            "When the task is completely finished, provide a concise summary of what was accomplished "
            "without calling any more tools."
        )

        tool_def = self._get_tool_def(display_size)
        beta_name = self._get_beta_name()

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Task: {task}\nStep: {step_number}",
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                ],
            }
        ]

        try:
            try:
                response = self.client.beta.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=system_prompt,
                    tools=[tool_def],
                    messages=messages,
                    betas=[beta_name],
                )
            except (AttributeError, TypeError):
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=system_prompt,
                    tools=[tool_def],
                    messages=messages,
                    extra_headers={"anthropic-beta": beta_name},
                )

            thought_chunks = []
            provider_actions: List[ProviderAction] = []

            for block in response.content:
                if block.type == "text":
                    thought_chunks.append(block.text)
                elif block.type == "tool_use":
                    inp = block.input
                    act_name = inp.get("action", block.name)
                    coord = inp.get("coordinate")
                    c_tuple = (int(coord[0]), int(coord[1])) if coord and len(coord) >= 2 else None
                    start_coord = inp.get("start_coordinate")
                    sc_tuple = (
                        (int(start_coord[0]), int(start_coord[1]))
                        if start_coord and len(start_coord) >= 2
                        else None
                    )

                    provider_actions.append(
                        ProviderAction(
                            action_type=act_name,
                            coordinate=c_tuple,
                            start_coordinate=sc_tuple,
                            text=inp.get("text"),
                            key=inp.get("key") or inp.get("text"),
                            keys=inp.get("keys"),
                            duration=inp.get("duration"),
                            clicks=inp.get("clicks"),
                            raw_params=inp,
                        )
                    )

            thought = "\n".join(thought_chunks).strip()
            is_finished = len(provider_actions) == 0

            return ModelResponse(
                thought=thought,
                actions=provider_actions,
                is_finished=is_finished,
                raw_response=response,
            )

        except Exception as e:
            logger.error(f"Anthropic provider call failed: {e}")
            return ModelResponse(error=str(e))
