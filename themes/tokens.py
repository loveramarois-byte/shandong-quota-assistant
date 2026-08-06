from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Colors:
    background: str
    sidebar: str
    sidebar_border: str
    surface: str
    elevated: str
    subtle: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_fill: str
    on_accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    focus: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    user_surface: str
    user_text: str


@dataclass(frozen=True)
class Typography:
    # Quiet editorial scale for mixed Chinese/Latin cost-engineering content.
    caption: int = 12
    meta: int = 13
    body: int = 15
    section: int = 17
    title: int = 22


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    colors: Colors
    spacing: tuple[int, ...] = (4, 8, 12, 16, 20, 24, 32, 40)
    radius_xs: int = 5
    radius_sm: int = 8
    radius_md: int = 10
    radius_lg: int = 12
    control_height: int = 40
    control_height_sm: int = 32
    # The rail is deliberately wide enough for Chinese session names at the
    # common 125%-150% Windows scale. The conversation remains the primary
    # surface, but no longer competes with a clipped navigation column.
    sidebar_width: int = 252
    main_min_width: int = 760
    # Keep the work surface readable on wide monitors while preserving a
    # little room for result tables and evidence actions.
    content_max_width: int = 820
    icon_sm: int = 16
    icon_md: int = 18
    transition_fast: int = 150
    transition_normal: int = 220
    transition_slow: int = 300
    font_family: str = "Inter"
    typography: Typography = field(default_factory=Typography)

    def font(self, size: int, weight: str = "regular") -> tuple[str, int, str]:
        # Windows/Tk falls back to the system CJK font for glyphs Inter lacks.
        # Bold covers medium and semibold in Tk's portable font tuple.
        tk_weight = "bold" if weight in {"semibold", "bold"} else "normal"
        return (self.font_family, size, tk_weight)


LIGHT = ThemeTokens(
    name="light",
    colors=Colors(
        background="#F3F4F1",
        sidebar="#E9EBE7",
        sidebar_border="#D2D5CF",
        surface="#FAFAF8",
        elevated="#FFFFFF",
        subtle="#ECEEEA",
        border="#DADDD7",
        border_strong="#BFC4BC",
        text="#272A27",
        text_secondary="#5B605B",
        text_muted="#6B6A64",
        accent="#5F6D60",
        accent_fill="#556356",
        on_accent="#FFFFFF",
        accent_hover="#485548",
        accent_pressed="#3D473E",
        accent_soft="#E0E6DF",
        focus="#657765",
        success="#4F755C",
        success_soft="#E2EBE4",
        warning="#80642F",
        warning_soft="#F2EBD9",
        danger="#9E504A",
        danger_soft="#F1E3E1",
        user_surface="#E6E9E4",
        user_text="#303430",
    ),
)

DARK = ThemeTokens(
    name="dark",
    colors=Colors(
        background="#1C1E1B",
        sidebar="#161815",
        sidebar_border="#343834",
        surface="#232622",
        elevated="#292C28",
        subtle="#2D312D",
        border="#393E39",
        border_strong="#555C55",
        text="#ECEFEA",
        text_secondary="#BCC2BC",
        text_muted="#8F9790",
        accent="#AAB7A8",
        accent_fill="#5E6E60",
        on_accent="#FFFFFF",
        accent_hover="#6D7D6F",
        accent_pressed="#4C594E",
        accent_soft="#303832",
        focus="#BECBBC",
        success="#8FB69A",
        success_soft="#29372E",
        warning="#D5B06B",
        warning_soft="#3C3425",
        danger="#D9958F",
        danger_soft="#422C2A",
        user_surface="#2F332F",
        user_text="#ECEFEA",
    ),
)


def get_theme(name: str) -> ThemeTokens:
    return DARK if name == "dark" else LIGHT
