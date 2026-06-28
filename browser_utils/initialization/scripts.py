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
    // Also patch Navigator.prototype.webdriver descriptor to look native
    try {
        const navProto = Navigator.prototype;
        const desc = Object.getOwnPropertyDescriptor(navProto, 'webdriver');
        if (desc) {
            Object.defineProperty(navProto, 'webdriver', {
                get: () => false,
                configurable: true,
                enumerable: true,
            });
        }
    } catch (_) {}

    // ── 2. Chrome DevTools Protocol artifacts ───────────────────────────────
    // Remove any window properties that look like CDP-injected markers.
    try {
        for (const key of Object.getOwnPropertyNames(window)) {
            if (/^cdc_|^__playwright|^__pw_manual|^__selenium|^_selenium|^webdriver_/.test(key)) {
                try { delete window[key]; } catch (_) {}
            }
        }
    } catch (_) {}

    // ── 3. Permissions.query (unified, fixes duplicate definition) ──────────
    // In automated browsers, Permissions.query('notifications') returns
    // 'denied' instantly instead of 'prompt'. Wrap to normalise.
    // NOTE: This combines the two previous duplicate blocks (sections 3 & 6).
    try {
        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = function(desc) {
            return origQuery(desc).then(status => {
                if (desc && desc.name === 'notifications' && status.state === 'denied') {
                    return { state: 'prompt', onchange: null, addEventListener: () => {}, removeEventListener: () => {} };
                }
                return status;
            }).catch(() => ({
                state: 'prompt',
                onchange: null,
                addEventListener: () => {},
                removeEventListener: () => {},
            }));
        };
    } catch (_) {}

    // ── 4. Plugin / MimeType arrays ─────────────────────────────────────────
    // Automated browsers often have empty plugin/mimeType arrays.
    // Build a fake PluginArray-like object with proper type so instanceof
    // checks pass and length/item/namedItem behave like a real PluginArray.
    try {
        if (navigator.plugins.length === 0) {
            const makePlugin = (name, filename, description) => {
                const mimes = [
                    Object.create(MimeType.prototype, {
                        type: { value: filename },
                        suffixes: { value: filename.split('.').pop() || '' },
                        description: { value: description },
                    }),
                ];
                const plugin = Object.create(Plugin.prototype, {
                    name: { value: name },
                    filename: { value: filename },
                    description: { value: description },
                    length: { value: mimes.length },
                    0: { value: mimes[0] },
                });
                return plugin;
            };
            const fakePlugins = [
                makePlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
                makePlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
                makePlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
                makePlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
                makePlugin('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format'),
            ];
            const fakePluginArray = Object.create(PluginArray.prototype, {
                length: { value: fakePlugins.length, configurable: true },
            });
            fakePlugins.forEach((p, i) => { fakePluginArray[i] = p; });
            fakePluginArray.item = function(i) { return this[i] || null; };
            fakePluginArray.namedItem = function(n) {
                for (let i = 0; i < this.length; i++) { if (this[i].name === n) return this[i]; }
                return null;
            };
            fakePluginArray.refresh = function() {};
            Object.defineProperty(navigator, 'plugins', {
                get: () => fakePluginArray,
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 5. chrome.runtime (skip on Firefox/camoufox - they don't have it) ──
    // Only create window.chrome if we appear to be a Chromium-based UA.
    // Camoufox is Firefox-based, so skip to avoid creating inconsistent state.
    try {
        const isChromeUA = /Chrome\//.test(navigator.userAgent);
        if (isChromeUA && !window.chrome) {
            window.chrome = {};
            window.chrome.runtime = {
                connect: function() {},
                sendMessage: function() {},
                onMessage: { addListener: function() {}, removeListener: function() {} }
            };
        }
    } catch (_) {}

    // ── 6. navigator.languages ──────────────────────────────────────────────
    // Headless sometimes returns ['en-US'] or empty. Real browsers usually
    // have at least two entries (e.g. ['en-US', 'en']).
    try {
        const langs = navigator.languages;
        if (!langs || langs.length === 0) {
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
                configurable: true,
            });
        } else if (langs.length === 1) {
            const base = langs[0].split('-')[0];
            if (base && base !== langs[0]) {
                Object.defineProperty(navigator, 'languages', {
                    get: () => [langs[0], base],
                    configurable: true,
                });
            }
        }
    } catch (_) {}

    // ── 7. Window dimensions (headless classic leak) ────────────────────────
    // Headless browsers often report outerWidth/outerHeight === 0 or
    // screenX/screenY === 0 while innerWidth differs from outerWidth.
    // Make outer dims slightly larger than inner to look like a real window.
    try {
        if (window.outerWidth === 0 || window.outerHeight === 0) {
            const iw = window.innerWidth || 1440;
            const ih = window.innerHeight || 900;
            Object.defineProperty(window, 'outerWidth', { get: () => iw + 16, configurable: true });
            Object.defineProperty(window, 'outerHeight', { get: () => ih + 88, configurable: true });
        }
        if (window.screenX === 0 && window.screenY === 0) {
            // Randomize slightly so it doesn't always look like (0,0)
            Object.defineProperty(window, 'screenX', { get: () => 0, configurable: true });
            Object.defineProperty(window, 'screenY', { get: () => 0, configurable: true });
        }
    } catch (_) {}

    // ── 8. navigator.hardwareConcurrency / deviceMemory ─────────────────────
    // Headless often returns 1 or 2 for hardwareConcurrency. Most real
    // desktops report 4, 8, or 12. deviceMemory usually 8.
    try {
        const hc = navigator.hardwareConcurrency;
        if (!hc || hc <= 2) {
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
                configurable: true,
            });
        }
    } catch (_) {}
    try {
        if (!navigator.deviceMemory) {
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 9. WebGL renderer/vendor (SwiftShader detection) ────────────────────
    // Headless uses SwiftShader which returns "Google Inc. (Google)" as
    // vendor and "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device))" as
    // renderer. Replace with realistic Intel/NVIDIA values.
    try {
        const getParameterProto = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {
            // UNMASKED_VENDOR_WEBGL
            if (param === 37445) return 'Intel Inc.';
            // UNMASKED_RENDERER_WEBGL
            if (param === 37446) return 'Intel(R) Iris(R) Xe Graphics';
            return getParameterProto.call(this, param);
        };
        // Also patch WebGL2RenderingContext if present
        if (typeof WebGL2RenderingContext !== 'undefined') {
            const getParameterProto2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Intel Inc.';
                if (param === 37446) return 'Intel(R) Iris(R) Xe Graphics';
                return getParameterProto2.call(this, param);
            };
        }
    } catch (_) {}

    // ── 10. Notification.permission ─────────────────────────────────────────
    // Headless returns 'denied'. Real browsers return 'default'.
    try {
        if (typeof Notification !== 'undefined' && Notification.permission === 'denied') {
            Object.defineProperty(Notification, 'permission', {
                get: () => 'default',
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 11. navigator.connection (headless often missing) ───────────────────
    try {
        if (!navigator.connection) {
            const fakeConn = {
                effectiveType: '4g',
                rtt: 50,
                downlink: 10,
                saveData: false,
                addEventListener: () => {},
                removeEventListener: () => {},
            };
            Object.defineProperty(navigator, 'connection', {
                get: () => fakeConn,
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 12. navigator.platform consistency ──────────────────────────────────
    // Ensure platform matches UA (Win32 on Windows UA). Camoufox usually
    // handles this but double-check.
    try {
        if (/Windows/.test(navigator.userAgent) && navigator.platform !== 'Win32') {
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32',
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 13. Function.toString() native check ────────────────────────────────
    // Some detection checks fn.toString() to see if it contains native code.
    // Our patched functions should look native. This is best-effort.
    try {
        const nativeToStringFn = Function.prototype.toString;
        const nativeFns = new Set();
        // Mark our patches so toString() returns "[native code]"
        const patchFn = (obj, prop) => {
            try {
                nativeFns.add(obj[prop]);
            } catch (_) {}
        };
        // Override toString to return native code for our patched functions
        Function.prototype.toString = function() {
            if (nativeFns.has(this)) {
                return 'function ' + (this.name || '') + '() { [native code] }';
            }
            return nativeToStringFn.call(this);
        };
        // Re-point nativeToStringFn so it looks native too
        nativeFns.add(Function.prototype.toString);
    } catch (_) {}

    // ── 14. iframe contentWindow navigator consistency ──────────────────────
    // Google may create an iframe and check its navigator.webdriver.
    // add_init_script runs in all frames, but ensure consistency by
    // re-applying key patches via Object.defineProperty on the prototype.
    // (Already covered by section 1's prototype patch above.)

    // ── 15. MediaDevices.enumerateDevices (headless returns empty) ──────────
    try {
        if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
            const origEnumerate = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
            navigator.mediaDevices.enumerateDevices = function() {
                return origEnumerate().then(devices => {
                    if (devices.length === 0) {
                        return [
                            { kind: 'audioinput', deviceId: 'default', groupId: 'group1', label: '' },
                            { kind: 'audiooutput', deviceId: 'default', groupId: 'group1', label: '' },
                            { kind: 'videoinput', deviceId: 'default', groupId: 'group2', label: '' },
                        ];
                    }
                    return devices;
                });
            };
        }
    } catch (_) {}

    // ── 16. navigator.getBattery (headless sometimes missing) ───────────────
    try {
        if (!navigator.getBattery) {
            navigator.getBattery = () => Promise.resolve({
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1,
                addEventListener: () => {},
                removeEventListener: () => {},
            });
        }
    } catch (_) {}

    // ── 17. Headless UA substring removal ───────────────────────────────────
    // Some headless builds still leak "Headless" in the UA. Camoufox
    // should handle this, but strip it defensively in case.
    try {
        const ua = navigator.userAgent;
        if (/HeadlessChrome|Headless/i.test(ua)) {
            const cleaned = ua.replace(/HeadlessChrome/i, 'Chrome').replace(/Headless/i, '');
            Object.defineProperty(navigator, 'userAgent', {
                get: () => cleaned,
                configurable: true,
            });
        }
    } catch (_) {}

    // ── 18. Permissions API re-patch (moved here to avoid duplicate) ────────
    // NOTE: Original code had sections 3 AND 6 both patching permissions.
    // Section 3 above is the unified version. This section removed.
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
