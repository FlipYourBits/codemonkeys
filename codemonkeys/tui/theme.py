"""Color palettes and theme management for the codemonkeys TUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePalette:
    name: str
    bg: str
    bg_dark: str
    surface: str
    surface_light: str
    text: str
    text_dim: str
    accent: str
    accent_hover: str
    cyan: str
    green: str
    yellow: str
    red: str
    orange: str
    purple: str

    def to_variables(self) -> dict[str, str]:
        return {
            "bg": self.bg,
            "bg-dark": self.bg_dark,
            "surface": self.surface,
            "surface-light": self.surface_light,
            "text": self.text,
            "text-dim": self.text_dim,
            "accent": self.accent,
            "accent-hover": self.accent_hover,
            "cyan": self.cyan,
            "green": self.green,
            "yellow": self.yellow,
            "red": self.red,
            "orange": self.orange,
            "purple": self.purple,
        }


THEMES: dict[str, ThemePalette] = {
    "dracula": ThemePalette(
        name="Dracula",
        bg="#282a36",
        bg_dark="#1e1f29",
        surface="#282a36",
        surface_light="#44475a",
        text="#f8f8f2",
        text_dim="#6272a4",
        accent="#bd93f9",
        accent_hover="#ff79c6",
        cyan="#8be9fd",
        green="#50fa7b",
        yellow="#f1fa8c",
        red="#ff5555",
        orange="#ffb86c",
        purple="#bd93f9",
    ),
    "nord": ThemePalette(
        name="Nord",
        bg="#2e3440",
        bg_dark="#242933",
        surface="#2e3440",
        surface_light="#3b4252",
        text="#eceff4",
        text_dim="#4c566a",
        accent="#88c0d0",
        accent_hover="#81a1c1",
        cyan="#8fbcbb",
        green="#a3be8c",
        yellow="#ebcb8b",
        red="#bf616a",
        orange="#d08770",
        purple="#b48ead",
    ),
    "catppuccin": ThemePalette(
        name="Catppuccin Mocha",
        bg="#1e1e2e",
        bg_dark="#181825",
        surface="#1e1e2e",
        surface_light="#313244",
        text="#cdd6f4",
        text_dim="#6c7086",
        accent="#cba6f7",
        accent_hover="#f5c2e7",
        cyan="#89dceb",
        green="#a6e3a1",
        yellow="#f9e2af",
        red="#f38ba8",
        orange="#fab387",
        purple="#cba6f7",
    ),
    "gruvbox": ThemePalette(
        name="Gruvbox Dark",
        bg="#282828",
        bg_dark="#1d2021",
        surface="#282828",
        surface_light="#3c3836",
        text="#ebdbb2",
        text_dim="#665c54",
        accent="#d79921",
        accent_hover="#fabd2f",
        cyan="#83a598",
        green="#b8bb26",
        yellow="#fabd2f",
        red="#fb4934",
        orange="#fe8019",
        purple="#d3869b",
    ),
    "tokyo-night": ThemePalette(
        name="Tokyo Night",
        bg="#1a1b26",
        bg_dark="#16161e",
        surface="#1a1b26",
        surface_light="#24283b",
        text="#c0caf5",
        text_dim="#565f89",
        accent="#7aa2f7",
        accent_hover="#bb9af7",
        cyan="#7dcfff",
        green="#9ece6a",
        yellow="#e0af68",
        red="#f7768e",
        orange="#ff9e64",
        purple="#bb9af7",
    ),
}

THEME_ORDER = ["tokyo-night", "dracula", "nord", "catppuccin", "gruvbox"]
