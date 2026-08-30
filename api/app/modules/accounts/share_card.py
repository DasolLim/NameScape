"""The passport share card. Internal to accounts.

A PNG rather than SVG: social preview crawlers do not rasterise SVG, and a
broken preview kills the growth loop silently.
"""

import io
import unicodedata
from typing import Final

from PIL import Image, ImageDraw, ImageFont

from app.modules.accounts.service import Passport

#: Standard Open Graph card size.
WIDTH: Final = 1200
HEIGHT: Final = 630

HANDLE_MAX_CHARS: Final = 24

# Design tokens from the brand doc.
INK_900: Final = "#0E131C"
INK_700: Final = "#1E2735"
PARCHMENT_50: Final = "#F5F1E8"
PARCHMENT_400: Final = "#9B9484"
BRASS_500: Final = "#E8A33D"

#: Control, format (bidi overrides) and surrogate characters.
_UNSAFE_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs"})


def fit(text: str, limit: int) -> str:
    """Make user text safe to draw: no control characters, no overflow."""
    stripped = "".join(
        character for character in text if unicodedata.category(character) not in _UNSAFE_CATEGORIES
    ).strip()

    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1] + "\u2026"


def render(passport: Passport) -> bytes:
    """Draw the card. The first-finder count is the hero number."""
    card = Image.new("RGB", (WIDTH, HEIGHT), INK_900)
    draw = ImageDraw.Draw(card)

    hero_font = ImageFont.load_default(size=160)
    title_font = ImageFont.load_default(size=44)
    label_font = ImageFont.load_default(size=26)

    draw.rectangle([(0, 0), (WIDTH, 8)], fill=BRASS_500)

    draw.text((72, 92), "TOPONOMICON", font=label_font, fill=PARCHMENT_400)
    draw.text(
        (72, 140),
        f"@{fit(passport.username, HANDLE_MAX_CHARS)}",
        font=title_font,
        fill=PARCHMENT_50,
    )

    draw.text((72, 250), str(passport.first_finds), font=hero_font, fill=BRASS_500)
    draw.text((72, 440), "places found first", font=label_font, fill=PARCHMENT_400)

    countries = sorted(passport.countries.items(), key=lambda item: -item[1])[:6]
    x = 72
    for code, count in countries:
        draw.rectangle([(x, 500), (x + 132, 566)], fill=INK_700)
        draw.text((x + 18, 508), code, font=label_font, fill=PARCHMENT_50)
        draw.text((x + 18, 536), str(count), font=label_font, fill=BRASS_500)
        x += 148

    draw.text(
        (72, HEIGHT - 52),
        "the atlas of absurd place names",
        font=label_font,
        fill=PARCHMENT_400,
    )

    buffer = io.BytesIO()
    card.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
