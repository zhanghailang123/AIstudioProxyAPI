# 🎯 Headless 模式 403 修复

## 问题根源

**发现：DEBUG 模式正常，headless 模式 403**

这说明问题不在账号、网络或参数设置，而在 **headless 模式特有的检测**。

## 关键证据

### 1. 启动日志警告
```
WARNING: When using a proxy, it is heavily recommended that you pass `geoip=True`.
```

### 2. headless 特有的检测点

Google 可以通过以下方式检测 headless 浏览器：

1. **浏览器指纹不一致**
   - Headless Chrome 有特殊的 User-Agent 标记
   - 缺少某些 WebGL/Canvas 特征
   - window.chrome 对象差异

2. **GeoIP 不匹配** ⭐ 最关键
   - 代理 IP 的地理位置：可能是其他国家/地区
   - 浏览器指纹的地理位置：默认本地
   - 不匹配 → Google 判定为可疑请求

3. **行为模式**
   - Headless 模式下某些操作过于精准
   - 缺少人类的随机性

## 已实施的修复

### 修改文件：`launch_camoufox.py:965-973`

```python
# 修改前
launch_args_for_internal_camoufox = {
    "port": camoufox_port_internal,
    "addons": [],
    "exclude_addons": [DefaultAddons.UBO],
    "window": (1440, 900),
}

# 修改后
launch_args_for_internal_camoufox = {
    "port": camoufox_port_internal,
    "addons": [],
    "exclude_addons": [DefaultAddons.UBO],
    "window": (1440, 900),
    "geoip": True,  # 🔥 关键：匹配代理的地理位置
}
```

### 效果

`geoip=True` 会让 Camoufox：
1. 根据代理 IP 自动调整浏览器的地理位置指纹
2. 包括时区、语言、地理位置 API 等
3. 使浏览器指纹与代理 IP 保持一致

## 🚀 测试步骤

### 1. 完全重启（重要！）

```bash
# 1. 停止当前所有进程
# Ctrl+C 停止服务

# 2. 确认 Camoufox 进程已停止
tasklist | findstr camoufox
# 如果有进程，手动 kill

# 3. 重新启动
poetry run python launch_camoufox.py --headless

# 等待启动完成
```

### 2. 观察启动日志

**期望看到：**
```
Args passed to launch_server: {..., 'geoip': True, ...}
```

**不应该看到警告：**
```
❌ WARNING: When using a proxy, it is heavily recommended that you pass `geoip=True`.
```

### 3. 测试请求

```powershell
$json = '{"model":"gemini-2.5-flash","messages":[{"role":"user","content":"hi"}],"stream":false}'

Invoke-RestMethod -Uri "http://127.0.0.1:2048/v1/chat/completions" `
  -Method Post `
  -ContentType "application/json" `
  -Body $json
```

## 📊 预期结果

### 结果A: 成功 ✅
```
[INFO] [Input] Prompt input completed
[INFO] Combo submission successful
[INFO] Successfully retrieved content
```

**说明：** GeoIP 匹配修复了 headless 检测问题

### 结果B: 仍然 403 ❌
**说明：** 还有其他 headless 特有的检测点

**进一步排查：**
1. 检查是否还有其他浏览器指纹泄露
2. 尝试添加更多 Camoufox 反检测选项
3. 考虑使用 DEBUG 模式（非 headless）作为临时方案

## 🔬 技术原理

### 为什么 DEBUG 模式正常？

DEBUG 模式（非 headless）：
- 完整的浏览器环境
- 所有 WebGL/Canvas 特征完整
- 鼠标光标、焦点等人类特征
- Google 更难检测

Headless 模式：
- 缺少某些浏览器特征
- 没有真实的鼠标光标
- 某些 API 行为不同
- Google 容易检测

### GeoIP 的作用

```
没有 geoip=True:
代理 IP: 美国      ❌ 不匹配
浏览器: 中国       ❌ Google 检测到

有 geoip=True:
代理 IP: 美国      ✅ 匹配
浏览器: 美国       ✅ Google 放行
```

## 💡 如果还是失败

### 方案1: 使用 DEBUG 模式（临时方案）

```env
# .env
LAUNCH_MODE=normal  # 或 debug
```

虽然会显示浏览器窗口，但最不容易被检测。

### 方案2: 添加更多反检测选项

```python
launch_args_for_internal_camoufox = {
    ...,
    "geoip": True,
    "humanize": True,  # 如果 Camoufox 支持
    "fonts": True,     # 匹配系统字体
}
```

### 方案3: 更换代理

有些代理 IP 可能已被 Google 标记，尝试：
- 使用本地直连（临时禁用代理）
- 更换代理服务器
- 使用住宅 IP 代理

---

**准备好重启测试了吗？** 🚀
