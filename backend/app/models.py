from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    whatsapp_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tracking_ids: Mapped[list["TrackingID"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Marketplace(Base):
    __tablename__ = "marketplaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    domain: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    tracking_ids: Mapped[list["TrackingID"]] = relationship(
        back_populates="marketplace", cascade="all, delete-orphan"
    )


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
