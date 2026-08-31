"""Distance, bearing, and the bands a guess falls into.

Pure arithmetic, no database. The boundaries are the acceptance criterion for
this step: a guess at exactly 500km and one at exactly 3000km have to land on
the right side of the line, and the antimeridian must not be a special case
anybody has to remember.
"""

import pytest

from app.modules.puzzles import geo

# Known pairs, with distances from the standard great-circle formula.
LONDON = (51.5074, -0.1278)
PARIS = (48.8566, 2.3522)
NEW_YORK = (40.7128, -74.0060)
SYDNEY = (-33.8688, 151.2093)


def test_a_place_is_no_distance_from_itself() -> None:
    assert geo.distance_km(LONDON, LONDON) == pytest.approx(0.0, abs=0.001)


def test_london_to_paris_is_the_famous_344km() -> None:
    assert geo.distance_km(LONDON, PARIS) == pytest.approx(344, abs=3)


def test_london_to_new_york_is_five_and_a_half_thousand() -> None:
    assert geo.distance_km(LONDON, NEW_YORK) == pytest.approx(5570, abs=20)


def test_london_to_sydney_is_most_of_the_way_round() -> None:
    assert geo.distance_km(LONDON, SYDNEY) == pytest.approx(16_990, abs=40)


def test_crossing_the_antimeridian_is_short_not_most_of_the_planet() -> None:
    """The failure this test exists to catch: subtracting longitudes gives 358
    degrees here, and a naive implementation reports twenty thousand kilometres
    for a two hundred kilometre hop.
    """
    east = (0.0, 179.0)
    west = (0.0, -179.0)

    assert geo.distance_km(east, west) == pytest.approx(222, abs=2)


def test_the_poles_are_the_full_meridian_apart() -> None:
    assert geo.distance_km((90.0, 0.0), (-90.0, 0.0)) == pytest.approx(20_015, abs=20)


def test_bearing_is_the_direction_you_would_set_off_in() -> None:
    assert geo.bearing_degrees(LONDON, PARIS) == pytest.approx(149, abs=2)
    assert geo.bearing_degrees((0.0, 0.0), (10.0, 0.0)) == pytest.approx(0, abs=0.1)
    assert geo.bearing_degrees((0.0, 0.0), (0.0, 10.0)) == pytest.approx(90, abs=0.1)
    assert geo.bearing_degrees((10.0, 0.0), (0.0, 0.0)) == pytest.approx(180, abs=0.1)
    assert geo.bearing_degrees((0.0, 10.0), (0.0, 0.0)) == pytest.approx(270, abs=0.1)


def test_bearing_across_the_antimeridian_points_the_short_way() -> None:
    assert geo.bearing_degrees((0.0, 179.0), (0.0, -179.0)) == pytest.approx(90, abs=0.1)
    assert geo.bearing_degrees((0.0, -179.0), (0.0, 179.0)) == pytest.approx(270, abs=0.1)


@pytest.mark.parametrize(
    ("degrees", "arrow"),
    [
        (0, "⬆️"),
        (45, "↗️"),
        (90, "➡️"),
        (135, "↘️"),
        (180, "⬇️"),
        (225, "↙️"),
        (270, "⬅️"),
        (315, "↖️"),
        (359, "⬆️"),
        # Eight arrows of 45 degrees each, so north runs to 22.5.
        (22, "⬆️"),
        (23, "↗️"),
    ],
)
def test_a_bearing_becomes_one_of_eight_arrows(degrees: float, arrow: str) -> None:
    assert geo.arrow(degrees) == arrow


def test_the_bands_are_right_on_the_line() -> None:
    """The acceptance criterion for this step. Inclusive at both edges: a guess
    exactly 500km out is within 500km, which is what the words say.
    """
    assert geo.band(0) is geo.Band.CORRECT
    assert geo.band(499.9) is geo.Band.NEAR
    assert geo.band(500) is geo.Band.NEAR
    assert geo.band(500.1) is geo.Band.FAR
    assert geo.band(2999.9) is geo.Band.FAR
    assert geo.band(3000) is geo.Band.FAR
    assert geo.band(3000.1) is geo.Band.COLD


def test_only_an_exact_match_is_correct() -> None:
    """Proximity is never the answer: a guess one metre away is still wrong,
    because the answer is a gazetteer record and not a coordinate.
    """
    assert geo.band(0.001) is geo.Band.NEAR


def test_each_band_has_its_own_marker() -> None:
    markers = {band: band.marker for band in geo.Band}

    assert markers[geo.Band.CORRECT] == "🟩"
    assert markers[geo.Band.NEAR] == "🟨"
    assert markers[geo.Band.FAR] == "🟧"
    assert markers[geo.Band.COLD] == "⬜"
    # Four distinct markers, or the grid says nothing.
    assert len(set(markers.values())) == 4


def test_proximity_reads_as_a_percentage_of_the_way_there() -> None:
    """Shown per guess beside the distance, so a wrong guess still feels like
    progress rather than a flat no."""
    assert geo.proximity(0) == 100
    assert geo.proximity(geo.EARTH_HALF_CIRCUMFERENCE_KM) == 0
    assert geo.proximity(geo.EARTH_HALF_CIRCUMFERENCE_KM / 2) == pytest.approx(50, abs=1)
    # Never negative, however far off the guess is.
    assert geo.proximity(99_999) == 0
