"""Distance, bearing, and how close a guess came. Internal, and pure.

Kept apart from the play path because it is arithmetic with exact answers, and
because the two boundaries in it decide what colour a player sees: 500km and
3000km are the whole feedback vocabulary of the puzzle.
"""

import math
from enum import Enum
from typing import Final

#: Mean radius, which is what the great-circle formula wants.
EARTH_RADIUS_KM: Final = 6371.0088

#: The furthest two points on the planet can be, and so the zero point of
#: proximity: a guess this far out is as wrong as a guess can be.
EARTH_HALF_CIRCUMFERENCE_KM: Final = math.pi * EARTH_RADIUS_KM

#: Inclusive upper bounds, in kilometres. Named so the numbers appear once.
NEAR_KM: Final = 500.0
FAR_KM: Final = 3000.0

#: Eight arrows, so each covers 45 degrees, centred on its own direction.
_ARROWS: Final = ("⬆️", "↗️", "➡️", "↘️", "⬇️", "↙️", "⬅️", "↖️")
_ARC: Final = 360 / len(_ARROWS)

Point = tuple[float, float]


class Band(Enum):
    """How close a guess landed. The marker is what the share grid prints."""

    CORRECT = "🟩"
    NEAR = "🟨"
    FAR = "🟧"
    COLD = "⬜"

    @property
    def marker(self) -> str:
        return self.value


def distance_km(origin: Point, target: Point) -> float:
    """Great-circle distance between two (lat, lon) pairs.

    Haversine rather than a flat subtraction of coordinates, which is what
    makes the antimeridian unremarkable: 179E to 179W is 222km, not most of
    the planet.
    """
    lat1, lon1 = math.radians(origin[0]), math.radians(origin[1])
    lat2, lon2 = math.radians(target[0]), math.radians(target[1])

    half_lat = (lat2 - lat1) / 2
    half_lon = (lon2 - lon1) / 2
    inner = math.sin(half_lat) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(half_lon) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(inner))


def bearing_degrees(origin: Point, target: Point) -> float:
    """Initial bearing from origin to target, 0 at north, clockwise."""
    lat1, lon1 = math.radians(origin[0]), math.radians(origin[1])
    lat2, lon2 = math.radians(target[0]), math.radians(target[1])
    delta_lon = lon2 - lon1

    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return math.degrees(math.atan2(y, x)) % 360


def arrow(degrees: float) -> str:
    """One of eight arrows. 348.75 to 11.25 degrees is north, and so on."""
    index = int((degrees % 360 + _ARC / 2) // _ARC) % len(_ARROWS)
    return _ARROWS[index]


def band(distance: float) -> Band:
    """Which band a distance falls in. Inclusive at both edges.

    Only an exact match is correct: the answer is a gazetteer record, not a
    coordinate, so a guess a metre away is still a different place.
    """
    if distance == 0:
        return Band.CORRECT
    if distance <= NEAR_KM:
        return Band.NEAR
    if distance <= FAR_KM:
        return Band.FAR
    return Band.COLD


def proximity(distance: float) -> int:
    """How far there the guess got, as a whole percentage.

    A wrong guess that was close should read as progress rather than a flat no,
    which is the point of showing this at all.
    """
    share = 1 - (distance / EARTH_HALF_CIRCUMFERENCE_KM)
    return max(0, min(100, round(share * 100)))
