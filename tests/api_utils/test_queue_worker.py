from unittest.mock import AsyncMock, MagicMock, patch
import importlib

import pytest

queue_worker_module = importlib.import_module("api_utils.queue_worker")
_force_goto_new_chat = queue_worker_module._force_goto_new_chat


@pytest.mark.asyncio
async def test_force_goto_new_chat_success():
    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.evaluate = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    locator = MagicMock()
    page.locator = MagicMock(return_value=locator)
    logger = MagicMock()

    expect_result = MagicMock()
    expect_result.to_be_visible = AsyncMock()

    with patch.object(queue_worker_module, "expect_async", return_value=expect_result):
        result = await _force_goto_new_chat(page, logger, "req1", "测试恢复")

    assert result is True
    page.evaluate.assert_awaited_once_with("window.stop()")
    page.goto.assert_awaited_once()
    expect_result.to_be_visible.assert_awaited_once()
    page.wait_for_load_state.assert_awaited_once_with("networkidle", timeout=10000)
    page.wait_for_function.assert_awaited_once()
    page.keyboard.press.assert_awaited_once_with("Escape")


@pytest.mark.asyncio
async def test_force_goto_new_chat_returns_false_on_goto_error():
    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.evaluate = AsyncMock()
    page.goto = AsyncMock(side_effect=Exception("nav failed"))
    page.wait_for_load_state = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    logger = MagicMock()

    result = await _force_goto_new_chat(page, logger, "req1", "测试恢复")

    assert result is False
    logger.error.assert_called()
