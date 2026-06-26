# 403 Permission Denied - 快速修复方案

## 🎯 核心问题

Google 检测到自动化请求并在服务端拒绝（403），问题不在代码逻辑，而在**认证状态或浏览器指纹**。

## 🚀 立即执行（按优先级）

### 方案 1: 重新认证（推荐）⭐⭐⭐

```bash
# 1. 停止当前服务（Ctrl+C）

# 2. 备份当前认证
cp auth_profiles/active/0626.json auth_profiles/saved/backup_0626_$(date +%H%M%S).json

# 3. 删除当前认证
rm auth_profiles/active/0626.json

# 4. 使用 DEBUG 模式重新登录
poetry run python launch_camoufox.py --debug

# 5. 手动登录 Google 账号
#    - 浏览器会自动打开
#    - 正常登录
#    - 访问 AI Studio 并发送一条测试消息
#    - 确认能正常使用

# 6. 保存后关闭（Ctrl+C）

# 7. 切换回 headless 模式
poetry run python launch_camoufox.py --headless

# 8. 测试
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.5-flash","messages":[{"role":"user","content":"hi"}]}'
```

### 方案 2: 尝试不同的代理或直连 ⭐⭐

Google 可能检测到你的代理 IP 异常。

```bash
# 临时禁用代理测试
# 编辑 .env：
# UNIFIED_PROXY_CONFIG=

# 或使用不同的代理
# UNIFIED_PROXY_CONFIG=http://127.0.0.1:其他端口
```

### 方案 3: 更换 Google 账号 ⭐

如果账号被风控标记，换个账号：

```bash
# 删除所有旧认证
rm auth_profiles/active/*.json
rm auth_profiles/saved/*.json

# 使用新账号重新登录
poetry run python launch_camoufox.py --debug
```

### 方案 4: 检查代理服务 ⭐⭐

```bash
# 测试代理是否正常
curl -x http://127.0.0.1:7897 https://www.google.com

# 检查代理日志，看是否有异常
```

## 🔍 诊断步骤

### 1. 手动测试浏览器

```bash
# 使用 DEBUG 模式启动
poetry run python launch_camoufox.py --debug

# 在打开的浏览器中手动：
# 1. 访问 https://aistudio.google.com
# 2. 手动发送一条消息
# 3. 如果手动也失败 → 账号/网络问题
# 4. 如果手动成功 → 自动化检测问题
```

### 2. 检查浏览器指纹

访问这个网站测试指纹：https://abrahamjuliot.github.io/creepjs/

如果检测到自动化特征，说明反检测脚本失效。

### 3. 查看认证文件

```bash
# 检查 Cookie 是否完整
cat auth_profiles/active/0626.json | grep -i "sid\|hsid\|ssid"

# 查看文件修改时间
ls -lh auth_profiles/active/0626.json
```

## 🛡️ 为什么会出现这个问题？

### 可能原因排序：

1. **Cookie 过期/失效** (70% 可能性)
   - Google 定期使 session 失效
   - 特别是长时间未手动使用

2. **代理 IP 被标记** (20% 可能性)
   - 代理 IP 有异常流量
   - Google 检测到非本地 IP 访问

3. **账号触发风控** (5% 可能性)
   - 短时间大量请求
   - 异常访问模式

4. **Google 升级检测** (5% 可能性)
   - AI Studio 前端更新
   - 新的反自动化机制

## 📝 预防措施

### 1. 定期刷新 Cookie

```env
# .env 中启用
AUTO_SAVE_AUTH=true
```

### 2. 使用认证轮转

```bash
# 准备多个认证文件
auth_profiles/active/account1.json
auth_profiles/active/account2.json

# 启用自动轮转
AUTO_ROTATE_AUTH_PROFILE=true
```

### 3. 降低请求频率

如果短时间大量请求，Google 可能标记账号。

### 4. 使用稳定的代理

避免使用公共代理或频繁切换代理。

## ⚠️ 注意事项

1. **DEBUG 模式会显示浏览器窗口**
   - 这是正常的，用于手动登录
   - 登录成功后可关闭

2. **不要跳过手动测试**
   - 在 DEBUG 模式中手动发送消息
   - 确认账号本身没问题

3. **认证文件很重要**
   - 保存成功的认证文件
   - 不要频繁删除重建

## 🔗 相关文档

- [完整排障指南](docs/troubleshooting.md)
- [认证轮转配置](docs/auth-rotation-cookie-refresh.md)

## 📅 更新

- 2026-06-26: 初次诊断 - 问题不在代码而在认证/网络
