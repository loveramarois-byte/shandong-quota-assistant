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
    # Compact Fluent-like scale for mixed Chinese/Latin cost-engineering content.
    caption: int = 11
    meta: int = 12
    body: int = 14
    section: int = 16
    title: int = 22


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    colors: Colors
    spacing: tuple[int, ...] = (4, 8, 12, 16, 20, 24, 32, 40)
    radius_xs: int = 6
    radius_sm: int = 8
    radius_md: int = 10
    radius_lg: int = 12
    control_height: int = 38
    control_height_sm: int = 30
    sidebar_width: int = 204
    content_max_width: int = 960
    icon_sm: int = 16
    icon_md: int = 18
    transition_fast: int = 150
    transition_normal: int = 220
    transition_slow: int = 300
    font_family: str = "Segoe UI"
    typography: Typography = field(default_factory=Typography)

    def font(self, size: int, weight: str = "regular") -> tuple[str, int, str]:
        # Tk falls back to YaHei UI for CJK glyphs while Segoe keeps controls
        # visually native to Windows. Bold covers medium and semibold weights.
        tk_weight = "bold" if weight in {"semibold", "bold"} else "normal"
        return (self.font_family, size, tk_weight)


LIGHT = ThemeTokens(
    name="light",
    colors=Colors(
        background="#F5F6F4",
        sidebar="#ECEFEB",
        surface="#FAFBFA",
        elevated="#FFFFFF",
        subtle="#E9ECE8",
        border="#D9DEDA",
        border_strong="#B8C0BA",
        text="#1D2420",
        text_secondary="#4D5851",
        text_muted="#758079",
        accent="#315C4B",
        accent_fill="#315C4B",
        on_accent="#FFFFFF",
        accent_hover="#284E3F",
        accent_pressed="#203F34",
        accent_soft="#DDE9E2",
        focus="#477A65",
        success="#397052",
        success_soft="#E0EDE5",
        warning="#85621F",
        warning_soft="#F4ECD8",
        danger="#9A4744",
        danger_soft="#F4E3E1",
        user_surface="#E6ECE8",
        user_text="#263C32",
    ),
)

DARK = ThemeTokens(
    name="dark",
    colors=Colors(
        background="#191D1A",
        sidebar="#151916",
        surface="#202521",
        elevated="#272D29",
        subtle="#2D342F",
        border="#39413C",
        border_strong="#5E6962",
        text="#EEF2EF",
        text_secondary="#BDC7C0",
        text_muted="#8E9A92",
        accent="#89B8A3",
        accent_fill="#3F715D",
        on_accent="#FFFFFF",
        accent_hover="#4B806A",
        accent_pressed="#345E4E",
        accent_soft="#294137",
        focus="#A6D2BE",
        success="#83BE9A",
        success_soft="#263B2F",
        warning="#DCB86E",
        warning_soft="#403725",
        danger="#E39A96",
        danger_soft="#452D2C",
        user_surface="#293C33",
        user_text="#E5F0E9",
    ),
)


def get_theme(name: str) -> ThemeTokens:
    return DARK if name == "dark" else LIGHT
