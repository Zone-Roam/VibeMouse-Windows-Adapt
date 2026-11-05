from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from vibemouse.overlay.state import OverlayState


class OverlayTheme(Protocol):
    def render(self, state: OverlayState) -> None: ...


ThemeFactory = Callable[[tk.Canvas], OverlayTheme]


@dataclass(frozen=True)
class OverlayThemeSpec:
    name: str
    width: int
    height: int
    window_alpha: float
    create: ThemeFactory
