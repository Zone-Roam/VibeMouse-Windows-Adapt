from __future__ import annotations

import math
import tkinter as tk

from vibemouse.overlay.state import OverlayState
from vibemouse.overlay.theme import OverlayThemeSpec


OVERLAY_SIZE = 92
WAVE_BAR_COUNT = 9
WAVE_BAR_SPACING = 6
WAVE_BAR_WIDTH = 4


class VoiceOrbTheme:
    """The original VibeMouse audio-reactive orb."""

    def __init__(self, canvas: tk.Canvas) -> None:
        self._canvas = canvas
        self._activity = 0.0
        self._phase = 0.0
        center = OVERLAY_SIZE // 2
        self._outer_glow_id = canvas.create_oval(
            2, 2, OVERLAY_SIZE - 2, OVERLAY_SIZE - 2, fill="#16090C", outline=""
        )
        self._mid_glow_id = canvas.create_oval(
            7, 7, OVERLAY_SIZE - 7, OVERLAY_SIZE - 7, fill="#33131B", outline=""
        )
        self._core_id = canvas.create_oval(
            13, 13, OVERLAY_SIZE - 13, OVERLAY_SIZE - 13, fill="#8E3245", outline=""
        )
        self._pulse_id = canvas.create_oval(
            center - 16,
            center - 16,
            center + 16,
            center + 16,
            fill="#FFDDE4",
            outline="",
        )
        self._wave_ids: list[int] = []
        start_x = center - ((WAVE_BAR_COUNT - 1) * WAVE_BAR_SPACING) // 2
        for idx in range(WAVE_BAR_COUNT):
            x = start_x + idx * WAVE_BAR_SPACING
            self._wave_ids.append(
                canvas.create_line(
                    x,
                    center - 8,
                    x,
                    center + 8,
                    fill="#FFF8FA",
                    width=WAVE_BAR_WIDTH,
                    capstyle=tk.ROUND,
                )
            )

    def render(self, state: OverlayState) -> None:
        now = _normalize_activity(state.audio_level) if state.recording else 0.0
        self._activity = max(now, self._activity * 0.7)
        self._phase = (self._phase + 0.32) % 10_000
        center = OVERLAY_SIZE // 2

        pulse = 10 + int(self._activity * 18)
        self._canvas.coords(
            self._pulse_id,
            center - pulse,
            center - pulse,
            center + pulse,
            center + pulse,
        )
        colors = _colors_for_activity(self._activity)
        self._canvas.itemconfig(self._outer_glow_id, fill=colors[0])
        self._canvas.itemconfig(self._mid_glow_id, fill=colors[1])
        self._canvas.itemconfig(self._core_id, fill=colors[2])
        self._canvas.itemconfig(self._pulse_id, fill=colors[3])

        mid = (WAVE_BAR_COUNT - 1) / 2.0
        for idx, bar_id in enumerate(self._wave_ids):
            distance = abs(idx - mid)
            focus = max(0.2, 1.0 - (distance / (mid + 0.5)))
            oscillation = 0.5 + 0.5 * math.sin(self._phase + idx * 0.72)
            bar_half = 4.0 + (2.0 + self._activity * 20.0) * focus * oscillation
            x = (
                center
                - ((WAVE_BAR_COUNT - 1) * WAVE_BAR_SPACING) / 2.0
                + idx * WAVE_BAR_SPACING
            )
            self._canvas.coords(bar_id, x, center - bar_half, x, center + bar_half)
            self._canvas.itemconfig(bar_id, fill=colors[4])


def _normalize_activity(raw_level: float) -> float:
    noise_floor = 0.0012
    speech_peak = 0.018
    if raw_level <= noise_floor:
        return 0.0
    return min(1.0, (raw_level - noise_floor) / (speech_peak - noise_floor))


def _colors_for_activity(activity: float) -> tuple[str, str, str, str, str]:
    if activity < 0.3:
        return "#14080B", "#2C1018", "#7A2B3D", "#FFE8EE", "#FFF7F9"
    if activity < 0.7:
        return "#1A0A0E", "#34131C", "#96374B", "#FFE2E9", "#FFF4F7"
    return "#220D12", "#3D1620", "#AB3E55", "#FFD9E3", "#FFF0F4"


VOICE_ORB_THEME = OverlayThemeSpec(
    name="voice_orb",
    width=OVERLAY_SIZE,
    height=OVERLAY_SIZE,
    window_alpha=0.78,
    create=VoiceOrbTheme,
)
