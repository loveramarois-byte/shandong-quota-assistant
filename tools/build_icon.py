from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "images" / "app.ico"
CANVAS = 256


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size, index=0)
    return ImageFont.load_default()


def main() -> None:
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=54, fill="#F4F1EC", outline="#D8D1C9", width=5)
    draw.rounded_rectangle((28, 30, 42, 226), radius=7, fill="#A16550")
    draw.rounded_rectangle((50, 30, 226, 226), radius=38, fill="#292C29")

    font = _font(112)
    text = "鲁"
    box = draw.textbbox((0, 0), text, font=font)
    width, height = box[2] - box[0], box[3] - box[1]
    x = 138 - width / 2
    y = 126 - height / 2 - box[1]
    draw.text((x, y), text, font=font, fill="#F7F4EF")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(OUTPUT)


if __name__ == "__main__":
    main()
