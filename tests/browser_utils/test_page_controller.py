from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_utils.page_controller import PageController
from models import ClientDisconnectedError


@pytest.mark.asyncio
async def test_page_controller_initialization(mock_page: MagicMock):
    """Test PageController initialization and mixin inheritance."""
    logger = MagicMock()
    req_id = "test_req_id"

    controller = PageController(mock_page, logger, req_id)

    assert controller.page == mock_page
    assert controller.logger == logger
    assert controller.req_id == req_id
    assert hasattr(controller, "submit_prompt")
    assert hasattr(controller, "get_response")
    assert hasattr(controller, "_check_disconnect")
    assert isinstance(controller, PageController)


@pytest.mark.asyncio
async def test_page_controller_delegation(mock_page: MagicMock):
    """Test that PageController delegates methods to mixins correctly."""
    logger = MagicMock()
    req_id = "test_req_id"
    controller = PageController(mock_page, logger, req_id)

    with patch.object(
        controller, "submit_prompt", new_callable=AsyncMock
    ) as mock_submit:
        await controller.submit_prompt("test prompt", [], MagicMock())
        mock_submit.assert_called_once_with(
            "test prompt", [], mock_submit.call_args[0][2]
        )


@pytest.mark.asyncio
async def test_page_controller_check_disconnect(mock_page: MagicMock):
    """Test _check_disconnect method from BaseController."""
    logger = MagicMock()
    req_id = "test_req_id"
    controller = PageController(mock_page, logger, req_id)

    mock_check_func = MagicMock()
    with pytest.raises(ClientDisconnectedError):
        await controller._check_disconnect(
            stage="test stage", check_client_disconnected=mock_check_func
        )

    mock_check_func.side_effect = ClientDisconnectedError("Disconnected")
    with pytest.raises(ClientDisconnectedError):
        mock_check_func("test")
    with pytest.raises(ClientDisconnectedError):
        await controller._check_disconnect(
            stage="test stage", check_client_disconnected=mock_check_func
        )


@pytest.mark.asyncio
async def test_page_controller_extract_dom_content_excludes_thoughts(
    mock_page: MagicMock,
):
    """DOM extraction should exclude Thoughts and keep only final body text."""
    logger = MagicMock()
    controller = PageController(mock_page, logger, "test_req_id")
    mock_page.evaluate = AsyncMock(return_value="body content")

    result = await controller._extract_dom_content()

    assert result == "body content"


def test_page_controller_separate_analysis_and_answer_tags(mock_page: MagicMock):
    """Structured analysis/answer output should be split correctly."""
    controller = PageController(mock_page, MagicMock(), "test_req_id")

    content, reasoning = controller._separate_thinking_and_response(
        "<analysis>先分析问题</analysis>\n<answer>最终答案</answer>"
    )

    assert content == "最终答案"
    assert reasoning == "先分析问题"


def test_page_controller_separate_thinking_and_plain_text(mock_page: MagicMock):
    """Plain final text should remain while tagged thinking is separated."""
    controller = PageController(mock_page, MagicMock(), "test_req_id")

    content, reasoning = controller._separate_thinking_and_response(
        "[THINKING]内部推理[/THINKING]\n这里是最终正文"
    )

    assert content == "这里是最终正文"
    assert reasoning == "内部推理"


@pytest.mark.asyncio
async def test_page_controller_get_response_with_function_calls_strips_analysis_answer(
    mock_page: MagicMock,
):
    """Response path should return split answer content."""
    controller = PageController(mock_page, MagicMock(), "test_req_id")

    with (
        patch.object(controller, "get_response", new_callable=AsyncMock) as mock_get,
        patch.object(
            controller, "parse_function_calls", new_callable=AsyncMock
        ) as mock_parse,
    ):
        mock_get.return_value = "<analysis>先分析</analysis><answer>最终输出</answer>"
        mock_parse.return_value = (False, [], "")

        result = await controller.get_response_with_function_calls(
            MagicMock(return_value=False)
        )

    assert result["content"] == "最终输出"
    assert result["reasoning_content"] == "先分析"
    assert result["raw_content"] == "<analysis>先分析</analysis><answer>最终输出</answer>"
