"""
PageController Module
Encapsulates all complex logic for direct interaction with Playwright pages.
"""

import asyncio
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from playwright.async_api import Page as AsyncPage

from config import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_STOP_SEQUENCES,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    EDIT_MESSAGE_BUTTON_SELECTOR,
    ENABLE_URL_CONTEXT,
    PROMPT_TEXTAREA_SELECTOR,
    SUBMIT_BUTTON_SELECTOR,
)
from models import ClientDisconnectedError

from .operations import (
    _get_final_response_content,
    _wait_for_response_completion,
    get_response_via_copy_button,
    get_response_via_edit_button,
)
from .page_controller_modules.base import BaseController
from .page_controller_modules.chat import ChatController
from .page_controller_modules.function_calling import FunctionCallingController
from .page_controller_modules.input import InputController
from .page_controller_modules.parameters import ParameterController
from .page_controller_modules.response import ResponseController
from .page_controller_modules.thinking import ThinkingController


class PageController(
    ParameterController,
    InputController,
    ChatController,
    ResponseController,
    ThinkingController,
    FunctionCallingController,
    BaseController,
):
    """Encapsulates all operations for interacting with the AI Studio page."""

    def __init__(self, page: AsyncPage, logger, req_id: str):
        self.page = page
        self.logger = logger
        self.req_id = req_id

    async def _check_disconnect(self, check_client_disconnected: Callable, stage: str):
        if check_client_disconnected(stage):
            raise ClientDisconnectedError(
                f"[{self.req_id}] Client disconnected at stage: {stage}"
            )

    async def adjust_parameters(
        self,
        request_params: Dict[str, Any],
        page_params_cache: Dict[str, Any],
        params_cache_lock: asyncio.Lock,
        model_id_to_use: Optional[str],
        parsed_model_list: List[Dict[str, Any]],
        check_client_disconnected: Callable,
        is_streaming: bool = True,
    ):
        self.logger.info(f"[{self.req_id}] Adjusting parameters...")
        await self._check_disconnect(
            check_client_disconnected, "Start Parameter Adjustment"
        )
        temp = request_params.get("temperature", DEFAULT_TEMPERATURE)
        await self._adjust_temperature(
            temp, page_params_cache, params_cache_lock, check_client_disconnected
        )
        max_tokens = request_params.get("max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS)
        await self._adjust_max_tokens(
            max_tokens,
            page_params_cache,
            params_cache_lock,
            model_id_to_use,
            parsed_model_list,
            check_client_disconnected,
        )
        stop = request_params.get("stop", DEFAULT_STOP_SEQUENCES)
        await self._adjust_stop_sequences(
            stop, page_params_cache, params_cache_lock, check_client_disconnected
        )
        top_p = request_params.get("top_p", DEFAULT_TOP_P)
        await self._adjust_top_p(top_p, check_client_disconnected)
        await self._ensure_tools_panel_expanded(check_client_disconnected)

        # Force disable URL context if function calling is active
        is_fc_enabled = await self.is_function_calling_enabled(
            check_client_disconnected
        )
        if is_fc_enabled:
            await self._adjust_url_context(False, check_client_disconnected)
        elif ENABLE_URL_CONTEXT:
            await self._adjust_url_context(True, check_client_disconnected)

        # 先调整 Google Search，避免其启用时锁死思考模式开关
        await self._adjust_google_search(
            request_params, model_id_to_use, check_client_disconnected
        )
        await self._handle_thinking_budget(
            request_params,
            page_params_cache,
            params_cache_lock,
            model_id_to_use,
            check_client_disconnected,
            is_streaming,
        )

    async def clear_chat_history(self, check_client_disconnected: Callable):
        """Clear chat history and invalidate function calling cache.

        Delegates to the robust ChatController.clear_chat_history implementation
        which includes: submit-button stop (to halt ongoing AI generation),
        backdrop/overlay dismissal, retry logic, dialog-disappear verification,
        and temporary-chat-mode re-enabling.

        The previous simple override here lacked all of these safeguards and
        could hang indefinitely on enable_temporary_chat_mode() when the page
        was in a transitional or error state.
        """
        self.logger.info(f"[{self.req_id}] Clearing chat history...")

        # Invalidate FC cache since we're starting a new chat
        self.invalidate_fc_cache("new_chat")

        # Delegate to the inherited ChatController implementation which has
        # comprehensive error handling, retry logic, and submit-button stop.
        await ChatController.clear_chat_history(self, check_client_disconnected)

    # NOTE: submit_prompt() is intentionally NOT overridden here.
    # The inherited InputController.submit_prompt uses Playwright's native fill()
    # which properly updates Angular's reactive form state. The previous override
    # used element.value = text via evaluate(), bypassing the ControlValueAccessor
    # and causing AI Studio to receive empty/stale prompt data → 403 Forbidden.
    #
    # Similarly, _open_upload_menu_and_choose_file() is inherited from
    # InputController which has a more robust implementation with overlay
    # handling, menu visibility waits, and multiple selector fallbacks.

    async def get_response(
        self,
        check_client_disconnected: Callable,
        prompt_length: int = 0,
        timeout: Optional[float] = None,
    ) -> str:
        """Retrieve response content."""
        submit_btn = self.page.locator(SUBMIT_BUTTON_SELECTOR)
        edit_btn = self.page.locator(EDIT_MESSAGE_BUTTON_SELECTOR)
        input_field = self.page.locator(PROMPT_TEXTAREA_SELECTOR)
        await _wait_for_response_completion(
            self.page,
            input_field,
            submit_btn,
            edit_btn,
            self.req_id,
            check_client_disconnected,
            None,
            prompt_length=prompt_length,
            timeout=timeout,
        )
        content = await _get_final_response_content(
            self.page, self.req_id, check_client_disconnected
        )
        if not content or not content.strip():
            verified = await self.verify_response_integrity(check_client_disconnected)
            return verified.get("content", "")
        return content

    async def verify_response_integrity(
        self, check_client_disconnected: Callable, trigger_reason: str = ""
    ) -> Dict[str, str]:
        """Verify integrity via DOM."""
        await asyncio.sleep(1)
        final = await self._extract_complete_response_content()
        content, reasoning = self._separate_thinking_and_response(final)
        return {"content": content, "reasoning_content": reasoning}

    async def get_response_with_integrity_check(
        self,
        check_client_disconnected: Callable,
        prompt_length: int = 0,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Retrieve response content with full integrity check and function calls."""
        content = await self.get_response(
            check_client_disconnected, prompt_length, timeout
        )

        # Parse function calls from DOM as well
        has_fc, function_calls, text_content = await self.parse_function_calls(
            check_client_disconnected
        )

        c, r = self._separate_thinking_and_response(content)

        result = {
            "content": c,
            "reasoning_content": r,
            "recovery_method": "direct",
            "has_function_calls": has_fc,
            "function_calls": function_calls,
        }

        if has_fc:
            # If function calls found, use the text content (with calls removed) as content
            # But we need to separate thinking from it too
            c_fc, r_fc = self._separate_thinking_and_response(text_content)
            result["content"] = c_fc
            # Keep original reasoning if not found in text_content
            if r_fc:
                result["reasoning_content"] = r_fc

        return result

    def _separate_thinking_and_response(self, content: str) -> Tuple[str, str]:
        """Separate thinking and response."""
        if not content:
            return "", ""
        reasoning_parts = []
        reasoning_parts.extend(
            self._extract_tagged_sections(content, r"\[THINKING\](.*?)\[/THINKING\]")
        )
        for tag_name in ("analysis", "thinking", "reasoning"):
            reasoning_parts.extend(
                self._extract_tagged_sections(
                    content, rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>"
                )
            )

        answer_parts = []
        for tag_name in ("answer", "final"):
            answer_parts.extend(
                self._extract_tagged_sections(
                    content, rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>"
                )
            )

        body_content = re.sub(
            r"\[THINKING\](.*?)\[/THINKING\]",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        for tag_name in ("analysis", "thinking", "reasoning", "answer", "final"):
            body_content = re.sub(
                rf"<{tag_name}\b[^>]*>.*?</{tag_name}>",
                "",
                body_content,
                flags=re.DOTALL | re.IGNORECASE,
            )

        reasoning_content = "\n\n".join(reasoning_parts).strip()
        body_content = re.sub(r"\n{3,}", "\n\n", body_content).strip()
        final_content = "\n\n".join(answer_parts).strip() if answer_parts else body_content
        return final_content, reasoning_content

    def _extract_tagged_sections(self, content: str, pattern: str) -> List[str]:
        """提取结构化思考或答案片段。"""
        matches = re.findall(pattern, content, flags=re.DOTALL | re.IGNORECASE)
        return [match.strip() for match in matches if match and match.strip()]

    async def _emergency_stability_wait(
        self, check_client_disconnected: Callable
    ) -> bool:
        """Wait for DOM stability."""
        await asyncio.sleep(2)
        return True

    async def _check_generation_activity(self) -> bool:
        """Check if generation is in progress."""
        stop_btn = self.page.locator('button[aria-label="Stop generating"]')
        return await stop_btn.is_visible(timeout=500)

    async def _extract_dom_content(self) -> str:
        """Extract content from DOM."""
        dom_text = await self.page.evaluate(
            """
            () => {
                const normalize = (text) => (text || '')
                    .replace(/\\r/g, '')
                    .split('\\n')
                    .map((line) => line.trimEnd())
                    .join('\\n')
                    .trim();

                const extractVisibleText = (node) => {
                    if (!node) return '';
                    const clone = node.cloneNode(true);
                    clone.querySelectorAll('ms-thought-chunk, .thought-panel, [aria-label="Thoughts"]').forEach((el) => el.remove());
                    return normalize(clone.innerText || clone.textContent || '');
                };

                const lastTurn = document.querySelector('ms-chat-turn:last-of-type');
                if (!lastTurn) {
                    return '';
                }

                const preferredNodes = [
                    ...lastTurn.querySelectorAll(
                        '[data-turn-role="Model"] ms-prompt-chunk.text-chunk,' +
                        ' [data-turn-role="Model"] .text-chunk,' +
                        ' .model-prompt-container ms-prompt-chunk.text-chunk,' +
                        ' .model-prompt-container .text-chunk'
                    )
                ];

                for (const node of preferredNodes) {
                    const text = extractVisibleText(node);
                    if (text) {
                        return text;
                    }
                }

                const fallbackNodes = [
                    ...lastTurn.querySelectorAll(
                        '[data-turn-role="Model"], .model-prompt-container, ms-prompt-chunk'
                    )
                ];
                for (const node of fallbackNodes) {
                    const text = extractVisibleText(node);
                    if (text) {
                        return text;
                    }
                }

                return '';
            }
            """
        )
        return dom_text if isinstance(dom_text, str) else ""

    async def _extract_complete_response_content(self) -> str:
        """Extract complete response content."""
        c = await get_response_via_edit_button(self.page, self.req_id, lambda x: None)
        if not c:
            c = await get_response_via_copy_button(
                self.page, self.req_id, lambda x: None
            )
        return c if c else await self._extract_dom_content()

    async def get_body_text_only_from_dom(self) -> str:
        """Extract body text only."""
        return await self._extract_dom_content()
