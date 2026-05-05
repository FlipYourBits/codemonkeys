"""Color palette and style constants for the codemonkeys TUI."""

from __future__ import annotations

SEVERITY_COLORS = {
    "high": "#ff5555",
    "medium": "#ffb86c",
    "low": "#8be9fd",
    "info": "#6272a4",
}

STATUS_COLORS = {
    "running": "#f1fa8c",
    "done": "#50fa7b",
    "failed": "#ff5555",
    "queued": "#6272a4",
    "waiting": "#bd93f9",
}

ACCENT = "#bd93f9"
ACCENT_DIM = "#44475a"
SURFACE = "#282a36"
SURFACE_LIGHT = "#44475a"
TEXT = "#f8f8f2"
TEXT_DIM = "#6272a4"
