# Pull Request 提交流程指南

本文档记录如何向开源项目提交 Pull Request (PR) 的完整流程。

---

## 前置条件

1. 已安装 Git
2. 已有 GitHub 账户
3. 已 Fork 原项目到自己的 GitHub 账户

---

## 步骤一：Fork 原项目

1. 打开原项目 GitHub 页面（例如：`https://github.com/CJackHwang/AIstudioProxyAPI`）
2. 点击右上角 **Fork** 按钮
3. 选择你的 GitHub 账户作为目标

完成后，你将拥有：`https://github.com/你的用户名/AIstudioProxyAPI`

---

## 步骤二：配置远程仓库

```bash
# 查看当前远程仓库
git remote -v

# 添加你的 Fork 作为新的远程仓库
# 将 YOUR_USERNAME 替换为你的 GitHub 用户名
git remote add myfork https://github.com/YOUR_USERNAME/AIstudioProxyAPI.git

# 验证配置
git remote -v
# 应该看到：
# origin   https://github.com/CJackHwang/AIstudioProxyAPI.git (fetch/push)  # 原项目
# myfork   https://github.com/YOUR_USERNAME/AIstudioProxyAPI.git (fetch/push)  # 你的 Fork
```

---

## 步骤三：创建功能分支

```bash
# 确保在最新的 main 分支上
git checkout main
git pull origin main

# 创建新分支（使用描述性的名称）
git checkout -b fix/upload-button-selector

# 分支命名建议：
# - fix/xxx     修复 bug
# - feat/xxx    新功能
# - docs/xxx    文档更新
# - refactor/xxx 代码重构
```

---

## 步骤四：提交更改

```bash
# 查看更改状态
git status

# 添加更改的文件
git add browser_utils/page_controller_modules/input.py

# 或添加所有更改
git add .

# 提交（使用规范的 commit message）
git commit -m "fix: update upload button selector for new AI Studio UI

Google AI Studio changed the menu item text from 'Upload File' to 'Upload a file'.
Added fallback chain to support both old and new UI versions."
```

### Commit Message 规范

```
<type>: <subject>

<body>
```

**type 类型：**
- `fix`: 修复 bug
- `feat`: 新功能
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 代码重构
- `test`: 添加测试
- `chore`: 构建/工具变动

---

## 步骤五：推送到你的 Fork

```bash
# 推送到你的 Fork
git push myfork fix/upload-button-selector

# 如果是首次推送可能需要设置上游分支
git push -u myfork fix/upload-button-selector
```

---

## 步骤六：在 GitHub 上创建 PR

1. 打开你的 Fork 仓库页面：`https://github.com/YOUR_USERNAME/AIstudioProxyAPI`
2. GitHub 会自动检测到新推送的分支，显示 **"Compare & pull request"** 按钮
3. 点击该按钮
4. 填写 PR 信息：

### PR 标题
```
fix: update upload button selector for new AI Studio UI
```

### PR 描述模板
```markdown
## 问题描述
简要描述你发现的问题。

## 修复内容
- 列出你做的更改
- 说明为什么这样修改

## 测试
- 描述你如何测试的
- 测试结果

## 相关 Issue
如果有相关的 Issue，在这里引用：Fixes #123
```

5. 点击 **"Create pull request"** 按钮

---

## 步骤七：关联相关 Issue

如果你的 PR 是为了修复某个已存在的 Issue，需要将它们关联起来。

### 方法一：在 PR 描述或评论中使用关键词

在描述中添加以下任意格式（`123` 替换为实际 Issue 编号）：

**会自动关闭 Issue 的关键词：**
```
Fixes #123
Closes #123
Resolves #123
```

**仅关联但不自动关闭：**
```
Related to #123
See #123
Ref #123
```

### 方法二：通过右侧栏的 Development 区域

1. 在 PR 页面右侧找到 **"Development"** 区域
2. 点击 **"None yet"** 或齿轮图标
3. 搜索并选择要关联的 Issue
4. 保存

### 方法三：直接在评论区添加

在 PR 底部的 **"Add a comment"** 输入框中输入：
```
Fixes #123
```
然后点击 **"Comment"** 按钮。

---

## 后续维护

### 如果维护者要求修改

```bash
# 在同一分支上继续修改
git checkout fix/upload-button-selector

# 修改代码...

# 提交新的更改
git add .
git commit -m "fix: address review feedback"

# 推送（PR 会自动更新）
git push myfork fix/upload-button-selector
```

### 如果需要更新到最新的上游代码

```bash
# 拉取上游最新代码
git fetch origin main

# 变基到最新
git rebase origin/main

# 强制推送（如果有冲突解决后）
git push myfork fix/upload-button-selector --force-with-lease
```

### PR 合并后的清理

```bash
# 切回 main 分支
git checkout main

# 拉取最新代码（包含你的 PR）
git pull origin main

# 删除本地功能分支
git branch -d fix/upload-button-selector

# 删除远程功能分支
git push myfork --delete fix/upload-button-selector
```

---

## 常用命令速查

| 命令 | 说明 |
|------|------|
| `git remote -v` | 查看远程仓库 |
| `git status` | 查看当前状态 |
| `git diff` | 查看未暂存的更改 |
| `git log --oneline -5` | 查看最近5条提交 |
| `git branch -a` | 查看所有分支 |
| `git stash` | 暂存当前更改 |
| `git stash pop` | 恢复暂存的更改 |

---

## 本次 PR 记录

**项目**: AIstudioProxyAPI  
**修复内容**: 更新上传按钮选择器以适配新版 AI Studio UI  
**修改文件**: `browser_utils/page_controller_modules/input.py`  
**问题**: Google AI Studio 将菜单项从 "Upload File" 改为 "Upload a file"  
**解决方案**: 添加选择器回退链，优先匹配新 UI，保留对旧 UI 的兼容  
