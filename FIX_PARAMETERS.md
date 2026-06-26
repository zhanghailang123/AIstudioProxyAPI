# 参数面板展开问题修复方案

## 问题诊断

**症状：**
```
Error operating temperature input: Locator expected to be visible
Error: element(s) not found
waiting for locator("ms-slider input[type=\"number\"][max=\"2\"]...")
```

**根本原因：**
代码尝试直接访问 Temperature/Top-P 控件，但这些控件可能在**未展开的参数设置面板**中。

## 解决方案

### 方案1: 添加参数面板展开逻辑（推荐）

在 `parameters.py` 的 `adjust_parameters` 方法开始时，添加展开逻辑：

```python
async def adjust_parameters(self, ...):
    """Adjust all request parameters."""
    
    # ⭐ 新增：确保参数面板展开
    await self._ensure_settings_panel_expanded(check_client_disconnected)
    
    # 原有逻辑...
    temperature = request_params.get("temperature")
    ...
```

添加新方法：

```python
async def _ensure_settings_panel_expanded(self, check_client_disconnected: Callable):
    """确保参数设置面板已展开"""
    try:
        # 查找可能的折叠按钮/面板
        panel_selectors = [
            'button[aria-label*="Run settings" i]',
            'button[aria-label*="Model settings" i]',
            'button[aria-label*="Advanced settings" i]',
            'button[aria-label*="Configuration" i]',
            'button[aria-label*="Settings" i]',
            '[data-testid*="settings-panel"]',
            '.settings-panel',
            'ms-model-config-panel button',
        ]
        
        for selector in panel_selectors:
            try:
                panel_locator = self.page.locator(selector)
                if await panel_locator.count() > 0:
                    # 检查是否已展开
                    aria_expanded = await panel_locator.first.get_attribute("aria-expanded")
                    class_attr = await panel_locator.first.get_attribute("class") or ""
                    
                    # 如果未展开，点击展开
                    if aria_expanded == "false" or "collapsed" in class_attr:
                        self.logger.debug(f"[Param] Expanding settings panel: {selector}")
                        await panel_locator.first.click(timeout=3000)
                        await check_client_disconnected("After expanding settings panel")
                        await asyncio.sleep(0.5)
                        return
                    else:
                        self.logger.debug(f"[Param] Settings panel already expanded")
                        return
            except Exception:
                continue
        
        # 如果没有找到面板按钮，说明可能默认就是展开的
        self.logger.debug("[Param] No collapsible settings panel found, assuming expanded")
        
    except Exception as e:
        self.logger.warning(f"[Param] Error checking settings panel: {e}")
        # 继续执行，尝试直接访问控件
```

### 方案2: 参数控件找不到时跳过（临时）

修改错误处理，让参数设置失败不影响请求提交：

```python
# 在 _adjust_temperature 的 except 块中
except Exception as pw_err:
    self.logger.warning(
        f"Error operating temperature input: {pw_err}. Skipping adjustment."
    )
    # 不抛出异常，继续执行
```

### 方案3: 增加重试和等待时间

```python
# 修改等待超时
await expect_async(temp_input_locator).to_be_visible(timeout=10000)  # 5000 -> 10000

# 添加滚动到可见
await temp_input_locator.scroll_into_view_if_needed()
await asyncio.sleep(0.5)
```

## 立即测试

我建议先用**方案2（跳过失败的参数设置）**快速测试，确认是否是参数设置导致的 403。

修改位置：
- `browser_utils/page_controller_modules/parameters.py:197-208`
- `browser_utils/page_controller_modules/parameters.py:506-514`

## 下一步

1. 先测试跳过参数设置是否能避免 403
2. 如果可以，再实现方案1完整修复
3. 如果还是 403，说明问题在其他地方
