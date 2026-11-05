# Overlay themes

Each theme owns only its canvas items and rendering behavior. Window placement,
status polling, transparency, and click-through behavior stay in `overlay/app.py`.

To add a code-driven theme:

1. Add a module beside `voice_orb.py`.
2. Implement `render(state: OverlayState)`.
3. Export an `OverlayThemeSpec` with a unique snake_case name.
4. Register the spec in `themes/__init__.py`.
5. Select it with `VIBEMOUSE_OVERLAY_THEME=<theme_name>`.

The normalized state already reserves `partial_text`, `job_stage`,
`last_outcome`, and `error_code` for future subtitle and result-aware themes.
Image, GIF, and sprite-sheet asset loading will be added as a separate theme
implementation so code-driven themes do not depend on Pillow.
