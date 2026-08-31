"""Readable names for GeoNames admin1 codes. Internal to the gazetteer.

Some countries use a two-letter code ("US.FL"), others a number ("CA.05").
Showing a number next to a place name is noise, so codes are resolved to
names at import time and stored alongside the place.
"""

from pathlib import Path

#: (country_code, admin1_code) -> readable name
RegionLookup = dict[tuple[str, str], str]


def parse(contents: str) -> RegionLookup:
    """Read admin1CodesASCII.txt: `CC.CODE<tab>name<tab>ascii<tab>geonameid`."""
    lookup: RegionLookup = {}
    for line in contents.splitlines():
        fields = line.split("\t")
        if len(fields) < 2 or "." not in fields[0]:
            continue
        country, _, code = fields[0].partition(".")
        if country and code:
            lookup[(country, code)] = fields[1]
    return lookup


def name_for(lookup: RegionLookup, country: str | None, code: str | None) -> str | None:
    """The readable name, or the raw code when it is not in the table."""
    if not code:
        return None
    if not country:
        return code
    return lookup.get((country, code), code)


def load(path: Path) -> RegionLookup:
    if not path.exists():
        return {}
    return parse(path.read_text(encoding="utf-8"))
