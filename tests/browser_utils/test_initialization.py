import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from playwright.async_api import Error as PlaywrightAsyncError

from browser_utils.initialization import (
    _close_page_logic,
    _initialize_page_logic,
    enable_temporary_chat_mode,
    signal_camoufox_shutdown,
)
from browser_utils.initialization.core import _wait_for_shutdown

# --- Existing Tests (Preserved) ---


@pytest.mark.asyncio
async def test_initialize_page_logic_success(
    mock_browser,
    mock_browser_context,
    mock_page,
    mock_env,
    mock_expect,
    mock_server_state,
):
    # Mock state
    mock_server_state.PLAYWRIGHT_PROXY_SETTINGS = None
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        # Mock page finding logic
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.is_closed = MagicMock(return_value=False)
        mock_browser_context.pages = [mock_page]

        # Mock locators for verification
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        mock_browser.new_context.assert_called()


@pytest.mark.asyncio
async def test_initialize_page_logic_new_page(
    mock_browser,
    mock_browser_context,
    mock_page,
    mock_env,
    mock_expect,
    mock_server_state,
):
    mock_server_state.PLAYWRIGHT_PROXY_SETTINGS = None
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"

        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        mock_page.goto.assert_called()


@pytest.mark.asyncio
async def test_close_page_logic_success():
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)

    from api_utils.server_state import state

    original_page = state.page_instance
    original_ready = state.is_page_ready

    try:
        state.page_instance = mock_page
        state.is_page_ready = True

        await _close_page_logic()

        mock_page.close.assert_called()
        assert state.page_instance is None
        assert state.is_page_ready is False
    finally:
        state.page_instance = original_page
        state.is_page_ready = original_ready


@pytest.mark.asyncio
async def test_close_page_logic_already_closed():
    from api_utils.server_state import state

    original_page = state.page_instance

    try:
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=True)
        state.page_instance = mock_page

        await _close_page_logic()

        mock_page.close.assert_not_called()
        assert state.page_instance is None
    finally:
        state.page_instance = original_page


@pytest.mark.asyncio
async def test_initialize_page_logic_headless_auth_missing(
    mock_browser, mock_env, mock_server_state
):
    """Test that headless mode raises when ACTIVE_AUTH_JSON_PATH is empty."""
    with (
        patch.dict(
            os.environ,
            {
                "LAUNCH_MODE": "headless",
                "ACTIVE_AUTH_JSON_PATH": "",
                "AUTO_AUTH_ROTATION_ON_STARTUP": "false",
            },
        ),
    ):
        with pytest.raises(RuntimeError) as exc:
            await _initialize_page_logic(mock_browser)
        assert "ACTIVE_AUTH_JSON_PATH" in str(exc.value)


@pytest.mark.asyncio
async def test_initialize_page_logic_proxy_settings(
    mock_browser,
    mock_browser_context,
    mock_page,
    mock_env,
    mock_expect,
    mock_server_state,
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_server_state.PLAYWRIGHT_PROXY_SETTINGS = {"server": "http://proxy:8080"}

        mock_browser_context.pages = [mock_page]
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.is_closed.return_value = False

        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        await _initialize_page_logic(mock_browser)

        call_args = mock_browser.new_context.call_args
        assert call_args is not None
        assert call_args[1]["proxy"] == {"server": "http://proxy:8080"}


@pytest.mark.asyncio
async def test_initialize_page_logic_reuses_existing_ai_studio_page(
    mock_browser,
    mock_browser_context,
    mock_page,
    mock_expect,
    mock_server_state,
):
    with (
        patch.dict(
            os.environ,
            {"LAUNCH_MODE": "debug", "REUSE_EXISTING_AISTUDIO_PAGE": "true"},
        ),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ) as mock_setup,
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = [mock_page]
        mock_browser.contexts = [mock_browser_context]
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        mock_browser.new_context.assert_not_called()
        mock_browser_context.new_page.assert_not_called()
        mock_setup.assert_awaited_once_with(mock_browser_context)
        assert mock_server_state.current_auth_profile_path is None


@pytest.mark.asyncio
async def test_initialize_page_logic_reuse_disabled_ignores_browser_contexts(
    mock_browser,
    mock_browser_context,
    mock_page,
    mock_expect,
    mock_server_state,
):
    with (
        patch.dict(
            os.environ,
            {"LAUNCH_MODE": "debug", "REUSE_EXISTING_AISTUDIO_PAGE": "false"},
        ),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        existing_page = AsyncMock()
        existing_page.url = "https://aistudio.google.com/prompts/new_chat"
        existing_page.is_closed = MagicMock(return_value=False)
        mock_browser.contexts = [AsyncMock(pages=[existing_page])]

        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        mock_browser.new_context.assert_called_once()
        mock_browser_context.new_page.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_page_logic_closes_blank_launcher_pages(
    mock_browser,
    mock_browser_context,
    mock_page,
    mock_expect,
    mock_server_state,
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        blank_page = AsyncMock()
        blank_page.url = "about:blank"
        blank_page.is_closed = MagicMock(return_value=False)
        blank_page.close = AsyncMock()

        launcher_context = AsyncMock()
        launcher_context.pages = [blank_page]

        mock_browser.contexts = [launcher_context]
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        blank_page.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_page_logic_does_not_close_non_blank_pages(
    mock_browser,
    mock_browser_context,
    mock_page,
    mock_expect,
    mock_server_state,
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        existing_page = AsyncMock()
        existing_page.url = "https://example.com/dashboard"
        existing_page.is_closed = MagicMock(return_value=False)
        existing_page.close = AsyncMock()

        other_context = AsyncMock()
        other_context.pages = [existing_page]

        mock_browser.contexts = [other_context]
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        existing_page.close.assert_not_called()


@pytest.mark.asyncio
async def test_initialize_page_logic_reuse_strict_fails_without_existing_page(
    mock_browser,
    mock_browser_context,
    mock_server_state,
):
    with (
        patch.dict(
            os.environ,
            {
                "LAUNCH_MODE": "debug",
                "REUSE_EXISTING_AISTUDIO_PAGE": "true",
                "REUSE_EXISTING_AISTUDIO_PAGE_STRICT": "true",
                "REUSE_EXISTING_AISTUDIO_WAIT_SECONDS": "0",
            },
        ),
        patch("os.path.exists", return_value=False),
    ):
        mock_browser.contexts = []

        with pytest.raises(RuntimeError, match="STRICT"):
            await _initialize_page_logic(mock_browser)

        mock_browser.new_context.assert_not_called()


@pytest.mark.asyncio
async def test_initialize_page_logic_reuse_strict_skipped_for_project_browser(
    mock_browser,
    mock_browser_context,
    mock_page,
    mock_expect,
    mock_server_state,
):
    with (
        patch.dict(
            os.environ,
            {
                "LAUNCH_MODE": "debug",
                "CAMOUFOX_BROWSER_LAUNCHED_BY_PROJECT": "true",
                "REUSE_EXISTING_AISTUDIO_PAGE": "true",
                "REUSE_EXISTING_AISTUDIO_PAGE_STRICT": "true",
                "REUSE_EXISTING_AISTUDIO_WAIT_SECONDS": "0",
            },
        ),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser.contexts = []
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        mock_browser.new_context.assert_called_once()
        mock_browser_context.new_page.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_shutdown_task_is_cancellable():
    task = asyncio.create_task(_wait_for_shutdown())
    await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


# --- New Tests ---

# 1. Storage State & Launch Modes


@pytest.mark.asyncio
async def test_init_storage_state_explicit_exists(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    with (
        patch("os.path.exists", return_value=True),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(
            mock_browser, storage_state_path="/path/to/auth.json"
        )

        call_args = mock_browser.new_context.call_args
        assert call_args[1]["storage_state"] == "/path/to/auth.json"


@pytest.mark.asyncio
async def test_init_storage_state_explicit_missing(mock_browser):
    with patch("os.path.exists", return_value=False):
        with pytest.raises(RuntimeError, match="Specified auth file does not exist"):
            await _initialize_page_logic(
                mock_browser, storage_state_path="/path/to/missing.json"
            )


@pytest.mark.asyncio
async def test_init_headless_auth_exists(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    with (
        patch.dict(
            os.environ,
            {
                "LAUNCH_MODE": "headless",
                "ACTIVE_AUTH_JSON_PATH": "/env/auth.json",
                "AUTO_AUTH_ROTATION_ON_STARTUP": "false",
            },
        ),
        patch("os.path.exists", return_value=True),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert call_args[1]["storage_state"] == "/env/auth.json"


@pytest.mark.asyncio
async def test_init_headless_auth_invalid(mock_browser):
    with (
        patch.dict(
            os.environ,
            {
                "LAUNCH_MODE": "headless",
                "ACTIVE_AUTH_JSON_PATH": "/env/invalid.json",
                "AUTO_AUTH_ROTATION_ON_STARTUP": "false",
            },
        ),
        patch("os.path.exists", return_value=False),
    ):
        with pytest.raises(RuntimeError, match="headless mode auth file invalid"):
            await _initialize_page_logic(mock_browser)


@pytest.mark.asyncio
async def test_init_debug_auth_exists(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    with (
        patch.dict(
            os.environ,
            {"LAUNCH_MODE": "debug", "ACTIVE_AUTH_JSON_PATH": "/env/debug.json"},
        ),
        patch("os.path.exists", return_value=True),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert call_args[1]["storage_state"] == "/env/debug.json"


@pytest.mark.asyncio
async def test_init_debug_auth_missing_file(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    with (
        patch.dict(
            os.environ,
            {"LAUNCH_MODE": "debug", "ACTIVE_AUTH_JSON_PATH": "/env/missing.json"},
        ),
        patch("os.path.exists", return_value=False),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert "storage_state" not in call_args[1]


@pytest.mark.asyncio
async def test_init_direct_debug_no_browser(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    with (
        patch.dict(os.environ, {"LAUNCH_MODE": "direct_debug_no_browser"}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert "storage_state" not in call_args[1]


@pytest.mark.asyncio
async def test_init_unknown_launch_mode(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    with (
        patch.dict(os.environ, {"LAUNCH_MODE": "unknown_mode"}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert "storage_state" not in call_args[1]


# 2. Page Discovery & Navigation Errors


@pytest.mark.asyncio
async def test_init_page_discovery_errors(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    """Test error handling during iteration of existing pages."""
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        # Create 3 pages:
        # 1. Raises PlaywrightAsyncError
        # 2. Raises AttributeError
        # 3. Raises generic Exception
        # 4. Valid page (to ensure loop continues or finishes)

        page1 = AsyncMock()
        page1.is_closed = MagicMock(return_value=False)
        type(page1).url = PropertyMock(side_effect=PlaywrightAsyncError("PW Error"))

        page2 = AsyncMock()
        page2.is_closed = MagicMock(return_value=False)
        type(page2).url = PropertyMock(side_effect=AttributeError("Attr Error"))

        page3 = AsyncMock()
        page3.is_closed = MagicMock(return_value=False)
        type(page3).url = PropertyMock(side_effect=Exception("Generic Error"))

        # We need to mock the pages property to return these
        mock_browser_context.pages = [page1, page2, page3]

        # It should fall through to creating a new page
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)

        # Should have tried to create a new page since no existing one was found
        mock_browser_context.new_page.assert_called()


@pytest.mark.asyncio
async def test_init_new_page_nav_error_generic(
    mock_browser, mock_browser_context, mock_page, mock_server_state
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = Exception("Navigation Failed")

        with pytest.raises(RuntimeError):
            await _initialize_page_logic(mock_browser)

        mock_snapshot.assert_any_call("init_new_page_nav_fail")


@pytest.mark.asyncio
async def test_init_new_page_nav_error_net_interrupt(
    mock_browser, mock_browser_context, mock_page, mock_server_state
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = Exception("NS_ERROR_NET_INTERRUPT")

        with pytest.raises(RuntimeError):
            await _initialize_page_logic(mock_browser)

        mock_snapshot.assert_any_call("init_new_page_nav_fail")


# 3. Login Logic


@pytest.mark.asyncio
async def test_init_login_headless_fail(
    mock_browser, mock_browser_context, mock_page, mock_server_state
):
    # Ensure ACTIVE_AUTH_JSON_PATH is set so we pass the initial check
    with (
        patch.dict(
            "os.environ",
            {"LAUNCH_MODE": "headless", "ACTIVE_AUTH_JSON_PATH": "/path/to/auth.json"},
        ),
        patch("os.path.exists", return_value=True),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        # First URL check (after goto) returns login URL
        mock_page.url = "https://accounts.google.com/signin"
        mock_page.goto = AsyncMock()

        with pytest.raises(RuntimeError) as exc:
            await _initialize_page_logic(mock_browser)
        assert "Auth failed in headless mode" in str(exc.value)


@pytest.mark.asyncio
async def test_init_login_interactive_success(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug", "SUPPRESS_LOGIN_WAIT": "0"}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.core.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch("builtins.input", return_value=""),
        patch("builtins.print"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        # Sequence of URLs:
        # 1. After goto -> signin
        # 2. After wait_for_url -> new_chat
        type(mock_page).url = PropertyMock(
            side_effect=[
                "https://accounts.google.com/signin",
                "https://aistudio.google.com/prompts/new_chat",
                "https://aistudio.google.com/prompts/new_chat",
                "https://aistudio.google.com/prompts/new_chat",
            ]
        )

        mock_page.wait_for_url = AsyncMock()
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)

        mock_page.wait_for_url.assert_called()


@pytest.mark.asyncio
async def test_init_login_interactive_suppress_wait(
    mock_browser, mock_browser_context, mock_page, mock_expect, mock_server_state
):
    with (
        patch.dict(
            "os.environ", {"LAUNCH_MODE": "debug", "SUPPRESS_LOGIN_WAIT": "true"}
        ),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.core.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch("builtins.input") as mock_input,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        type(mock_page).url = PropertyMock(
            side_effect=[
                "https://accounts.google.com/signin",
                "https://aistudio.google.com/prompts/new_chat",
                "https://aistudio.google.com/prompts/new_chat",
                "https://aistudio.google.com/prompts/new_chat",
            ]
        )

        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)

        mock_input.assert_not_called()


@pytest.mark.asyncio
async def test_init_login_interactive_fail_still_login_page(
    mock_browser, mock_browser_context, mock_page, mock_server_state
):
    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug"}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch("builtins.input", return_value=""),
        patch("browser_utils.operations.save_error_snapshot", new_callable=AsyncMock),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        type(mock_page).url = PropertyMock(
            return_value="https://accounts.google.com/signin"
        )

        with pytest.raises(
            RuntimeError, match="Still on login page after manual login attempt"
        ):
            await _initialize_page_logic(mock_browser)


@pytest.mark.asyncio
async def test_init_login_wait_exception(
    mock_browser, mock_browser_context, mock_page, mock_server_state
):
    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug"}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch("builtins.input", return_value=""),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        type(mock_page).url = PropertyMock(
            return_value="https://accounts.google.com/signin"
        )
        mock_page.wait_for_url.side_effect = Exception("Wait Timeout")

        with pytest.raises(RuntimeError):
            await _initialize_page_logic(mock_browser)

        mock_snapshot.assert_any_call("init_login_wait_fail")


# 4. Unexpected Page & Model Name Error


@pytest.mark.asyncio
async def test_init_unexpected_page_url(
    mock_browser, mock_browser_context, mock_page, mock_server_state
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        # Not login, but not target either
        type(mock_page).url = PropertyMock(return_value="https://google.com")

        with pytest.raises(RuntimeError):
            await _initialize_page_logic(mock_browser)

        mock_snapshot.assert_any_call("init_unexpected_page")


@pytest.mark.asyncio
async def test_init_model_name_error(
    mock_browser, mock_browser_context, mock_page, mock_server_state
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"

        mock_expect = MagicMock()
        mock_expect.return_value.to_be_visible = AsyncMock()

        # Override the locator to fail for model-name
        original_locator = mock_page.locator.side_effect

        def failing_locator_factory(selector):
            loc = original_locator()
            if '[data-test-id="model-name"]' in selector:
                loc.first.inner_text = AsyncMock(
                    side_effect=PlaywrightAsyncError("Locator Fail")
                )
            return loc

        mock_page.locator = MagicMock(side_effect=failing_locator_factory)

        with patch("browser_utils.initialization.core.expect_async", mock_expect):
            # The PlaywrightAsyncError is caught and re-raised as RuntimeError
            with pytest.raises(RuntimeError):
                await _initialize_page_logic(mock_browser)


@pytest.mark.asyncio
async def test_init_input_visible_timeout(
    mock_browser, mock_browser_context, mock_page, mock_server_state
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"

        mock_expect = MagicMock()
        # expect_async raises error (timeout)
        mock_expect.return_value.to_be_visible.side_effect = Exception(
            "Timeout waiting for input"
        )

        with patch("browser_utils.initialization.core.expect_async", mock_expect):
            with pytest.raises(RuntimeError):
                await _initialize_page_logic(mock_browser)

            mock_snapshot.assert_any_call("init_fail_input_timeout")


# 5. Cancellation & Generic Errors


@pytest.mark.asyncio
async def test_init_cancelled(mock_browser, mock_browser_context, mock_server_state):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
    ):
        mock_browser.new_context.side_effect = asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await _initialize_page_logic(mock_browser)


@pytest.mark.asyncio
async def test_init_generic_exception_cleanup(
    mock_browser, mock_browser_context, mock_server_state
):
    with (
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        # Fail at setup_network_interception_and_scripts
        with patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            side_effect=Exception("Setup Fail"),
        ):
            with pytest.raises(
                RuntimeError, match="Unexpected page initialization error"
            ):
                await _initialize_page_logic(mock_browser)

            # Verify context was closed
            mock_browser_context.close.assert_called()
            mock_snapshot.assert_called_with("init_unexpected_error")


# 6. Close Page Logic Errors


@pytest.mark.asyncio
async def test_close_page_logic_errors():
    from api_utils.server_state import state

    original_page = state.page_instance

    try:
        mock_page = AsyncMock()
        # is_closed must be a MagicMock returning bool, not AsyncMock returning coroutine
        mock_page.is_closed = MagicMock(return_value=False)

        # 1. PlaywrightAsyncError
        mock_page.close.side_effect = PlaywrightAsyncError("PW Error")
        state.page_instance = mock_page
        await _close_page_logic()  # Should not raise

        # 2. TimeoutError
        mock_page.close.side_effect = asyncio.TimeoutError("Timeout")
        state.page_instance = mock_page
        await _close_page_logic()  # Should not raise

        # 3. Generic Exception
        mock_page.close.side_effect = Exception("Generic")
        state.page_instance = mock_page
        await _close_page_logic()  # Should not raise

        # 4. CancelledError
        mock_page.close.side_effect = asyncio.CancelledError()
        state.page_instance = mock_page
        with pytest.raises(asyncio.CancelledError):
            await _close_page_logic()
    finally:
        state.page_instance = original_page


# 7. Signal Camoufox Shutdown


@pytest.mark.asyncio
async def test_signal_camoufox_shutdown_no_env():
    with patch.dict("os.environ", {}, clear=True):
        await signal_camoufox_shutdown()
        # Should just return


@pytest.mark.asyncio
async def test_signal_camoufox_shutdown_no_browser(mock_server_state):
    with (
        patch.dict("os.environ", {"CAMOUFOX_WS_ENDPOINT": "ws://test"}),
    ):
        mock_server_state.browser_instance = None
        await signal_camoufox_shutdown()
        # Should just return


@pytest.mark.asyncio
async def test_signal_camoufox_shutdown_success(mock_server_state):
    with (
        patch.dict("os.environ", {"CAMOUFOX_WS_ENDPOINT": "ws://test"}),
        patch("asyncio.sleep", side_effect=AsyncMock()),
    ):
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_server_state.browser_instance = mock_browser

        await signal_camoufox_shutdown()


@pytest.mark.asyncio
async def test_signal_camoufox_shutdown_exception(mock_server_state):
    with (
        patch.dict("os.environ", {"CAMOUFOX_WS_ENDPOINT": "ws://test"}),
        patch("asyncio.sleep", side_effect=Exception("Sleep Fail")),
    ):
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_server_state.browser_instance = mock_browser

        # Should catch exception and log error
        await signal_camoufox_shutdown()


# 8. Enable Temporary Chat Mode


def _make_temp_chat_locator(classes: str = "", count: int = 1):
    locator = MagicMock()
    locator.count = AsyncMock(return_value=count)
    locator.wait_for = AsyncMock()
    locator.click = AsyncMock()
    locator.is_visible = AsyncMock(return_value=True)
    locator.get_attribute = AsyncMock(
        side_effect=lambda name: classes if name == "class" else None
    )
    return locator


def _configure_temp_chat_page(mock_page, temp_locator):
    empty_locator = _make_temp_chat_locator(count=0)
    menu_locator = _make_temp_chat_locator(count=0)

    def locator_factory(selector):
        selector_text = str(selector)
        if "ms-incognito-mode-indicator" in selector_text:
            return empty_locator
        if "data-test-incognito-checkmark" in selector_text:
            return empty_locator
        if "data-test-incognito-toggle" in selector_text:
            return temp_locator
        if "View more actions" in selector_text:
            return menu_locator
        return empty_locator

    mock_page.locator = MagicMock(side_effect=locator_factory)
    return menu_locator


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_already_active(mock_page):
    locator = _make_temp_chat_locator(classes="ms-button-active")
    _configure_temp_chat_page(mock_page, locator)

    with patch.dict(os.environ, {"ENABLE_TEMPORARY_CHAT": "true"}):
        await enable_temporary_chat_mode(mock_page)

    locator.click.assert_not_called()


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_activate_success(mock_page):
    locator = _make_temp_chat_locator()
    # First inactive, then active
    locator.get_attribute = AsyncMock(
        side_effect=lambda name: "" if locator.click.await_count == 0 else "ms-button-active"
    )
    _configure_temp_chat_page(mock_page, locator)

    with patch.dict(os.environ, {"ENABLE_TEMPORARY_CHAT": "true"}):
        await enable_temporary_chat_mode(mock_page)

    locator.click.assert_called()


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_activate_fail(mock_page):
    locator = _make_temp_chat_locator()
    # Always inactive
    locator.get_attribute = AsyncMock(return_value="")
    _configure_temp_chat_page(mock_page, locator)

    with patch.dict(os.environ, {"ENABLE_TEMPORARY_CHAT": "true"}):
        await enable_temporary_chat_mode(mock_page)

    locator.click.assert_called()


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_exception(mock_page):
    locator = _make_temp_chat_locator()
    locator.wait_for.side_effect = Exception("Locator Fail")
    _configure_temp_chat_page(mock_page, locator)

    # Should catch exception and log warning
    with patch.dict(os.environ, {"ENABLE_TEMPORARY_CHAT": "true"}):
        await enable_temporary_chat_mode(mock_page)


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_cancelled(mock_page):
    mock_page.locator.side_effect = asyncio.CancelledError()

    with patch.dict(os.environ, {"ENABLE_TEMPORARY_CHAT": "true"}), pytest.raises(
        asyncio.CancelledError
    ):
        await enable_temporary_chat_mode(mock_page)
