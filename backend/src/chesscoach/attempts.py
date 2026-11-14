"""API làm bài tập: chọn bài, mở lần giải, gửi từng nước, xem lịch sử lần giải."""

from datetime import UTC, datetime
from typing import Annotated, Literal

import chess
from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from chesscoach.auth import CurrentPlayer, Db, player_api_router
from chesscoach.db import Attempt
from chesscoach.puzzles import Puzzle, PuzzleCatalog
from chesscoach.solving import IllegalMove, board_at, judge, player_color

router = player_api_router()


def get_catalog(request: Request) -> PuzzleCatalog:
    catalog: PuzzleCatalog = request.app.state.puzzle_catalog
    return catalog


Catalog = Annotated[PuzzleCatalog, Depends(get_catalog)]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _puzzle_or_404(catalog: PuzzleCatalog, puzzle_id: str) -> Puzzle:
    puzzle = catalog.get(puzzle_id)
    if puzzle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có bài tập này")
    return puzzle


class NextPuzzleOut(BaseModel):
    puzzle_id: str


@router.get("/puzzles/next")
def next_puzzle(player: CurrentPlayer, db: Db, catalog: Catalog) -> NextPuzzleOut:
    """Bài tập đang làm dở (chưa có nhãn) nếu có; nếu không thì một bài tập chưa làm."""
    unfinished = db.scalars(
        select(Attempt.puzzle_id)
        .where(Attempt.player_id == player.id, Attempt.correct.is_(None))
        .order_by(Attempt.started_at.desc())
    ).first()
    if unfinished is not None:
        return NextPuzzleOut(puzzle_id=unfinished)
    done = db.scalars(select(Attempt.puzzle_id).where(Attempt.player_id == player.id)).all()
    puzzle = catalog.random_excluding(done)
    if puzzle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bạn đã làm hết bài tập")
    return NextPuzzleOut(puzzle_id=puzzle.id)


class StartRequest(BaseModel):
    puzzle_id: str


class AttemptOut(BaseModel):
    attempt_id: int
    puzzle_id: str
    rating: int
    start_fen: str
    """Thế cờ trước nước đầu của đối thủ, để giao diện diễn lại nước đó."""
    opponent_move: str
    fen: str
    player_color: Literal["white", "black"]


def _attempt_out(attempt: Attempt, puzzle: Puzzle) -> AttemptOut:
    # next_ply luôn trỏ vào lượt của người chơi; nước ngay trước đó là nước vừa đi của đối thủ.
    last_opponent_ply = attempt.next_ply - 1
    return AttemptOut(
        attempt_id=attempt.id,
        puzzle_id=puzzle.id,
        rating=puzzle.rating,
        start_fen=board_at(puzzle, last_opponent_ply).fen(),
        opponent_move=puzzle.moves[last_opponent_ply],
        fen=board_at(puzzle, attempt.next_ply).fen(),
        player_color="white" if player_color(puzzle) == chess.WHITE else "black",
    )


@router.post("/attempts", status_code=status.HTTP_201_CREATED)
def start_attempt(
    body: StartRequest, player: CurrentPlayer, db: Db, catalog: Catalog, response: Response
) -> AttemptOut:
    """Mở lần giải cho một bài tập. Lần giải đang dở thì mở lại (200); bài tập đã có nhãn thì 409."""
    puzzle = _puzzle_or_404(catalog, body.puzzle_id)
    existing = db.scalars(
        select(Attempt).where(Attempt.player_id == player.id, Attempt.puzzle_id == puzzle.id)
    ).first()
    if existing is not None:
        if existing.correct is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Bạn đã làm bài tập này")
        response.status_code = status.HTTP_200_OK
        return _attempt_out(existing, puzzle)

    attempt = Attempt(player_id=player.id, puzzle_id=puzzle.id, started_at=_now())
    db.add(attempt)
    db.commit()
    return _attempt_out(attempt, puzzle)


class AttemptSummaryOut(BaseModel):
    attempt_id: int
    puzzle_id: str
    started_at: datetime
    completed: bool
    correct: bool | None
    solve_time_ms: int | None


@router.get("/attempts")
def list_attempts(player: CurrentPlayer, db: Db) -> list[AttemptSummaryOut]:
    """Các lần giải của người chơi, mới nhất trước."""
    rows = db.scalars(
        select(Attempt)
        .where(Attempt.player_id == player.id)
        .order_by(Attempt.started_at.desc(), Attempt.id.desc())
    ).all()
    return [
        AttemptSummaryOut(
            attempt_id=a.id,
            puzzle_id=a.puzzle_id,
            started_at=a.started_at.replace(tzinfo=UTC),  # SQLite lưu giờ UTC không kèm múi giờ
            completed=a.completed,
            correct=a.correct,
            solve_time_ms=a.solve_time_ms,
        )
        for a in rows
    ]


class MoveRequest(BaseModel):
    uci: str


class MoveOut(BaseModel):
    verdict: Literal["correct", "wrong"]
    fen: str
    opponent_move: str | None
    expected_move: str | None
    completed: bool
    correct: bool | None
    """Nhãn của lần giải; None khi chưa chốt (chưa sai nước nào và chưa giải xong)."""


@router.post("/attempts/{attempt_id}/moves")
def play_move(
    attempt_id: int, body: MoveRequest, player: CurrentPlayer, db: Db, catalog: Catalog
) -> MoveOut:
    attempt = db.get(Attempt, attempt_id)
    if attempt is None or attempt.player_id != player.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có lần giải này")
    if attempt.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lần giải này đã xong")
    puzzle = _puzzle_or_404(catalog, attempt.puzzle_id)

    try:
        verdict = judge(puzzle, attempt.next_ply, body.uci)
    except IllegalMove:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nước đi không hợp lệ")

    if attempt.correct is None and (not verdict.accepted or verdict.puzzle_completed):
        attempt.correct = verdict.accepted
        attempt.solve_time_ms = int((_now() - attempt.started_at).total_seconds() * 1000)
    attempt.next_ply = verdict.next_ply
    attempt.completed = verdict.puzzle_completed
    db.commit()

    return MoveOut(
        verdict="correct" if verdict.accepted else "wrong",
        fen=verdict.fen,
        opponent_move=verdict.opponent_move,
        expected_move=verdict.expected_move,
        completed=verdict.puzzle_completed,
        correct=attempt.correct,
    )
