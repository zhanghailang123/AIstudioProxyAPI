# 排障指南

## 1. 启动阶段失败

### 现象 A：浏览器相关初始化失败

优先检查：

1. `CAMOUFOX_WS_ENDPOINT` 是否被 launcher 正确注入（或你是否手动提供了有效地址）
2. 网络与代理配置（`UNIFIED_PROXY_CONFIG`）
3. 是否已有可用认证文件（`auth_profiles/active/*.json`）

### 现象 B：`/health` 一直是 503

查看响应中的 `details`：

- `is_playwright_ready`
- `is_browser_connected`
- `is_page_ready`
- `workerRunning`

如果 `launchMode=direct_debug_no_browser`，browser/page 不是硬依赖。

---

## 2. 聊天接口超时或挂起

### 排查步骤

1. 检查请求是否持续积压：`GET /v1/queue`
2. 查看日志中的 timeout/silence 关键字
3. 调整超时参数：
   - `RESPONSE_COMPLETION_TIMEOUT`
   - `SILENCE_TIMEOUT_MS`
   - `WAIT_FOR_ELEMENT_TIMEOUT_MS`
4. 在 debug 模式观察 AI Studio 页面是否卡住

---

## 3. Function Calling 异常

建议顺序：

1. `FUNCTION_CALLING_MODE=auto`
2. 开启 `FUNCTION_CALLING_DEBUG=true`
3. 仅打开必要 `FC_DEBUG_*` 模块（先 `ORCHESTRATOR/UI/WIRE`）
4. 观察 `logs/fc_debug/` 具体报错

如是 UI 结构变化导致，可核查 `config/selectors.py` 相关选择器。

---

## 4. 认证轮转不生效 / 频繁触发

检查：

- `AUTO_ROTATE_AUTH_PROFILE`
- `AUTO_AUTH_ROTATION_ON_STARTUP`
- `QUOTA_SOFT_LIMIT` / `QUOTA_HARD_LIMIT`
- `saved/` 或 `emergency/` 是否有可用 profile

如果“轮转后仍很快触发”，优先确认账号是否都已接近配额。

---

## 5. 自动化请求报 `permission denied`

### 现象

手动在 AI Studio 页面发送正常，但自动化提交后日志出现：

- `Failed to generate content: permission denied`
- `AI Studio page error`
- `[NetworkDiag] AI Studio response issue status=403`
- `[,[7,"The caller does not have permission"]]`
- 旧日志中可能继续显示 `Quota Exceeded` 或触发认证轮转

### 判断

`permission denied` 是 AI Studio 拒绝当前自动化请求，不等同于账号额度耗尽。它不应该设置 `GlobalState.IS_QUOTA_EXCEEDED`，也不应该触发认证轮转。

如果 `NetworkDiag` 捕获到 `MakerSuiteService/GenerateContent` 返回 `403` 且 body 包含 `The caller does not have permission`，说明页面输入、提交快捷键和响应等待都已经走通，失败点是 Google 服务端拒绝当前浏览器会话/RPC 请求。此时优先排查自动化新建上下文和手动可用上下文是否一致。

### 优先检查

1. 思考模型请求时确认 Google Search 已关闭。建议设置 `ENABLE_GOOGLE_SEARCH=false`，或不要在 `tools` 中传 `googleSearch`。
2. 优先使用 `STREAM_PORT=0`，让浏览器请求不经过本地 MITM 流代理；此时浏览器会直接使用 `UNIFIED_PROXY_CONFIG` / `HTTPS_PROXY` / `HTTP_PROXY`。
3. 确认日志中没有把 `permission denied` 继续归类为 `QuotaExceededError`。
4. 提交动作优先使用 AI Studio 页面提示的 `Ctrl+Enter` / `Meta+Enter` 快捷键，按钮点击仅作为兜底。
5. 如果页面只出现 `An internal error has occurred.` 且没有生成模型回复节点，应按上游页面错误处理，不要等待 `ms-cmark-node` 到 90 秒后包装成普通 500。

### 复用手动页面诊断

当“同一个浏览器里手动发送成功，但服务端自动化请求 403”时，可启用：

```env
REUSE_EXISTING_AISTUDIO_PAGE=true
```

使用方式：

1. 以 debug/normal 模式启动 Camoufox。
2. 在该浏览器里手动打开 `https://aistudio.google.com/prompts/new_chat`，确认当前账号能手动发送成功。
3. 重启服务端，让初始化日志出现 `[BrowserReuse] Reusing existing AI Studio page...`。
4. 再发 API 请求。

如果复用页面后请求成功，说明原先失败主要来自新建 `storage_state` 隔离上下文、认证文件状态或自动化上下文差异；应刷新/重存 auth profile，或继续保持调试复用模式验证。若复用页面后仍返回 `The caller does not have permission`，再重点排查代理出口、模型权限、账号地域/产品权限和自动化指纹。

---

## 6. Docker 常见问题

### 认证文件问题

容器无头运行时不能完成交互登录。必须先在宿主机生成认证文件，再挂载 `auth_profiles/`。

### 健康检查失败

```bash
docker compose logs -f
docker compose exec ai-studio-proxy /bin/bash
curl -v http://127.0.0.1:2048/health
```

### 日志/权限问题

如果你挂载了 `../logs:/app/logs`，需保证目录可写。
