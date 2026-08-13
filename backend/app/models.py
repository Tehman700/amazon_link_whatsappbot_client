from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    whatsapp_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Reply format: 'direct' = tagged Amazon link (original behavior, default),
    # 'hub' = article page on the Beast Affiliates website. server_default so
    # existing production rows keep behaving exactly as before the migration.
    link_preference: Mapped[str] = mapped_column(
        String(8), default="direct", server_default="direct"
    )
    store_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    # Which site this user's US articles are published to. "" = the original
    # destination, so every existing user keeps behaving exactly as before.
    # Values must match US_SITES in the website's config.py — the admin picks
    # one here, the website resolves it to a domain and stamps it on the link.
    us_site: Mapped[str] = mapped_column(String(32), default="", server_default="")

    tracking_ids: Mapped[list["TrackingID"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class LinkedNumber(Base):
    """Extra WhatsApp numbers linked to a user via the portal's code handshake.
    A linked number behaves exactly like the primary: same tags, preference,
    and attribution. Cap: MAX_NUMBERS_PER_USER total per user, enforced on
    claim in routers/process.py (6 since 2026-07-27 — primary + 5 linked)."""

    __tablename__ = "linked_numbers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    whatsapp_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    user: Mapped["User"] = relationship()


class Marketplace(Base):
    __tablename__ = "marketplaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    domain: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Built-in tracking ID for this country: new users are pre-filled with it
    # so the admin only edits the ones that differ.
    default_tag: Mapped[str] = mapped_column(String(64), default="", server_default="")

    tracking_ids: Mapped[list["TrackingID"]] = relationship(
        back_populates="marketplace", cascade="all, delete-orphan"
    )


class ResolvedLink(Base):
    """A blog/landing page and the Amazon product URL it was found to lead to.

    Those pages are fetched from a datacenter IP, and their hosts throttle
    datacenter traffic hard enough that the same page is served one minute and
    refused the next. Once a page has answered successfully there is no reason
    to ask it again, so the answer is kept here and reused for every later send
    of the same link, by any user."""

    __tablename__ = "resolved_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Lookups go through a hash: indexing the URL itself would risk Postgres'
    # btree key-size limit on the very long links some of these sites use.
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    amazon_url: Mapped[str] = mapped_column(String(2048))
    resolved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrackingID(Base):
    __tablename__ = "tracking_ids"
    __table_args__ = (UniqueConstraint("user_id", "marketplace_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    marketplace_id: Mapped[int] = mapped_column(
        ForeignKey("marketplaces.id", ondelete="CASCADE")
    )
    tag: Mapped[str] = mapped_column(String(64))

    user: Mapped["User"] = relationship(back_populates="tracking_ids")
    marketplace: Mapped["Marketplace"] = relationship(back_populates="tracking_ids")
