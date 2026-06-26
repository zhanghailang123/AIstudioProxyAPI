#!/usr/bin/env python3
"""
反自动化检测增强配置

根据手动操作成功、自动化失败的情况，增强自动化行为的人类化特征
"""

import os
from pathlib import Path

# 获取 .env 文件路径
env_path = Path(__file__).parent / ".env"

# 需要调整的配置
configs_to_update = {
    # 强制使用键盘逐字输入，避免批量粘贴被检测
    "LONG_PROMPT_BULK_INPUT_THRESHOLD": "999999",

    # 增加操作间的延迟，模拟人类思考时间
    "POST_SPINNER_CHECK_DELAY_MS": "1000",
    "POST_COMPLETION_BUFFER": "1500",

    # 点击超时增加，避免操作过快
    "CLICK_TIMEOUT_MS": "5000",

    # 确保 Thinking 启用（根据需求）
    "ENABLE_THINKING_BUDGET": "true",

    # 确保 Google Search 关闭（避免冲突）
    "ENABLE_GOOGLE_SEARCH": "false",

    # 自动保存认证
    "AUTO_SAVE_AUTH": "true",

    # Headless 模式
    "LAUNCH_MODE": "headless",
}

def update_env_file():
    """更新 .env 文件配置"""
    if not env_path.exists():
        print(f"❌ 错误：找不到 .env 文件: {env_path}")
        return False

    # 读取现有配置
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 更新配置
    updated_lines = []
    updated_keys = set()

    for line in lines:
        updated = False
        for key, value in configs_to_update.items():
            if line.startswith(f"{key}="):
                updated_lines.append(f"{key}={value}\n")
                updated_keys.add(key)
                updated = True
                print(f"✅ 更新: {key}={value}")
                break

        if not updated:
            updated_lines.append(line)

    # 检查是否有遗漏的配置
    missing_keys = set(configs_to_update.keys()) - updated_keys
    if missing_keys:
        print(f"\n⚠️  警告：以下配置未找到，将追加到文件末尾：")
        for key in missing_keys:
            value = configs_to_update[key]
            updated_lines.append(f"\n# 自动添加的配置\n{key}={value}\n")
            print(f"   {key}={value}")

    # 写回文件
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)

    print(f"\n✅ 配置已更新到: {env_path}")
    return True

def print_summary():
    """打印配置说明"""
    print("\n" + "="*60)
    print("🎯 反自动化检测增强 - 配置说明")
    print("="*60)
    print("""
主要变化：

1. 强制键盘逐字输入
   LONG_PROMPT_BULK_INPUT_THRESHOLD=999999
   → 避免批量粘贴操作被检测

2. 增加操作延迟
   POST_SPINNER_CHECK_DELAY_MS=1000
   POST_COMPLETION_BUFFER=1500
   CLICK_TIMEOUT_MS=5000
   → 模拟人类操作的自然节奏

3. 其他优化
   - 启用 Thinking Budget
   - 关闭 Google Search（避免冲突）
   - 自动保存认证

下一步：
1. 重启服务：
   poetry run python launch_camoufox.py --headless

2. 测试请求：
   curl -X POST http://127.0.0.1:2048/v1/chat/completions \\
     -H "Content-Type: application/json" \\
     -d '{"model":"gemini-3.5-flash","messages":[{"role":"user","content":"hi"}]}'

3. 如果仍然失败，尝试：
   - 更换代理或禁用代理
   - 使用不同的 Google 账号
   - 在 DEBUG 模式下观察行为差异
""")
    print("="*60)

if __name__ == "__main__":
    print("🔧 开始更新反自动化检测配置...\n")

    if update_env_file():
        print_summary()
        print("\n✅ 配置更新完成！请重启服务测试。\n")
    else:
        print("\n❌ 配置更新失败！\n")
        exit(1)
