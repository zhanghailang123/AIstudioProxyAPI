import asyncio
import logging
import time
from typing import Callable

from playwright.async_api import Error as PlaywrightAsyncError
from playwright.async_api import Page as AsyncPage
from playwright.async_api import expect as expect_async

from config import RESPONSE_CONTAINER_SELECTOR, RESPONSE_TEXT_SELECTOR
from models import AIStudioPermissionDeniedError, QuotaExceededError, UpstreamError

_PAGE_ERROR_PATTERNS = (
    "failed to generate content",
    "permission denied",
    "caller does not have permission",
    "please try again",
    "resource_exhausted",
    "resource has been exhausted",
    "rate limit",
    "too many requests",
    "internal error",
    "an internal error has occurred",
)


def _classify_page_error(text: str) -> str:
    """分类页面错误，避免权限拒绝被包装成普通 500。"""
    lower = (text or "").lower()
    if (
        "permission denied" in lower
        or "caller does not have permission" in lower
        or "forbidden" in lower
        or "403" in lower
    ):
        return "permission"
    if (
        "quota" in lower
        or "resource_exhausted" in lower
        or "resource has been exhausted" in lower
        or "rate limit" in lower
        or "too many requests" in lower
        or "429" in lower
    ):
        return "quota"
    return "upstream"


def _is_response_poll_error(error: Exception) -> bool:
    """识别响应节点轮询失败，统一走上游 502。"""
    return isinstance(error, (PlaywrightAsyncError, asyncio.TimeoutError, AssertionError))


async def _extract_ai_studio_page_error(page: AsyncPage) -> str:
    """读取 AI Studio 页面错误提示。"""
    try:
        return await page.evaluate(
            """() => {
                const bodyText = document.body && document.body.innerText || '';
                const lower = bodyText.toLowerCase();
                const patterns = [
                    'failed to generate content',
                    'permission denied',
                    'caller does not have permission',
                    'please try again',
                    'resource_exhausted',
                    'resource has been exhausted',
                    'rate limit',
                    'too many requests',
                    'internal error',
                    'an internal error has occurred',
                ];
                const index = patterns
                    .map((pattern) => lower.indexOf(pattern))
                    .filter((pos) => pos >= 0)
                    .sort((a, b) => a - b)[0];
                if (index !== undefined) {
                    const start = Math.max(0, index - 220);
                    const end = Math.min(bodyText.length, index + 360);
                    return bodyText.substring(start, end);
                }
                return '';
            }"""
        )
    except Exception:
        # 页面瞬时不可读时继续等待响应元素，避免误伤正常流程。
        return ""


def _raise_page_error(req_id: str, text: str) -> None:
    cleaned = str(text)[:500]
    category = _classify_page_error(cleaned)
    if category == "permission":
        raise AIStudioPermissionDeniedError(
            f"AI Studio page error: {cleaned}", req_id=req_id
        )
    if category == "quota":
        raise QuotaExceededError(f"AI Studio page error: {cleaned}", req_id=req_id)
    raise UpstreamError(f"AI Studio page error: {cleaned}", req_id=req_id)


async def locate_response_elements(
    page: AsyncPage,
    req_id: str,
    logger: logging.Logger,
    check_client_disconnected: Callable[[str], bool],
) -> None:
    """Locate response container and text elements, including timeout and error handling."""
    logger.info(f"[{req_id}] Locating response elements...")
    response_container = page.locator(RESPONSE_CONTAINER_SELECTOR).last
    response_element = response_container.locator(RESPONSE_TEXT_SELECTOR)

    try:
        await expect_async(response_container).to_be_attached(timeout=20000)
        check_client_disconnected("After Response Container Attached: ")

        # Playwright DOM 路径没有流代理队列，必须主动轮询页面错误 toast。
        deadline = time.monotonic() + 90.0
        timed_out_error = None
        while True:
            check_client_disconnected("Waiting for Response Element: ")
            page_error = await _extract_ai_studio_page_error(page)
            if page_error:
                logger.warning(
                    f"[{req_id}] AI Studio page error while locating response: "
                    f"{page_error[:200]}"
                )
                _raise_page_error(req_id, page_error)
            try:
                await expect_async(response_element).to_be_attached(timeout=1000)
                timed_out_error = None
                break
            except Exception as poll_err:
                if _is_response_poll_error(poll_err):
                    if time.monotonic() >= deadline:
                        timed_out_error = poll_err
                        break
                else:
                    raise
                await asyncio.sleep(0.5)
        if timed_out_error is not None:
            raise timed_out_error
        logger.info(f"[{req_id}] Response elements located.")
    except (AIStudioPermissionDeniedError, QuotaExceededError, UpstreamError):
        raise
    except (PlaywrightAsyncError, asyncio.TimeoutError, AssertionError) as locate_err:
        from .error_utils import upstream_error

        raise upstream_error(
            req_id, f"Failed to locate AI Studio response elements: {locate_err}"
        )
    except Exception as locate_exc:
        from .error_utils import server_error

        raise server_error(
            req_id, f"Unexpected error while locating response elements: {locate_exc}"
        )
