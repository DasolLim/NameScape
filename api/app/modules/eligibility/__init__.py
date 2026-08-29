"""Eligibility: check(). Zones, OSM rules and the language test live behind it."""

from app.modules.eligibility.service import Eligibility, EligibilityVerdict, check

__all__ = ["Eligibility", "EligibilityVerdict", "check"]
