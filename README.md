# VibeMouse

> **Windows adaptation of [vimalinx/VibeMouse](https://github.com/vimalinx/VibeMouse)** (Apache-2.0). The original project and its core voice-input design are by Vimalinx. This repository adds Windows support: a tray launcher with a hidden background runtime, one-click launch scripts, a minimal GUI, live logging and an OpenClaw routing toggle.

Mouse-side-button voice input for VibeCoding.

中文文档：[`README.zh-CN.md`](./README.zh-CN.md)

## What This Project Does

VibeMouse binds your coding speech workflow to mouse side buttons:
- Front side button: start/stop recording
- Rear side button while idle: send Enter
- Rear side button while recording: stop recording and output the transcript

Core goals are low friction, stable daily use, and graceful fallback when any subsystem fails.

## Runtime Architecture (Core)

The runtime is event-driven and split by responsibility:

1. `vibemouse/main.py`
   - CLI entry (`run` / `doctor`)
2. `vibemouse/app.py`
   - Orchestrates button events, recording state, transcription workers, and final output routing
3. `vibemouse/mouse_listener.py`
   - Captures side buttons and gestures (`evdev` first, fallback path available)
4. `vibemouse/audio.py`
   - Records audio to temp WAV
5. `vibemouse/transcriber.py`
   - SenseVoice backend selection and transcription
6. `vibemouse/output.py`
   - Text typing / clipboard routing and fallback
7. `vibemouse/system_integration.py`
   - Platform adapter boundary (Hyprland now, Windows/macOS extension points prepared)
8. `vibemouse/doctor.py`
   - Built-in diagnostics for environment, input permissions, and known conflicts

## Repository Structure (At a Glance)

```text
VibeMouse/
  vibemouse/     # Runtime package (app, transcriber, output, config, doctor)
  scripts/       # Windows launchers, tray GUI helpers, utility scripts
  tests/         # Unit tests
  docs/          # Deployment/adaptation guides and release notes
```

## Model and Backend Architecture

- Primary ASR model: `iic/SenseVoiceSmall`
- Backends:
  - `funasr`: `funasr.AutoModel` + optional VAD (`fsmn-vad`)
  - `funasr_onnx`: `funasr_onnx.SenseVoiceSmall` (ONNX path; quantized inference)
  - `auto`: choose backend by preferred device and fallback rules
- Device path:
  - `VIBEMOUSE_DEVICE` controls preferred device
  - If model load fails and `VIBEMOUSE_FALLBACK_CPU=true`, runtime falls back to CPU
- Model source:
  - ONNX mode resolves `iic/SenseVoiceSmall` to `iic/SenseVoiceSmall-onnx`
  - Model assets can be downloaded via ModelScope snapshot API

Default launcher profiles:
- `scripts/start_vibemouse_tray_fast.bat` -> `VIBEMOUSE_BACKEND=funasr_onnx`
- `scripts/start_vibemouse_tray_accurate.bat` -> `VIBEMOUSE_BACKEND=funasr`

## Optional Translation Route (ZH -> EN)

- Provider mode: OpenAI-compatible Chat Completions API (`/chat/completions`)
- Config:
  - `VIBEMOUSE_TRANSLATION_API_BASE`
  - `VIBEMOUSE_TRANSLATION_API_KEY`
  - `VIBEMOUSE_TRANSLATION_MODEL`
- Defaults in config:
  - API base: `https://api.openai.com/v1`
  - model: `gpt-4o-mini`
- If API key is empty, translation is skipped and original text is preserved.

## Quick Start (Linux)

### Ubuntu / Debian packages

```bash
sudo apt update
sudo apt install -y python3-gi gir1.2-atspi-2.0 portaudio19-dev libsndfile1
```

### Arch packages

```bash
sudo pacman -Syu --needed python python-pip python-gobject portaudio libsndfile
```

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

### Run

```bash
export VIBEMOUSE_BACKEND=auto
export VIBEMOUSE_DEVICE=cpu
vibemouse
```

## Quick Start (Windows, Tray)

From PowerShell in repo root:

```powershell
cd .\scripts
.\start_vibemouse_tray_fast.bat
```

Accurate profile:

```powershell
cd .\scripts
.\start_vibemouse_tray_accurate.bat
```

## Default Mapping and State Logic

- `VIBEMOUSE_FRONT_BUTTON` default: `x1`
- `VIBEMOUSE_REAR_BUTTON` default: `x2`

State matrix:
- Idle + rear press -> Enter (`VIBEMOUSE_ENTER_MODE`)
- Recording + rear press -> stop recording + normal text output

If your hardware labels are reversed:

```bash
export VIBEMOUSE_FRONT_BUTTON=x2
export VIBEMOUSE_REAR_BUTTON=x1
```

## Built-in Doctor

Run diagnostics:

```bash
vibemouse doctor
```

Current checks include:
- Config load validity
- Microphone input availability
- Linux input device permissions / side-button capability
- Hyprland rear-button Return bind conflicts
- `systemctl --user` service activity

Exit code is non-zero when any `FAIL` check exists.

## Frequently Used Variables

| Variable | Default | Purpose |
|---|---|---|
| `VIBEMOUSE_ENTER_MODE` | `enter` | Rear-button submit mode (`enter`, `ctrl_enter`, `shift_enter`, `none`) |
| `VIBEMOUSE_AUTO_PASTE` | `false` | Auto paste when route falls back to clipboard |
| `VIBEMOUSE_GESTURES_ENABLED` | `false` | Enable gesture recognition |
| `VIBEMOUSE_GESTURE_TRIGGER_BUTTON` | `rear` | Gesture trigger (`front`, `rear`, `right`) |
| `VIBEMOUSE_GESTURE_THRESHOLD_PX` | `120` | Gesture movement threshold |
| `VIBEMOUSE_GESTURE_FREEZE_POINTER` | `true` | Freeze pointer during gesture capture |
| `VIBEMOUSE_PREWARM_ON_START` | `true` | Preload ASR on startup to reduce first-use latency |
| `VIBEMOUSE_STATUS_FILE` | `$XDG_RUNTIME_DIR/vibemouse-status.json` | Runtime status for bars/widgets |

Full configuration source of truth: `vibemouse/config.py`.

## Troubleshooting Shortlist

### Rear button still sends Enter while recording

Check Hyprland-level hard bind conflict in
`~/.config/hypr/UserConfigs/UserKeybinds.conf` and remove lines like:

```ini
bind = , mouse:275, sendshortcut, , Return, activewindow
bind = , mouse:276, sendshortcut, , Return, activewindow
```

Then reload:

```bash
hyprctl reload config-only
```

### Side button not detected on Linux

```bash
sudo usermod -aG input $USER
# relogin required
```

## For AI Assistants and Platform Adapters

Use this guide when adapting to Windows/macOS or custom environments:

- [`docs/AI_ASSISTANT_DEPLOYMENT.md`](./docs/AI_ASSISTANT_DEPLOYMENT.md)
- [`docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md`](./docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md)

It contains architecture contracts, dependency download links, adaptation workflow,
and a prompt template for autonomous platform adaptation.

## License

Source code is licensed under Apache-2.0. See `LICENSE`.

Third-party and model asset notices: `THIRD_PARTY_NOTICES.md`.
