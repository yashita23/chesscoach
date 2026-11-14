from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, String, create_engine, func, inspect, text
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
    khi người chơi đi tiếp lời giải. `solve_time_ms` tính từ lúc mở lần giải tới lúc
    chốt nhãn (gồm cả thời gian diễn nước của đối thủ trên giao diện). Mỗi người chơi
    có tối đa một lần giải cho mỗi bài tập.
    """

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    puzzle_id: Mapped[str] = mapped_column(String(16))
    # Ảnh chụp bài tập lúc mở lần giải, để tính lại năng lực mà không phải tra kho bài tập.
    puzzle_rating: Mapped[int | None] = mapped_column(default=None)
    puzzle_themes: Mapped[str | None] = mapped_column(String(500), default=None)
    """Các chủ đề của bài tập, cách nhau bởi dấu cách; đọc qua `themes`."""
    started_at: Mapped[datetime] = mapped_column(DateTime)
    next_ply: Mapped[int] = mapped_column(default=1)
    completed: Mapped[bool] = mapped_column(default=False)
    correct: Mapped[bool | None] = mapped_column(default=None)
    solve_time_ms: Mapped[int | None] = mapped_column(default=None)

    @property
    def themes(self) -> tuple[str, ...]:
        return tuple((self.puzzle_themes or "").split())

    @themes.setter
    def themes(self, themes: Iterable[str]) -> None:
        self.puzzle_themes = " ".join(themes)

    @property
    def decided_at(self) -> datetime | None:
        """Lúc chốt nhãn: thời điểm mở cộng thời gian giải."""
        if self.solve_time_ms is None:
            return None
        return self.started_at + timedelta(milliseconds=self.solve_time_ms)


def add_missing_columns(engine: Engine) -> None:
    """Thêm cột mới (cho phép NULL) vào bảng đã có, vì create_all không sửa bảng cũ.

    Chưa có công cụ migration; đủ cho DB local khi model chỉ thêm cột.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    kind = column.type.compile(engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}'))


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False}
    if database_url in ("sqlite://", "sqlite:///:memory:"):
        # Một kết nối dùng chung để DB trong bộ nhớ sống suốt vòng đời app.
        return create_engine(database_url, connect_args=connect_args, poolclass=StaticPool)
    return create_engine(database_url, connect_args=connect_args)
