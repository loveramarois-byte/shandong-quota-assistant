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
    # Chinese cost-engineering tables stay readable at these sizes on 125% DPI.
    caption: int = 11
    meta: int = 12
    body: int = 14
    section: int = 15
    title: int = 20


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    colors: Colors
    spacing: tuple[int, ...] = (4, 8, 12, 16, 20, 24, 32, 40)
    radius_sm: int = 8
    radius_md: int = 10
    radius_lg: int = 14
    control_height: int = 40
    icon_sm: int = 16
    icon_md: int = 18
    transition_fast: int = 150
    transition_normal: int = 220
    transition_slow: int = 300
    font_family: str = "Microsoft YaHei UI"
    typography: Typography = field(default_factory=Typography)

    def font(self, size: int, weight: str = "regular") -> tuple[str, int, str]:
        # Inter has no Chinese glyphs; YaHei UI ships with Windows and keeps
        # Chinese/Latin mixed lines on one baseline. Bold covers medium+.
        tk_weight = "bold" if weight in {"semibold", "bold"} else "normal"
        return (self.font_family, size, tk_weight)


LIGHT = ThemeTokens(
    name="light",
    colors=Colors(
        background="#F7F6F3",
        sidebar="#EFEEE9",
        surface="#FCFBF9",
        elevated="#FFFFFF",
        subtle="#EEECE7",
        border="#DCD8D0",
        border_strong="#BDB7AE",
        text="#252825",
        text_secondary="#555A55",
        text_muted="#74766F",
        accent="#98563F",
        accent_hover="#854933",
        accent_pressed="#743C29",
        accent_soft="#EEE0D8",
        focus="#7D4937",
        success="#3F7252",
        success_soft="#E2EEE4",
        warning="#805D1C",
        warning_soft="#F2E9D4",
        danger="#934940",
        danger_soft="#F2E1DD",
        user_surface="#ECE2DA",
        user_text="#40352F",
    ),
)

DARK = ThemeTokens(
    name="dark",
    colors=Colors(
        background="#1F211F",
        sidebar="#1A1C1A",
        surface="#272A27",
        elevated="#2D302D",
        subtle="#343733",
        border="#454943",
        border_strong="#676B64",
        text="#F2F1ED",
        text_secondary="#C8C8C1",
        text_muted="#A5A69F",
        accent="#D7A088",
        accent_hover="#E3AE95",
        accent_pressed="#BF8269",
        accent_soft="#49372F",
        focus="#E3AE95",
        success="#91C39E",
        success_soft="#2B3C31",
        warning="#E0B66C",
        warning_soft="#433A29",
        danger="#E4A19A",
        danger_soft="#49302D",
        user_surface="#3C342F",
        user_text="#F4E6DE",
    ),
)


def get_theme(name: str) -> ThemeTokens:
    return DARK if name == "dark" else LIGHT
