# 🎯 自动化检测问题 - 最终解决方案

## 问题诊断结果

✅ **手动操作：成功** - 在 DEBUG 模式下手动输入完全正常  
❌ **自动化操作：失败** - Google 检测到自动化特征并返回 403

**结论：问题不在账号、网络或代理，而在自动化行为的特征！**

---

## 🔧 已实施的优化

### 1. 强制键盘逐字输入（最关键）

```env
LONG_PROMPT_BULK_INPUT_THRESHOLD=999999
```

**原因：** 批量粘贴（`insertFromPaste` 事件）会被 Google 检测为非人类行为。

### 2. 增加操作延迟

```env
POST_SPINNER_CHECK_DELAY_MS=1000      # 500 → 1000
POST_COMPLETION_BUFFER=1500           # 700 → 1500
FINAL_STATE_CHECK_TIMEOUT_MS=2000     # 1500 → 2000
CLICK_TIMEOUT_MS=5000                 # 3000 → 5000
SILENCE_TIMEOUT_MS=150000             # 60000 → 150000
```

**原因：** 操作过快、节奏过于规律会暴露自动化特征。

### 3. 其他优化

```env
ENABLE_THINKING_BUDGET=true           # 按需启用
ENABLE_GOOGLE_SEARCH=false            # 避免冲突
AUTO_SAVE_AUTH=true                   # 保持认证新鲜
LAUNCH_MODE=headless                  # 无头模式
```

---

## 🚀 测试步骤

### 第1步：确认配置

```bash
grep -E "LONG_PROMPT_BULK_INPUT_THRESHOLD|POST_SPINNER|CLICK_TIMEOUT" .env
```

应该看到：
```
LONG_PROMPT_BULK_INPUT_THRESHOLD=999999
POST_SPINNER_CHECK_DELAY_MS=1000
CLICK_TIMEOUT_MS=5000
```

### 第2步：重启服务

```bash
# 停止当前服务（如果在运行）
# Ctrl+C

# 使用 headless 模式启动
poetry run python launch_camoufox.py --headless

# 等待启动完成（看到 "Server startup complete"）
```

### 第3步：测试短消息（会使用键盘输入）

```powershell
$json = '{"model":"gemini-3.5-flash","messages":[{"role":"user","content":"hi"}],"stream":false}'

Invoke-RestMethod -Uri "http://127.0.0.1:2048/v1/chat/completions" `
  -Method Post `
  -ContentType "application/json" `
  -Body $json
```

**期望结果：** 成功返回响应，日志显示 `Using keyboard.type for short prompt`

### 第4步：查看日志

```bash
tail -50 logs/app.log
```

**检查点：**
- ✅ 应该看到：`[Input] Using keyboard.type for short prompt`
- ✅ 应该看到：`Combo submission successful`
- ✅ 应该看到：`Successfully retrieved content`
- ❌ **不应该看到：** `permission denied` 或 `403`

---

## 🔍 如果仍然失败

### 方案A：尝试不同模型

```powershell
# 测试非 Thinking 模型
$json = '{"model":"gemini-2.5-flash","messages":[{"role":"user","content":"hi"}]}'
Invoke-RestMethod -Uri "http://127.0.0.1:2048/v1/chat/completions" -Method Post -ContentType "application/json" -Body $json
```

### 方案B：禁用代理测试

```env
# 编辑 .env，临时注释掉代理
# UNIFIED_PROXY_CONFIG=http://127.0.0.1:7897
```

重启后测试。

### 方案C：增加更多延迟

```env
# 继续增加延迟
POST_SPINNER_CHECK_DELAY_MS=2000
POST_COMPLETION_BUFFER=3000
CLICK_TIMEOUT_MS=8000
```

### 方案D：使用 DEBUG 模式观察

```bash
poetry run python launch_camoufox.py --debug
```

在浏览器中观察自动化操作，对比和手动操作的差异。

---

## 🎓 技术原理

### Google 的自动化检测机制

1. **浏览器指纹**
   - `navigator.webdriver` ✅ 已绕过
   - CDP 痕迹 ✅ 已清理
   - 其他指纹（可能有新检测点）

2. **行为特征**（本次问题的核心）
   - ❌ **批量粘贴**：`insertFromPaste` 事件
   - ❌ **操作节奏**：延迟过短且规律
   - ❌ **输入速度**：15-45ms 太快
   - ✅ **键盘输入**：模拟真实按键

3. **网络特征**
   - TLS 指纹
   - HTTP/2 指纹
   - 请求时序

### 我们的对策

| 检测点 | 原方案 | 优化方案 |
|--------|--------|----------|
| 输入方式 | 批量粘贴 | 键盘逐字输入 |
| 输入延迟 | 15-45ms | 15-45ms（保持随机） |
| 操作延迟 | 500-700ms | 1000-1500ms |
| 点击超时 | 3000ms | 5000ms |

---

## 📊 预期效果

**优化前：**
```
[Input] Using bulk input for long prompt: 12 chars
[NetworkDiag] AI Studio response issue status=403
[ERR] AI Studio permission denied
```

**优化后：**
```
[Input] Using keyboard.type for short prompt: 12 chars
[Input] Prompt input completed in 0.5s
[Info] Combo submission successful
[Info] Successfully retrieved content
```

---

## 📝 长期建议

1. **定期更新认证**
   - 每天重新登录一次
   - 使用 `AUTO_SAVE_AUTH=true`

2. **监控成功率**
   - 如果成功率下降，可能需要调整参数
   - 关注 Google 的更新

3. **准备多个账号**
   - 设置认证轮转
   - 分散请求压力

4. **保持代理稳定**
   - 使用固定的出口 IP
   - 避免频繁切换

---

## 🎯 核心要点

💡 **关键发现：** 手动成功 + 自动化失败 = 行为特征被检测  
🔧 **核心修复：** 强制键盘输入 + 增加延迟  
⏱️ **测试重点：** 短消息能否通过（使用键盘输入）  

---

**祝测试成功！如果有任何问题，请查看日志并反馈。**
