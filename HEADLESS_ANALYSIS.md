# 🔍 Headless 模式深度分析报告

## 当前状态

### ✅ 已确认正常的部分
1. `geoip=True` - 已生效
2. `navigator.webdriver = false` - 反检测脚本工作
3. Cookie/认证 - 正常（DEBUG 模式能用）
4. 网络/代理 - 正常

### ❌ 仍然失败
- Headless 模式：403 permission denied
- DEBUG 模式：完全正常

## 🎯 核心差异分析

### DEBUG vs Headless 的关键区别

| 检测点 | DEBUG 模式 | Headless 模式 | 状态 |
|--------|-----------|---------------|------|
| navigator.webdriver | false | false | ✅ 已修复 |
| GeoIP 匹配 | - | 已启用 | ✅ 已修复 |
| 浏览器窗口 | 有 | 无 | ⚠️ 可能被检测 |
| WebGL | 完整 | 受限 | ⚠️ 可能被检测 |
| Chrome DevTools | 不可见 | 可检测 | ⚠️ 可能被检测 |
| **chrome.runtime** | 存在 | 可能缺失 | 🔥 **高度怀疑** |
| Permissions API | 正常 | 异常 | ⚠️ 可能被检测 |

## 🔬 最可能的检测点

### 1. chrome.runtime API（最可疑）

Headless Chrome 缺少 `chrome.runtime` 对象，这是一个明显的指纹。

**检测方法：**
```javascript
if (!window.chrome || !window.chrome.runtime) {
    // 这是 headless 浏览器
    return 403;
}
```

### 2. WebGL 指纹

Headless 模式的 WebGL 渲染器可能暴露：
```javascript
const gl = canvas.getContext('webgl');
const renderer = gl.getParameter(gl.RENDERER);
// Headless: "SwiftShader" 或 "llvmpipe"
// Normal: 真实 GPU 名称
```

### 3. Permissions API

```javascript
navigator.permissions.query({name: 'notifications'})
// Headless: 立即返回 'denied'
// Normal: 返回 'prompt' 或 'granted'
```

## 💡 解决方案

### 方案1: 增强反检测脚本（推荐尝试）

在 `browser_utils/initialization/scripts.py` 的 `ANTI_AUTOMATION_SCRIPT` 中添加：

```javascript
// ── 4. chrome.runtime (Headless detection) ──────────────────────────
try {
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: function() {},
            sendMessage: function() {},
            onMessage: {
                addListener: function() {},
                removeListener: function() {}
            }
        };
    }
} catch (_) {}

// ── 5. Permissions API normalization ────────────────────────────────
try {
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = function(parameters) {
        return originalQuery.call(this, parameters).then(result => {
            // If headless returns 'denied' instantly, fake it as 'prompt'
            if (result.state === 'denied' && parameters.name === 'notifications') {
                return {
                    state: 'prompt',
                    onchange: null
                };
            }
            return result;
        });
    };
} catch (_) {}
```

### 方案2: 使用虚拟显示（Linux）

```bash
# 在 Linux 上使用 Xvfb
poetry run python launch_camoufox.py --virtual-display
```

### 方案3: 临时使用 DEBUG 模式

如果 headless 无法绕过，暂时使用 DEBUG 模式：

```env
# .env
LAUNCH_MODE=normal
```

可以通过以下方式隐藏窗口：
- Windows: 最小化窗口
- Linux: 使用虚拟桌面
- macOS: 移到其他 Space

### 方案4: 禁用代理测试

临时禁用代理，看是否是代理+headless的组合被检测：

```env
# .env
# UNIFIED_PROXY_CONFIG=http://127.0.0.1:7897
```

## 🔍 调试步骤

### 1. 检查浏览器指纹

在 DEBUG 模式下访问：https://bot.sannysoft.com/

对比 headless 和 DEBUG 模式的差异，看哪些指纹暴露。

### 2. 检查 chrome.runtime

在浏览器控制台运行：
```javascript
console.log('chrome:', window.chrome);
console.log('chrome.runtime:', window.chrome?.runtime);
```

### 3. 检查 Permissions API

```javascript
navigator.permissions.query({name: 'notifications'}).then(r => 
    console.log('Notifications permission:', r.state)
);
```

## 📊 下一步建议

按优先级：

1. **立即尝试：禁用代理测试**
   ```env
   # UNIFIED_PROXY_CONFIG=
   ```
   重启后测试，看是否是代理被检测

2. **增强反检测脚本**
   添加 chrome.runtime mock

3. **使用 normal 模式**
   虽然有窗口，但最稳定

4. **等待 Camoufox 更新**
   或考虑其他反检测浏览器

## 💬 需要你确认

1. 你的代理 `http://127.0.0.1:7897` 是什么类型？
   - Clash？
   - V2Ray？
   - 其他？

2. 能否临时禁用代理测试一次？

3. 是否可以接受使用 DEBUG 模式（有窗口但稳定）？

---

**当前最怀疑：headless Chrome 的 chrome.runtime 缺失被 Google 检测到。**
