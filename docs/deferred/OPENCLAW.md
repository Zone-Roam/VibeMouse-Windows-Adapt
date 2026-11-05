# Deferred OpenClaw integration

OpenClaw is intentionally isolated from the default VibeMouse experience while
the core Windows voice-input, overlay, and live-caption work is in progress.

- Default runtime flag: `VIBEMOUSE_OPENCLAW_ENABLED=false`
- Isolated implementation: `vibemouse/integrations/openclaw.py`
- The tray, GUI, and Doctor do not expose or check the integration by default.
- Core recording actions always use normal text output while the flag is off.

The legacy bridge remains available for future development and compatibility
tests. Experimental development must explicitly set
`VIBEMOUSE_OPENCLAW_ENABLED=true`; it is not part of the supported user flow.
