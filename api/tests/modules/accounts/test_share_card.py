import io

from PIL import Image

from app.modules.accounts import share_card
from app.modules.accounts.service import Passport

#: A right-to-left override: invisible, and a classic way to disguise text.
BIDI_OVERRIDE = "\u202e"


def passport(username: str = "collector", discoveries: int = 12) -> Passport:
    return Passport(
        username=username,
        discoveries=discoveries,
        first_finds=discoveries,
        countries={"CA": 7, "GB": 5},
        completion={"CA": 0.02, "GB": 0.01},
    )


def test_the_card_is_a_png_at_the_standard_share_size() -> None:
    image = Image.open(io.BytesIO(share_card.render(passport())))

    assert image.format == "PNG"
    assert image.size == (share_card.WIDTH, share_card.HEIGHT)


def test_a_very_long_handle_is_truncated_rather_than_overflowing() -> None:
    drawn = share_card.fit("x" * 200, share_card.HANDLE_MAX_CHARS)

    assert len(drawn) <= share_card.HANDLE_MAX_CHARS
    assert drawn.endswith("\u2026")


def test_user_text_cannot_smuggle_control_characters_into_the_card() -> None:
    hostile = f"coll\nector{BIDI_OVERRIDE}  <script>"

    cleaned = share_card.fit(hostile, share_card.HANDLE_MAX_CHARS)

    assert "\n" not in cleaned
    assert BIDI_OVERRIDE not in cleaned


def test_a_hostile_handle_still_renders() -> None:
    image = Image.open(io.BytesIO(share_card.render(passport(username=BIDI_OVERRIDE * 80))))

    assert image.size == (share_card.WIDTH, share_card.HEIGHT)
