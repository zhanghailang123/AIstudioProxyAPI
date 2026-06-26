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
REUSE_EXISTING_AISTUDIO_PAGE_STRICT=true
REUSE_EXISTING_AISTUDIO_WAIT_SECONDS=45
```

使用方式：

1. 以 debug/normal 模式启动 Camoufox。
2. 在该浏览器里手动打开 `https://aistudio.google.com/prompts/new_chat`，确认当前账号能手动发送成功。
3. 重启服务端，让初始化日志出现 `[BrowserReuse] Reusing existing AI Studio page...`。
4. 再发 API 请求。

建议连接外部/已手动打开的浏览器时开启 strict 模式。strict 模式下，如果没有找到已打开的 AI Studio prompt 页面，服务端会等待 `REUSE_EXISTING_AISTUDIO_WAIT_SECONDS` 秒，仍找不到就启动失败，不再静默退回新建 `storage_state` 上下文。由项目 `launch_camoufox.py` 新建的空浏览器会自动跳过 strict 启动拦截，避免服务刚启动就因没有手动页面而退出。

如果复用页面后请求成功，说明原先失败主要来自新建 `storage_state` 隔离上下文、认证文件状态或自动化上下文差异；应刷新/重存 auth profile，或继续保持调试复用模式验证。若复用页面后仍返回 `The caller does not have permission`，再重点排查代理出口、模型权限、账号地域/产品权限和自动化指纹。

### 长 prompt 输入很慢

如果日志里出现很长的 `prompt_chars`，但迟迟没有 `Attempting combo submission`，通常是提示词仍卡在输入阶段。当前可用：

```env
LONG_PROMPT_BULK_INPUT_THRESHOLD=2000
```

超过该字符数会使用批量写入，并在日志中输出：

- `[Input] Using bulk input for long prompt...`
- `[Input] Prompt input completed in ...s`

短 prompt 仍保留逐字键入，减少 UI 兼容和自动化特征风险。

### 恢复后输入框 `click` 超时

如果日志集中出现下面这类报错：

- `Locator.click: Timeout 5000ms exceeded`
- `locator resolved to <textarea ... aria-label="Enter a prompt"...>`
- 随后紧跟 `页面恢复：请求处理失败，跳转到新聊天页...`

通常不是“新开了一个浏览器导致失败”，而是同一个已连接页面在恢复到 `new_chat` 后，输入框虽然已经可见，但还没完全进入可交互状态，或被 tooltip / overlay / 右侧面板瞬时遮挡。

当前修复点：

1. 输入框聚焦改为 `focus` 优先，`click` 只作为降级兜底。
2. `goto(new_chat)` 恢复后，除了等待输入框可见，还会继续等待它进入“可交互”状态。
3. 恢复完成前会先尝试发送一次 `Escape`，清理残留 tooltip / overlay。

因此如果你仍观察到“窗口像闪了一下”，更可能是页面导航重绘，而不是重新创建 browser / context / page。

### 本地出现两个浏览器窗口

如果任务栏里同时看到：

1. 一个已打开的 `Google AI Studio` 页面
2. 一个空白的 `Camoufox` 窗口

通常是启动器先拉起了浏览器默认空白页，随后服务端又在新的 context/page 里打开了 AI Studio。真正处理请求的是 AI Studio 页，空白 `Camoufox` 窗口只是启动残留。

当前修复会在成功拿到 AI Studio 页面后，主动回收其它 context 里的 `about:blank` / `data:,` 空白页，减少双窗口现象，同时避免这类空白页继续干扰“复用已有 AI Studio 页面”的判断。

### 调用方拿到的是分析稿，不是最终答案

如果业务 prompt 要求模型按：

```text
<analysis>...</analysis>
<answer>...</answer>
```

输出，而调用方却拿到了整段 `<analysis>`，通常不是输入问题，而是响应解析没有把结构化标签拆开。当前 DOM 返回路径已兼容：

- `[THINKING]...[/THINKING]`
- `<analysis>...</analysis>`
- `<answer>...</answer>`
- `<final>...</final>`

当 `INCLUDE_REASONING_IN_OPENAI_OUTPUT=false` 时，会优先把 `<answer>` / `<final>` 作为 `content` 返回，把 `<analysis>` 归入 `reasoning_content`，避免调用方把分析稿误当成最终答案。

### 外部调用方报 `0xEF is an invalid start of a value`

如果服务端日志已经显示：

- `Successfully retrieved content directly (...)`
- `Token usage stats: ...`

但外部调用方仍报类似：

- `JsonReaderException`
- `'0xEF' is an invalid start of a value`
- “非流式降级也失败”

优先怀疑的是“对外返回格式不兼容”，而不是 AI Studio 没拿到内容。

这个项目里，旧逻辑会在非流式响应体较大时，把本应一次性返回的 JSON 包成 `StreamingResponse(application/json)` 分块输出。部分外部 SDK，尤其带“流式失败后自动降级非流式”逻辑的客户端，对这种 chunked JSON 兼容较差，可能把返回体当成异常编码或非标准 JSON。

当前修复后：

1. `stream=false` 的请求始终返回标准 `JSONResponse`
2. 只有真正的流式请求才返回 `text/event-stream`

如果外部仍报同类错误，再继续检查调用方是否对响应字节流做了额外 BOM 处理、重复解码，或把 SSE 降级结果继续按普通 JSON 二次解析。

### 长 prompt 输入很慢、结果提取偶发失败

如果日志里出现：

- `[Input] Using bulk input for long prompt...`
- `Bulk input verification mismatch`
- `Edit button click intercepted`
- `(Helper DOM) Successfully extracted DOM content`

说明长 prompt 已切换到分段批量注入，结果提取也已增加 DOM 兜底。

当前策略是：

1. 长 prompt 先走批量注入
2. 校验不一致时自动重试分段注入
3. `Edit`/`Copy` 都失败时，直接从最后一条模型消息 DOM 提取正文

这样可以避免“输入成功但取不回内容”时一直卡住。

补充说明：

- DOM 兜底现在会主动排除 `Thoughts` / `ms-thought-chunk` 区域
- 优先提取最后一条模型消息中的正文 `text-chunk`

这样可以避免把思考稿和最终正文混在一起返回给调用方。

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
