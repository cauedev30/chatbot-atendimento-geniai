"""Draws the invented screenshots of the image evaluation cases (geniai/eval/images/*.png).

Every screen is made up here, with the fictitious catalog's systems (Painel, WhatsApp) and no real
unit, person, phone number or third-party brand. Needs Pillow, which is not a dependency of the
service; run from backend/ once, then commit the PNGs:

    pip install pillow
    python scripts/make_eval_images.py
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "geniai" / "eval" / "images"
SIZE = (640, 400)
INK, MUTED, LINE, PAGE = "#1f2933", "#616e7c", "#cbd2d9", "#f5f7fa"
RED, RED_BG, BLUE = "#ab091e", "#ffe3e3", "#2f5fd0"


FONTS = ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf")
"""The first one installed is used: Pillow's own default font has no accented letters."""


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def app_screen(breadcrumb: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """A blank page of the invented "Painel" web app, with its top bar."""
    image = Image.new("RGB", SIZE, PAGE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, SIZE[0], 48), fill=INK)
    draw.text((20, 13), "Painel", font=font(22), fill="white")
    draw.text((120, 17), breadcrumb, font=font(15), fill="#9aa5b1")
    return image, draw


def login_error() -> Image.Image:
    image, draw = app_screen("Entrar")
    draw.rounded_rectangle((170, 70, 470, 370), radius=10, fill="white", outline=LINE)
    draw.text((200, 88), "Entrar no Painel", font=font(22), fill=INK)
    draw.rounded_rectangle((195, 130, 445, 172), radius=6, fill=RED_BG, outline=RED)
    draw.text((208, 142), "Senha incorreta. Tente de novo.", font=font(15), fill=RED)
    for top, name, value in ((190, "E-mail", "usuario@exemplo.com"), (255, "Senha", "••••••••")):
        draw.text((200, top), name, font=font(14), fill=MUTED)
        draw.rounded_rectangle((200, top + 20, 440, top + 52), radius=5, fill="white", outline=LINE)
        draw.text((210, top + 27), value, font=font(15), fill=INK)
    draw.rounded_rectangle((200, 322, 440, 356), radius=6, fill=BLUE)
    draw.text((296, 330), "Entrar", font=font(16), fill="white")
    return image


def blank_report() -> Image.Image:
    image, draw = app_screen("Relatórios  /  Vendas do mês")
    draw.text((30, 68), "Relatório de vendas", font=font(24), fill=INK)
    draw.text((30, 102), "Período: 01/09 a 30/09", font=font(15), fill=MUTED)
    draw.rectangle((30, 135, 610, 375), fill="white", outline=LINE)
    for x, title in ((45, "Data"), (190, "Cliente"), (380, "Serviço"), (530, "Valor")):
        draw.text((x, 147), title, font=font(15), fill=MUTED)
    draw.line((30, 175, 610, 175), fill=LINE)
    draw.text((205, 250), "Nenhum dado para exibir.", font=font(18), fill=MUTED)
    return image


def whatsapp_disconnected() -> Image.Image:
    image, draw = app_screen("Configurações  /  WhatsApp da unidade")
    draw.text((30, 68), "WhatsApp da unidade", font=font(24), fill=INK)
    draw.rounded_rectangle((30, 108, 170, 136), radius=14, fill=RED_BG, outline=RED)
    draw.text((52, 113), "Desconectado", font=font(15), fill=RED)
    draw.text((30, 160), "O número foi desconectado do Painel.", font=font(16), fill=INK)
    draw.text((30, 186), "Leia o QR Code com o celular da unidade", font=font(16), fill=INK)
    draw.text((30, 208), "para conectar de novo.", font=font(16), fill=INK)
    # An invented pattern in the place of a QR Code; it encodes nothing.
    rng = random.Random(7)
    left, top, cell = 420, 150, 8
    draw.rectangle((left - 10, top - 10, left + 25 * cell + 10, top + 25 * cell + 10), fill="white", outline=LINE)
    for row in range(25):
        for col in range(25):
            corner = (row < 7 or row > 17) and (col < 7 or col > 17) and not (row > 17 and col > 17)
            if (
                corner
                and (
                    row in (0, 6, 18, 24) or col in (0, 6, 18, 24) or (row % 18 in (2, 3, 4) and col % 18 in (2, 3, 4))
                )
            ) or (not corner and rng.random() < 0.45):
                x, y = left + col * cell, top + row * cell
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=INK)
    return image


def landscape() -> Image.Image:
    """Nothing to do with support: a drawn landscape, with no text."""
    image = Image.new("RGB", SIZE, "#9fd3f5")
    draw = ImageDraw.Draw(image)
    draw.ellipse((470, 40, 560, 130), fill="#ffd166")
    draw.polygon([(0, 300), (160, 140), (330, 300)], fill="#6b8f71")
    draw.polygon([(220, 300), (420, 110), (640, 300)], fill="#557a5e")
    draw.rectangle((0, 290, SIZE[0], SIZE[1]), fill="#88b04b")
    draw.ellipse((60, 60, 170, 100), fill="white")
    draw.ellipse((110, 45, 220, 95), fill="white")
    return image


IMAGES = {
    "painel-senha-incorreta.png": login_error,
    "painel-relatorio-vazio.png": blank_report,
    "whatsapp-desconectado.png": whatsapp_disconnected,
    "paisagem.png": landscape,
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, draw in IMAGES.items():
        draw().save(OUT / name, optimize=True)
        print(f"{OUT / name} ({(OUT / name).stat().st_size} bytes)")


if __name__ == "__main__":
    main()
