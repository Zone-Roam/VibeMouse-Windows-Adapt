# scripts 目录说明（Windows）

更新时间：2026-03-03

## 推荐入口（保留在 scripts 根目录）

1. 托盘 + 热键 + 快速识别（推荐日常）
- `start_vibemouse_tray_hotkey_fast.bat`

2. 托盘 + 热键 + 高精度
- `start_vibemouse_tray_hotkey_accurate.bat`

3. 托盘 + 鼠标侧键 + 快速识别
- `start_vibemouse_tray_fast.bat`

4. 托盘 + 鼠标侧键 + 高精度
- `start_vibemouse_tray_accurate.bat`

5. 打开个人词典（纠错）
- `open_user_dictionary.bat`

## 运行内核脚本（不要直接双击）

- `run_tray.py`
- `run_gui.py`
- `start_vibemouse_tray.vbs`

## 已归档旧版本脚本

为减少主目录混乱，以下旧入口已迁移到：
- `scripts/archive/2026-03-03_legacy_launchers/`

归档文件：
- `start_vibemouse.bat`
- `start_vibemouse.ps1`
- `start_vibemouse_fast.bat`
- `start_vibemouse_fast.ps1`
- `start_vibemouse_accurate.bat`
- `start_vibemouse_accurate.ps1`
- `start_vibemouse_gui.bat`
- `start_vibemouse_tray.bat`

## 你现在应该怎么用

如果你在 Telegram/浏览器里有 X1/X2 冲突，优先使用热键版：
- `start_vibemouse_tray_hotkey_fast.bat`
- 或 `start_vibemouse_tray_hotkey_accurate.bat`

并在鼠标驱动里把侧键映射到：
- 前键热键：`Ctrl+Alt+Shift+F9`
- 后键热键：`Ctrl+Alt+Shift+F10`

Cursor CLI 兼容：
- 热键托盘脚本默认开启 `VIBEMOUSE_WINDOWS_CURSOR_TERMINAL_MODE=true`
- 在 Cursor 里会优先按终端粘贴顺序：`Shift+Insert` -> `Ctrl+Shift+V` -> `Ctrl+V`

Win11 录音动态反馈：
- 热键托盘脚本默认开启 `VIBEMOUSE_TRAY_MIC_OVERLAY=true`
- 录音时会出现桌面悬浮麦克风点，随音量强弱动态变化
- 无声时基本不动，停止录音时自动隐藏

中译英翻译（DeepSeek API）：
- 不再使用翻译快捷键（默认禁用）
- 在托盘图标右键菜单勾选：`Enable ZH->EN Translation`
- 勾选后运行中即时生效（不重启服务）
- API Key 推荐放在项目脚本，不要写入系统环境变量：
  1. 复制 `scripts/local_api_keys.example.bat` 为 `scripts/local_api_keys.bat`
  2. 编辑其中 `VIBEMOUSE_TRANSLATION_API_KEY`
  3. 启动脚本会自动 `call scripts/local_api_keys.bat`
- 默认走 DeepSeek OpenAI 兼容接口：
  - `VIBEMOUSE_TRANSLATION_API_BASE=https://api.deepseek.com/v1`
  - `VIBEMOUSE_TRANSLATION_MODEL=deepseek-chat`
- 未设置 API Key 时，翻译会自动跳过并保留原文输出（不会报错退出）

## 个人词典与记忆文件

- 词典文件：`.runtime/user_dictionary.json`
- 历史记忆：`.runtime/transcript-history.jsonl`

词典格式示例：

```json
{
  "replacements": {
    "telegarm": "Telegram",
    "open claw": "OpenClaw",
    "chat g p t": "ChatGPT"
  }
}
```

说明：
- 左边写“常识别错的词/短语”
- 右边写“你想要的最终输出”
- 匹配不区分大小写
