import logging
import asyncio

from playwright.async_api import Page as AsyncPage

logger = logging.getLogger("AIStudioProxyServer")

_STATIC_ASSET_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".css", ".woff", ".woff2")
_AI_STUDIO_RESPONSE_MARKERS = (
    "generatecontent",
    "streamgeneratecontent",
    "batchexecute",
)
_AI_STUDIO_ERROR_MARKERS = (
    "failed to generate content",
    "permission denied",
    "caller does not have permission",
    "forbidden",
    "resource_exhausted",
    "resource has been exhausted",
    "quota",
    "rate limit",
    "too many requests",
    "internal error",
    "an internal error has occurred",
)
_BODY_PREVIEW_LIMIT = 1000


def _is_static_asset(url_lower: str) -> bool:
    """识别静态资源，降低调试日志噪声。"""
    return any(ext in url_lower for ext in _STATIC_ASSET_EXTENSIONS)


def _is_ai_studio_generation_response(url_lower: str) -> bool:
    """识别 AI Studio 生成/RPC 响应。"""
    if "jserror" in url_lower:
        return False
    if not any(marker in url_lower for marker in _AI_STUDIO_RESPONSE_MARKERS):
        return False
    return (
        "aistudio.google.com" in url_lower
        or "makersuite" in url_lower
        or "alkalimakersuite" in url_lower
    )


def _extract_error_preview(body: str) -> tuple[str, list[str]]:
    """提取错误关键词附近的响应片段，避免整段响应入日志。"""
    lower = (body or "").lower()
    matches = [
        (lower.index(marker), marker)
        for marker in _AI_STUDIO_ERROR_MARKERS
        if marker in lower
    ]
    if not matches:
        return "", []
    first_pos = min(pos for pos, _ in matches)
    start = max(0, first_pos - 260)
    end = min(len(body), first_pos + _BODY_PREVIEW_LIMIT)
    preview = body[start:end].replace("\r", " ").replace("\n", " ").strip()
    markers = [marker for _, marker in sorted(matches)[:5]]
    return preview, markers


def setup_debug_listeners(page: AsyncPage) -> None:
    """
    Setup console and network logging listeners for comprehensive error snapshots.

    This function attaches event listeners to capture:
    - Browser console messages (log, warning, error, etc.)
    - Network requests and responses

    Args:
        page: Playwright page instance to attach listeners to
    """
    from datetime import datetime, timezone

    from api_utils.server_state import state

    def handle_console(msg):
        """Handle console messages from the browser."""
        try:
            # Extract location info if available
            location_str = ""
            if msg.location:
                url = msg.location.get("url", "")
                line = msg.location.get("lineNumber", 0)
                if url or line:
                    location_str = f"{url}:{line}"

            state.console_logs.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": msg.type,
                    "text": msg.text,
                    "location": location_str,
                }
            )

            # Log errors to our logger as well
            if msg.type == "error":
                # Filter out known benign browser warnings - log at DEBUG level
                text_lower = msg.text.lower()
                if "cookie" in text_lower and "rejected" in text_lower:
                    # Known Google cookie warning (SIDCC, etc.) - benign but may indicate stale auth profile
                    # Log at DEBUG to reduce noise but preserve for troubleshooting
                    logger.debug(
                        f"[Browser Cookie Warning] {msg.text} - This may indicate the auth profile needs refresh"
                    )
                    return
                logger.warning(f"[Browser Console Error] {msg.text}")

        except Exception as e:
            logger.error(f"Failed to capture console message: {e}")

    def handle_request(request):
        """Handle network requests."""
        try:
            # Only log relevant requests (skip static assets, images, etc.)
            url_lower = request.url.lower()
            if _is_static_asset(url_lower):
                return  # Skip static assets

            state.network_log["requests"].append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                }
            )
        except Exception as e:
            logger.error(f"Failed to capture network request: {e}")

    async def capture_ai_studio_error_body(response, response_entry):
        """异步读取 AI Studio 错误响应体。"""
        try:
            body = await response.text()
        except Exception as body_err:
            response_entry["body_read_error"] = str(body_err)[:300]
            logger.debug(
                f"[NetworkDiag] Failed to read AI Studio response body: {body_err}"
            )
            return

        preview, markers = _extract_error_preview(body)
        if not preview and response.status < 400:
            return

        if not preview:
            preview = body[:_BODY_PREVIEW_LIMIT].replace("\r", " ").replace("\n", " ")

        response_entry["body_preview"] = preview[:_BODY_PREVIEW_LIMIT]
        if markers:
            response_entry["error_markers"] = markers

        marker_text = ",".join(markers) if markers else "status_error"
        logger.warning(
            "[NetworkDiag] AI Studio response issue "
            f"status={response.status} markers={marker_text} "
            f"url={response.url} body={response_entry['body_preview']}"
        )

    def handle_response(response):
        """Handle network responses."""
        try:
            # Only log relevant responses
            url_lower = response.url.lower()
            if _is_static_asset(url_lower):
                return  # Skip static assets

            response_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": response.url,
                "status": response.status,
                "status_text": response.status_text,
            }
            state.network_log["responses"].append(response_entry)

            if _is_ai_studio_generation_response(url_lower):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        capture_ai_studio_error_body(response, response_entry)
                    )
                except RuntimeError:
                    logger.debug(
                        "[NetworkDiag] No running loop, skipping response body capture"
                    )
        except Exception as e:
            logger.error(f"Failed to capture network response: {e}")

    # Attach listeners
    page.on("console", handle_console)
    page.on("request", handle_request)
    page.on("response", handle_response)

    logger.debug("Debug listeners (console + network) attached to page")
