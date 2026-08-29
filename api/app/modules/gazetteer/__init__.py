"""Gazetteer: search, resolve, enrich. Everything else is an implementation detail."""

from app.modules.gazetteer.service import PlaceResult, enrich, resolve, search

__all__ = ["PlaceResult", "enrich", "resolve", "search"]
