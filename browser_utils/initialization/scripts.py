# --- browser_utils/initialization/scripts.py ---
import asyncio
import logging
import os

from playwright.async_api import BrowserContext as AsyncBrowserContext

logger = logging.getLogger("AIStudioProxyServer")


async def add_init_scripts_to_context(context: AsyncBrowserContext):
    """Add initialization scripts to browser context (fallback option)"""
    try:
        from config.settings import USERSCRIPT_PATH

        # Check if script file exists
        if not os.path.exists(USERSCRIPT_PATH):
            logger.info(
                f"Script file does not exist, skipping script injection: {USERSCRIPT_PATH}"
            )
            return

        # Read script content
        with open(USERSCRIPT_PATH, "r", encoding="utf-8") as f:
            script_content = f.read()

        # Clean UserScript headers
        cleaned_script = _clean_userscript_headers(script_content)

        # Add to context initialization scripts
        await context.add_init_script(cleaned_script)
        logger.info(
            f"Added script to browser context initialization scripts: {os.path.basename(USERSCRIPT_PATH)}"
        )

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error adding initialization script to context: {e}")


def _clean_userscript_headers(script_content: str) -> str:
    """Clean UserScript header information"""
    lines = script_content.split("\n")
    cleaned_lines = []
    in_userscript_block = False

    for line in lines:
        if line.strip().startswith("// ==UserScript=="):
            in_userscript_block = True
            continue
        elif line.strip().startswith("// ==/UserScript=="):
            in_userscript_block = False
            continue
        elif in_userscript_block:
            continue
        else:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


# ---------------------------------------------------------------------------
# Anti-automation-detection init script
# ---------------------------------------------------------------------------
# Playwright connects to the browser via Chrome DevTools Protocol (CDP).
# Google's AI Studio frontend JavaScript checks for automation fingerprints
# (primarily navigator.webdriver) and rejects GenerateContent requests with
# 403 "permission denied" when automation is detected.
#
# This script patches the detectable properties BEFORE any page scripts run,
# making the automated browser look like a normal manual session.
# ---------------------------------------------------------------------------
ANTI_AUTOMATION_SCRIPT = r"""
(() => {
    // ── 1. navigator.webdriver ──────────────────────────────────────────────
    // Playwright sets navigator.webdriver = true via CDP. This is the
    // primary signal Google checks. We must patch BOTH the instance and
    // the prototype so that Object.getOwnPropertyDescriptor() also
    // returns a normal-browser-like result.
    try {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
            configurable: true,
        });
    } catch (_) {}
    try {
        const proto = Object.getPrototypeOf(navigator);
        if (proto) {
            Object.defineProperty(proto, 'webdriver', {
                get: () => false,
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 2. Chrome DevTools Protocol artifacts ───────────────────────────────
    // Remove any window properties that look like CDP-injected markers.
    try {
        for (const key of Object.getOwnPropertyNames(window)) {
            if (/^cdc_|^__playwright|^__pw_manual/.test(key)) {
                try { delete window[key]; } catch (_) {}
            }
        }
    } catch (_) {}

    // ── 3. Permissions.query ────────────────────────────────────────────────
    // In automated browsers, Permissions.query('notifications') returns
    // 'denied' instantly instead of 'prompt'. Wrap to normalise.
    try {
        const origQuery = Permissions.prototype.query;
        Permissions.prototype.query = function(desc) {
            return origQuery.call(this, desc).then(status => {
                if (desc.name === 'notifications' && status.state === 'denied') {
                    return { state: 'prompt', onchange: null };
                }
                return status;
            });
        };
    } catch (_) {}

    // ── 4. Plugin / MimeType arrays ─────────────────────────────────────────
    // Automated browsers often have empty plugin/mimeType arrays.
    // We cannot fake real plugins, but we prevent the most obvious checks.
    try {
        if (navigator.plugins.length === 0) {
            Object.defineProperty(navigator, 'plugins', {
                get: () => { const a = [1, 2, 3]; a.length = 3; return a; },
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 5. chrome.runtime ───────────────────────────────────────────────────
    // Some CDP implementations leave chrome.runtime in a detectable state.
    try {
        if (window.chrome && window.chrome.runtime) {
            const rt = window.chrome.runtime;
            if (!rt.sendMessage) {
                Object.defineProperty(rt, 'sendMessage', {
                    value: function() {},
                    configurable: true,
                });
            }
        }
    } catch (_) {}
})();
"""


async def add_anti_automation_script(context: AsyncBrowserContext):
    """Inject anti-automation-detection script into every page.

    This patches navigator.webdriver and other CDP fingerprints that
    Google's AI Studio frontend uses to detect automated browsers and
    reject GenerateContent requests with 403 'permission denied'.

    Must be called BEFORE any page navigation so the script runs before
    Google's own JavaScript.
    """
    try:
        await context.add_init_script(ANTI_AUTOMATION_SCRIPT)
        logger.info("[AntiDetect] Anti-automation script injected successfully")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"[AntiDetect] Failed to inject anti-automation script: {e}")
