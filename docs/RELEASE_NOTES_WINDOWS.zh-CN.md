# VibeMouse Windows 版本说明

更新时间：2026-03-03

## 版本概览（Windows 适配阶段）

本阶段目标是把 Linux 原项目稳定落地到 Windows 11，重点是可启动、可用、可诊断、可切换。

### 主要新增能力

1. Windows 启动与运行方式
- 新增托盘启动器（后台运行、无黑框终端弹窗）
- 新增 GUI 启动器（可看日志与录音状态）
- 统一 `.venv` 启动链路，默认 Python 3.11

2. OpenClaw 路由控制
- 保留原状态机语义：
  - 前侧键：开始/结束录音
  - 后侧键空闲态：Enter
  - 后侧键录音态：停止录音并输出（普通输出或 OpenClaw 路由）
- 支持 OpenClaw 路由开关热键（默认 `F8`）
- 保留失败回退：OpenClaw 失败时回退剪贴板

3. 输入模式扩展
- 新增 `hotkey` 模式（避免 X1/X2 与浏览器/Telegram 冲突）
- 新增配置：
  - `VIBEMOUSE_INPUT_MODE=mouse|hotkey`
  - `VIBEMOUSE_FRONT_HOTKEY`
  - `VIBEMOUSE_REAR_HOTKEY`

4. 模型启动档位（便于直接用）
- `FAST`：`funasr_onnx`（更快）
- `ACCURATE`：`funasr`（更准，首启更慢）
- 首次冷启动新增预热提示，避免误判为失败

5. Windows 鼠标稳定性修复
- Windows 下侧键拦截改为 `win32_event_filter` 层处理，减少副作用
- 启动 profile 默认关闭手势冻结/回位，降低“光标错位/跳动”风险

## 验证结果（本地）

- `python -m compileall vibemouse scripts`：通过
- `python -m unittest discover -s tests -p "test_*.py"`：通过（133 tests）
- `vibemouse doctor`：可运行；在未配置 `openclaw` PATH 的 Windows 下会出现该项 fail（预期）

## 平台限制说明（当前）

1. 模型切换
- 目前是进程级加载，切换模型/后端需要重启 VibeMouse 进程（托盘下就是 Stop/Start）。

2. OpenClaw 检查
- `doctor` 若提示 `openclaw-command not found in PATH`，表示当前 Windows 侧找不到 `openclaw` 可执行命令。
- 若你使用 WSL 方案，建议保持 `VIBEMOUSE_OPENCLAW_COMMAND=wsl -d Ubuntu -- openclaw`。

3. Linux 专属检查项
- `input-device-permissions`、`hyprland-bind-conflict`、`user-service` 在 Windows 下会是 warn，不影响 Windows 主流程。

