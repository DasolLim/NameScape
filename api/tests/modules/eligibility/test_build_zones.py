"""The Overpass parser, exercised against a committed fixture. No network."""

import json
from pathlib import Path

from scripts.build_zones import disputed_rings, to_rings

FIXTURE = Path(__file__).parents[2] / "fixtures" / "overpass_sample.json"
DISPUTED = Path(__file__).parents[3] / "data" / "zones" / "disputed.yaml"


def test_overpass_ways_become_closed_polygons() -> None:
    zones = to_rings(json.loads(FIXTURE.read_text(encoding="utf-8")))

    assert len(zones) == 2
    for wkt, reason in zones:
        coordinates = wkt.removeprefix("POLYGON((").removesuffix("))").split(",")
        assert coordinates[0] == coordinates[-1], "ring must close"
        assert reason.endswith("Naming is disabled here.")


def test_ways_with_too_few_points_are_skipped() -> None:
    assert to_rings([{"geometry": [{"lat": 1.0, "lon": 1.0}], "tags": {}}]) == []


def test_the_disputed_file_parses_into_closed_rings() -> None:
    zones = disputed_rings(DISPUTED)

    assert len(zones) >= 3
    for wkt, reason in zones:
        coordinates = wkt.removeprefix("POLYGON((").removesuffix("))").split(",")
        assert coordinates[0] == coordinates[-1]
        assert "Disputed territory" in reason
