from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class Avatar(Base):
    __tablename__ = "avatars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    greeting: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    emoji: Mapped[str] = mapped_column(String(10), nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="current_avatar")
    messages: Mapped[list["DialogMessage"]] = relationship(back_populates="avatar")
    facts: Mapped[list["MemoryFact"]] = relationship(back_populates="avatar")

    def __repr__(self) -> str:
        return f"<Avatar(id={self.id}, name={self.name!r})>"


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    current_avatar_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("avatars.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    current_avatar: Mapped[Optional["Avatar"]] = relationship(back_populates="users")
    messages: Mapped[list["DialogMessage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    facts: Mapped[list["MemoryFact"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, avatar_id={self.current_avatar_id})>"


class DialogMessage(Base):
    __tablename__ = "dialog_messages"
    __table_args__ = (
        Index(
            "ix_dialog_messages_user_avatar_created",
            "user_id",
            "avatar_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    avatar_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("avatars.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="messages")
    avatar: Mapped["Avatar"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<DialogMessage(id={self.id}, role={self.role!r})>"


class MemoryFact(Base):
    __tablename__ = "memory_facts"
    __table_args__ = (
        Index(
            "ix_memory_facts_user_avatar_active",
            "user_id",
            "avatar_id",
            postgresql_where="is_active = true",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    avatar_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("avatars.id", ondelete="CASCADE"), nullable=False
    )
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="facts")
    avatar: Mapped["Avatar"] = relationship(back_populates="facts")

    def __repr__(self) -> str:
        return f"<MemoryFact(id={self.id}, active={self.is_active})>"
