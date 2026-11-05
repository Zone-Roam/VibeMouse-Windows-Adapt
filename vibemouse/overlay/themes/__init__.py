from __future__ import annotations

from vibemouse.overlay.theme import OverlayThemeSpec
from vibemouse.overlay.themes.voice_orb import VOICE_ORB_THEME


_THEMES: dict[str, OverlayThemeSpec] = {
    VOICE_ORB_THEME.name: VOICE_ORB_THEME,
}


def available_theme_names() -> tuple[str, ...]:
    return tuple(sorted(_THEMES))


def get_theme_spec(name: str) -> OverlayThemeSpec:
    normalized = name.strip().lower().replace("-", "_")
    if not normalized:
        normalized = VOICE_ORB_THEME.name
    try:
        return _THEMES[normalized]
    except KeyError as error:
        choices = ", ".join(available_theme_names())
        raise ValueError(f"Unknown overlay theme {name!r}. Available themes: {choices}") from error
