from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Player(Base):
    """Người chơi: người dùng của hệ thống, đăng nhập bằng email."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[bytes]
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LoginSession(Base):
    """Phiên đăng nhập; chỉ lưu hash của token nằm trong cookie."""

    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Attempt(Base):
    """Lần giải: một lần người chơi làm một bài tập.

    Nhãn `correct` được chốt ở nước sai đầu tiên hoặc khi giải xong, và không đổi
    khi người chơi đi tiếp lời giải.
    """

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    puzzle_id: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    next_ply: Mapped[int] = mapped_column(default=1)
    completed: Mapped[bool] = mapped_column(default=False)
    correct: Mapped[bool | None] = mapped_column(default=None)
    solve_time_ms: Mapped[int | None] = mapped_column(default=None)


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False}
    if database_url in ("sqlite://", "sqlite:///:memory:"):
        # Một kết nối dùng chung để DB trong bộ nhớ sống suốt vòng đời app.
        return create_engine(database_url, connect_args=connect_args, poolclass=StaticPool)
    return create_engine(database_url, connect_args=connect_args)
