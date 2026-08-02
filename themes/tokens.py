from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Colors:
    background: str
    sidebar: str
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
    sidebar_width: int = 204
    # Wide desktop breathing room without leaving a conspicuous unused rail
    # on 150% DPI screens. Compact windows still fall back to the minimum edge.
    content_max_width: int = 1080
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
        background="#F7F6F2",
        sidebar="#EFEEE9",
        surface="#F2F0EA",
        elevated="#FCFBF8",
        subtle="#ECEAE4",
        border="#DEDBD3",
        border_strong="#C5C1B7",
        text="#292824",
        text_secondary="#5F5C55",
        text_muted="#817D74",
        accent="#5C6557",
        accent_fill="#50594B",
        on_accent="#FFFFFF",
        accent_hover="#424B3F",
        accent_pressed="#363D34",
        accent_soft="#E4E8DF",
        focus="#737E6C",
        success="#58715F",
        success_soft="#E4ECE5",
        warning="#87662D",
        warning_soft="#F4ECD9",
        danger="#A05049",
        danger_soft="#F3E4E1",
        user_surface="#ECE9E2",
        user_text="#34312C",
    ),
)

DARK = ThemeTokens(
    name="dark",
    colors=Colors(
        background="#1E1D1A",
        sidebar="#181714",
        surface="#25231F",
        elevated="#2B2924",
        subtle="#302E29",
        border="#3D3A34",
        border_strong="#5D5950",
        text="#EFEEE9",
        text_secondary="#C7C3BA",
        text_muted="#969087",
        accent="#B7BDAA",
        accent_fill="#626B5B",
        on_accent="#FFFFFF",
        accent_hover="#717B68",
        accent_pressed="#505848",
        accent_soft="#343A31",
        focus="#C4CAB8",
        success="#8DB096",
        success_soft="#2B3A30",
        warning="#D5B06B",
        warning_soft="#403625",
        danger="#D9958F",
        danger_soft="#452D2A",
        user_surface="#33312C",
        user_text="#EFEEE9",
    ),
)


def get_theme(name: str) -> ThemeTokens:
    return DARK if name == "dark" else LIGHT
