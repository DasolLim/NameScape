import uuid
from datetime import datetime

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    CHAR,
    BigInteger,
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
