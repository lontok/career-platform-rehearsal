from sqlalchemy import Boolean, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        Index("ux_profiles_seed_key", "seed_key", unique=True),
        Index(
            "ux_profiles_single_published",
            "published",
            unique=True,
            sqlite_where=text("published = 1"),
            postgresql_where=text("published = true"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    seed_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    headline: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(255))
    target_roles: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(String(320))
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
