"""Text normalisation. Internal to the moderation module."""

import re
import unicodedata
from typing import Final

#: Zero-width and joiner characters used to break up blocked terms.
_INVISIBLE: Final = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0x180E, 0xFEFF], None)

#: Cyrillic and Greek lookalikes. NFKC does not fold these; they are visually
#: identical to Latin letters and are the cheapest blocklist evasion there is.
_HOMOGLYPHS: Final = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "ѕ": "s",
        "і": "i",
        "ј": "j",
        "ԁ": "d",
        "һ": "h",
        "ν": "v",
        "ɡ": "g",
        "α": "a",
        "ε": "e",
        "ο": "o",
        "ρ": "p",
        "τ": "t",
        "κ": "k",
        "ι": "i",
    }
)

_LEETSPEAK: Final = str.maketrans(
    {
        "4": "a",
        "@": "a",
        "3": "e",
        "1": "i",
        "!": "i",
        "|": "i",
        "0": "o",
        "5": "s",
        "$": "s",
        "7": "t",
        "8": "b",
    }
)


def normalize(text: str) -> str:
    """Trim, collapse whitespace, strip invisibles, fold homoglyphs."""
    folded = unicodedata.normalize("NFKC", text).translate(_INVISIBLE)
    folded = folded.casefold().translate(_HOMOGLYPHS)
    return re.sub(r"\s+", " ", folded).strip()


def fold_for_matching(text: str) -> str:
    """A harsher fold used only for blocklist comparison.

    Leetspeak is undone and every separator dropped, so 'b4d w0rd' and
    'b-a-d-w-o-r-d' collapse onto the same string.
    """
    return re.sub(r"[^a-z0-9]", "", normalize(text).translate(_LEETSPEAK))
