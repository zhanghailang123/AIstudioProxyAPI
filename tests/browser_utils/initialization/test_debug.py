"""
Tests for browser_utils/initialization/debug.py
Target coverage: >80% (from baseline 10%)
"""

import asyncio
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest

from browser_utils.initialization.debug import setup_debug_listeners


@pytest.fixture
def mock_page():
    """Create mock page"""
    page = Mock()
    page.on = Mock()
    return page


@pytest.fixture
def mock_state_with_logs():
    """Create a mock state with console_logs and network_log that we can inspect."""
    mock_state = Mock()
    mock_state.console_logs = []
    mock_state.network_log = {"requests": [], "responses": []}

    with patch("api_utils.server_state.state", mock_state):
        yield mock_state


@pytest.fixture
def mock_console_message():
    """Create mock console message"""
    msg = Mock()
    msg.type = "log"
    msg.text = "test message"
    msg.location = {"url": "https://example.com/page.js", "lineNumber": 42}
    return msg


@pytest.fixture
def mock_request():
    """Create mock network request"""
    req = Mock()
    req.url = "https://example.com/api/data"
    req.method = "GET"
    req.resource_type = "xhr"
    return req


@pytest.fixture
def mock_response():
    """Create mock network response"""
    resp = Mock()
    resp.url = "https://example.com/api/data"
    resp.status = 200
    resp.status_text = "OK"
    return resp


def test_listeners_attached(mock_page, mock_state_with_logs):
    """Test all listeners attached"""
    setup_debug_listeners(mock_page)

    assert mock_page.on.call_count == 3

    listener_names = [call_args[0][0] for call_args in mock_page.on.call_args_list]
    assert "console" in listener_names
    assert "request" in listener_names
    assert "response" in listener_names


def test_console_handler_log(mock_page, mock_state_with_logs, mock_console_message):
    """Test console log captured"""
    setup_debug_listeners(mock_page)

    # Extract console handler
    console_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "console":
            console_handler = call_args[0][1]
            break

    assert console_handler is not None

    # Trigger handler (datetime is imported inside the handler, no need to mock)
    console_handler(mock_console_message)

    # Verify log captured
    assert len(mock_state_with_logs.console_logs) == 1
    log_entry = mock_state_with_logs.console_logs[0]
    assert log_entry["type"] == "log"
    assert log_entry["text"] == "test message"
    assert "timestamp" in log_entry
    assert "location" in log_entry


def test_console_handler_error(mock_page, mock_state_with_logs):
    """Test console error captured"""
    setup_debug_listeners(mock_page)

    console_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "console":
            console_handler = call_args[0][1]
            break

    error_msg = Mock()
    error_msg.type = "error"
    error_msg.text = "Critical error"
    error_msg.location = {"url": "test.js", "lineNumber": 1}

    assert console_handler is not None
    console_handler(error_msg)

    assert len(mock_state_with_logs.console_logs) == 1
    assert mock_state_with_logs.console_logs[0]["type"] == "error"


def test_request_handler_xhr(mock_page, mock_state_with_logs, mock_request):
    """Test XHR request captured"""
    setup_debug_listeners(mock_page)

    request_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "request":
            request_handler = call_args[0][1]
            break

    assert request_handler is not None
    request_handler(mock_request)

    assert len(mock_state_with_logs.network_log["requests"]) == 1
    req_entry = mock_state_with_logs.network_log["requests"][0]
    assert req_entry["url"] == "https://example.com/api/data"
    assert req_entry["method"] == "GET"
    assert "timestamp" in req_entry


def test_request_handler_image_filtered(mock_page, mock_state_with_logs):
    """Test image request filtered out"""
    setup_debug_listeners(mock_page)

    request_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "request":
            request_handler = call_args[0][1]
            break

    image_req = Mock()
    image_req.url = "https://example.com/logo.png"
    image_req.method = "GET"
    image_req.resource_type = "image"

    assert request_handler is not None
    request_handler(image_req)

    assert len(mock_state_with_logs.network_log["requests"]) == 0


def test_request_handler_css_filtered(mock_page, mock_state_with_logs):
    """Test CSS request filtered out"""
    setup_debug_listeners(mock_page)

    request_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "request":
            request_handler = call_args[0][1]
            break

    css_req = Mock()
    css_req.url = "https://example.com/styles.css"
    css_req.method = "GET"
    css_req.resource_type = "stylesheet"

    assert request_handler is not None
    request_handler(css_req)

    assert len(mock_state_with_logs.network_log["requests"]) == 0


def test_response_handler_success(mock_page, mock_state_with_logs, mock_response):
    """Test successful response captured"""
    setup_debug_listeners(mock_page)

    response_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "response":
            response_handler = call_args[0][1]
            break

    assert response_handler is not None
    response_handler(mock_response)

    assert len(mock_state_with_logs.network_log["responses"]) == 1
    resp_entry = mock_state_with_logs.network_log["responses"][0]
    assert resp_entry["status"] == 200
    assert resp_entry["url"] == "https://example.com/api/data"
    assert "timestamp" in resp_entry


def test_response_handler_error_status(mock_page, mock_state_with_logs):
    """Test error response captured"""
    setup_debug_listeners(mock_page)

    response_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "response":
            response_handler = call_args[0][1]
            break

    error_resp = Mock()
    error_resp.url = "https://example.com/api/error"
    error_resp.status = 404
    error_resp.status_text = "Not Found"

    assert response_handler is not None
    response_handler(error_resp)

    assert len(mock_state_with_logs.network_log["responses"]) == 1
    assert mock_state_with_logs.network_log["responses"][0]["status"] == 404


@pytest.mark.asyncio
async def test_ai_studio_error_response_body_preview(mock_page, mock_state_with_logs):
    """AI Studio 生成错误响应应记录截断后的错误体，便于定位上游原因。"""
    setup_debug_listeners(mock_page)

    response_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "response":
            response_handler = call_args[0][1]
            break

    error_resp = Mock()
    error_resp.url = (
        "https://aistudio.google.com/_/MakerSuiteUi/data/batchexecute"
        "?rpcids=GenerateContent"
    )
    error_resp.status = 403
    error_resp.status_text = "Forbidden"
    error_resp.text = AsyncMock(
        return_value="prefix Failed to generate content: permission denied. Please try again."
    )

    assert response_handler is not None
    with patch("browser_utils.initialization.debug.logger") as mock_logger:
        response_handler(error_resp)
        await asyncio.sleep(0)

    response_entry = mock_state_with_logs.network_log["responses"][0]
    assert response_entry["status"] == 403
    assert "permission denied" in response_entry["body_preview"].lower()
    assert "permission denied" in response_entry["error_markers"]
    assert mock_logger.warning.called


@pytest.mark.asyncio
async def test_ai_studio_permission_rpc_body_marker(mock_page, mock_state_with_logs):
    """gRPC status 7 权限拒绝响应应标记为 permission 类错误。"""
    setup_debug_listeners(mock_page)

    response_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "response":
            response_handler = call_args[0][1]
            break

    error_resp = Mock()
    error_resp.url = (
        "https://alkalimakersuite-pa.clients6.google.com/$rpc/"
        "google.internal.alkali.applications.makersuite.v1."
        "MakerSuiteService/GenerateContent"
    )
    error_resp.status = 403
    error_resp.status_text = "Forbidden"
    error_resp.text = AsyncMock(
        return_value='[,[7,"The caller does not have permission"]]'
    )

    assert response_handler is not None
    response_handler(error_resp)
    await asyncio.sleep(0)

    response_entry = mock_state_with_logs.network_log["responses"][0]
    assert "caller does not have permission" in response_entry["body_preview"].lower()
    assert "caller does not have permission" in response_entry["error_markers"]


def test_console_handler_exception_caught(mock_page, mock_state_with_logs):
    """Test exception in console handler caught"""
    setup_debug_listeners(mock_page)

    console_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "console":
            console_handler = call_args[0][1]
            break

    bad_msg = Mock()
    # Use PropertyMock to raise exception when .text is accessed as property
    type(bad_msg).text = PropertyMock(side_effect=RuntimeError("Extraction failed"))

    assert console_handler is not None
    with patch("browser_utils.initialization.debug.logger") as mock_logger:
        # Should not raise
        console_handler(bad_msg)

        # Verify error logged
        assert mock_logger.error.called


def test_request_handler_exception_caught(mock_page, mock_state_with_logs):
    """Test exception in request handler caught"""
    setup_debug_listeners(mock_page)

    request_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "request":
            request_handler = call_args[0][1]
            break

    bad_req = Mock()
    bad_req.url = Mock(side_effect=RuntimeError("URL access failed"))

    assert request_handler is not None
    with patch("browser_utils.initialization.debug.logger") as mock_logger:
        request_handler(bad_req)
        assert mock_logger.error.called
