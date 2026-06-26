# 403 Permission Denied 问题解决方案

## 📊 问题诊断

### 症状
- 日志显示: `[NetworkDiag] AI Studio response issue status=403`
- 错误信息: `The caller does not have permission`
- AI Studio 页面显示: `Failed to generate content: permission denied`
- 昨天还能用，今天突然不行

### 根本原因
**Thinking 模式 + Google Search 冲突**导致 Google 服务端拒绝请求。

当 `ENABLE_THINKING_BUDGET=true` 且模型支持 Thinking 时：
1. 代码会自动设置 Thinking Level 为 high
2. 代码尝试强制关闭 Google Search（避免 403）
3. **但如果 Google Search toggle 未成功关闭，就会触发 403**

### 次要原因
1. **UI 元素变化**: Temperature 和 Top-P 控件找不到
   ```
   09:51:53.643 ERR Error operating temperature input: element(s) not found
   09:52:00.018 ERR Error adjusting Top P: element(s) not found
   ```
   说明 AI Studio 的 UI 可能有更新

2. **反自动化检测加强**: Google 可能调整了检测策略

## ✅ 已实施的解决方案

### 1. 核心配置调整

```env
# 禁用 Thinking Budget（最关键）
ENABLE_THINKING_BUDGET=false

# 确保 Google Search 默认关闭
ENABLE_GOOGLE_SEARCH=false

# 禁用流式代理（避免 TLS 指纹检测）
STREAM_PORT=0

# 增加静默超时
SILENCE_TIMEOUT_MS=150000

# 启用自动保存认证
AUTO_SAVE_AUTH=true

# 设置为 headless 模式
LAUNCH_MODE=headless
```

### 2. 页面复用配置（已有）

```env
# 优先复用已打开的 AI Studio 页面
REUSE_EXISTING_AISTUDIO_PAGE=true
REUSE_EXISTING_AISTUDIO_PAGE_STRICT=true
REUSE_EXISTING_AISTUDIO_WAIT_SECONDS=45
```

## 🚀 重启步骤

### 方案 A: 快速重启（推荐先试）

```bash
# 停止当前服务
# Ctrl+C 或停止进程

# 清理旧的 Cookie（可选）
# rm auth_profiles/active/0626.json

# 重新启动
poetry run python launch_camoufox.py --headless
```

### 方案 B: 重新认证（如果方案 A 无效）

```bash
# 1. 使用 debug 模式重新登录
poetry run python launch_camoufox.py --debug

# 2. 在浏览器中手动登录 Google 账号
# 3. 等待保存认证文件
# 4. Ctrl+C 停止

# 5. 切换回 headless 模式
poetry run python launch_camoufox.py --headless
```

### 方案 C: 完全清理重启（终极方案）

```bash
# 1. 备份当前认证
cp auth_profiles/active/0626.json auth_profiles/saved/backup_$(date +%Y%m%d_%H%M%S).json

# 2. 清理所有缓存
rm -rf .pytest_cache errors_py/*.png errors_py/*.html logs/*.log

# 3. 删除旧认证
rm auth_profiles/active/*.json

# 4. 重新认证
poetry run python launch_camoufox.py --debug

# 5. 登录并测试
# 6. 确认可用后切换 headless
```

## 🔍 验证步骤

### 1. 检查服务健康

```bash
curl http://127.0.0.1:2048/health
```

期望输出包含:
```json
{
  "status": "ok",
  "is_page_ready": true,
  "current_model": "gemini-3.5-flash"
}
```

### 2. 测试聊天接口

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.5-flash",
    "messages": [{"role": "user", "content": "你好，请回复OK"}],
    "stream": false
  }'
```

### 3. 查看实时日志

```bash
tail -f logs/app.log
```

期望看到:
- ✅ `Combo submission successful`
- ✅ `Successfully retrieved content`
- ❌ 不应该出现 `permission denied`
- ❌ 不应该出现 `status=403`

## 🛡️ 预防措施

### 1. 监控关键指标

- 定期检查 `errors_py/` 目录的错误快照
- 关注日志中的 `[NetworkDiag]` 警告
- 监控参数设置是否失败（Temperature, Top-P）

### 2. 认证轮转配置

```env
# 启用自动轮转
AUTO_ROTATE_AUTH_PROFILE=true

# 配置多个认证 profile
# auth_profiles/active/profile1.json
# auth_profiles/active/profile2.json
```

### 3. 降级策略

如果问题持续，可以临时：
1. 使用更稳定的模型（如 gemini-2.0-flash-exp）
2. 降低请求频率
3. 使用不同的 Google 账号

## 📝 已知限制

### Google Search + Thinking 冲突
当前代码逻辑（`parameters.py:719-720`）:
```python
if not should_enable_search:
    # 思考模型必须关闭搜索，否则 AI Studio 可能直接返回 permission denied。
    raise RuntimeError(msg)
```

解决办法：
- **禁用 Thinking**: `ENABLE_THINKING_BUDGET=false`
- **或在请求中不传 `reasoning_effort` 参数**

### UI 元素变化
AI Studio 的前端会不定期更新，可能导致：
- 参数控件选择器失效
- 提交按钮位置变化
- 响应元素结构调整

解决办法：
- 查看 `config/selectors.py` 更新选择器
- 提 Issue 到 GitHub 仓库

## 🔗 相关资源

- [完整配置文档](docs/configuration-reference.md)
- [排障指南](docs/troubleshooting.md)
- [GitHub Issues](https://github.com/CJackHwang/AIstudioProxyAPI/issues)

## 📅 更新日志

- 2026-06-26: 初次诊断并实施解决方案
  - 禁用 ENABLE_THINKING_BUDGET
  - 增加 SILENCE_TIMEOUT_MS 到 150s
  - 启用 AUTO_SAVE_AUTH
