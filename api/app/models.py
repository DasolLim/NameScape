import uuid
from datetime import datetime

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    username_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ui_language: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Place(Base):
    """A gazetteer record. Never user-authored; every discovery anchors to one."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geonames_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    wof_id: Mapped[int | None] = mapped_column(BigInteger)
    wikidata_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    name_normalized: Mapped[str] = mapped_column(Text)
    alternate_names: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    feature_class: Mapped[str] = mapped_column(CHAR(1))
    feature_code: Mapped[str] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(CHAR(2))
    admin1: Mapped[str | None] = mapped_column(Text)
    centroid: Mapped[WKBElement] = mapped_column(Geography("POINT", srid=4326))
    tier: Mapped[int] = mapped_column(SmallInteger)
    population: Mapped[int] = mapped_column(Integer, default=0)
    etymology: Mapped[str | None] = mapped_column(Text)


class Discovery(Base):
    """A user's claim on a place. The unique place_id is what makes it scarce."""

    __tablename__ = "discoveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    place_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("places.id"), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    caption: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MagicLink(Base):
    """A single-use sign-in token. Only the hash is stored."""

    __tablename__ = "magic_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contest(Base):
    """A 24h nickname contest, opened by the first proposal on a place."""

    __tablename__ = "contests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    place_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("places.id"))
    status: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    winner_proposal_id: Mapped[int | None] = mapped_column(BigInteger)
    winning_score: Mapped[int | None] = mapped_column(Integer)
    term_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Proposal(Base):
    """A nickname put forward in a contest."""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    contest_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("contests.id"))
    place_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("places.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    agree: Mapped[int] = mapped_column(Integer, default=0)
    disagree: Mapped[int] = mapped_column(Integer, default=0)
    is_incumbent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Vote(Base):
    """One vote per account per proposal, changeable until the contest closes."""

    __tablename__ = "votes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    proposal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proposals.id"), primary_key=True
    )
    value: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RestrictedZone(Base):
    """A polygon that gates nomination. It never affects rendering."""

    __tablename__ = "restricted_zones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geom: Mapped[WKBElement] = mapped_column(Geography("POLYGON", srid=4326))
    rule_type: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)


class Bookmark(Base):
    """A personal save. Unlimited, and the lightest action in the product."""

    __tablename__ = "bookmarks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    place_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("places.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Nickname(Base):
    """The resolved winner. What the globe renders beneath the official name."""

    __tablename__ = "nicknames"

    place_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("places.id"), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    proposal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proposals.id"))
    score: Mapped[int] = mapped_column(Integer)
    term_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NicknameHistory(Base):
    __tablename__ = "nickname_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    place_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("places.id"))
    text: Mapped[str] = mapped_column(Text)
    held_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    held_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
