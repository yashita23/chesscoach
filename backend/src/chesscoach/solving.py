"""Chấm nước đi trong một lần giải. Hàm thuần: không đọc DB, không biết HTTP."""

from dataclasses import dataclass
from typing import Literal

import chess

from chesscoach.puzzles import Puzzle


class IllegalMove(ValueError):
    pass


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    """Nước đúng: trùng lời giải hoặc là nước chiếu hết."""
    puzzle_completed: bool
    opponent_move: str | None
    next_ply: int
    fen: str
    expected_move: str | None
    """Nước đúng theo lời giải, chỉ có khi nước vừa đi sai."""


def board_at(puzzle: Puzzle, ply: int) -> chess.Board:
    """Thế cờ sau `ply` nước đầu của chuỗi Moves (ply 1 = sau nước đầu của đối thủ)."""
    board = chess.Board(puzzle.fen)
    for uci in puzzle.moves[:ply]:
        board.push_uci(uci)
    return board


def player_color(puzzle: Puzzle) -> chess.Color:
    return board_at(puzzle, 1).turn


def color_name(puzzle: Puzzle) -> Literal["white", "black"]:
    """Bên người chơi cầm quân, dạng chữ cho API."""
    return "white" if player_color(puzzle) == chess.WHITE else "black"


def judge(puzzle: Puzzle, ply: int, uci: str) -> Verdict:
    """Chấm nước `uci` của người chơi khi lượt hiện tại là `puzzle.moves[ply]`."""
    board = board_at(puzzle, ply)
    try:
        move = chess.Move.from_uci(uci)
    except chess.InvalidMoveError as e:
        raise IllegalMove(uci) from e
    if move not in board.legal_moves:
        raise IllegalMove(uci)

    expected = puzzle.moves[ply]
    after = board.copy(stack=False)
    after.push(move)
    if move.uci() != expected and not after.is_checkmate():
        return Verdict(
            accepted=False, puzzle_completed=False, opponent_move=None,
            next_ply=ply, fen=board.fen(), expected_move=expected,
        )

    completed = after.is_checkmate() or ply + 1 >= len(puzzle.moves)
    if completed:
        return Verdict(
            accepted=True, puzzle_completed=True, opponent_move=None,
            next_ply=ply + 1, fen=after.fen(), expected_move=None,
        )
    reply = puzzle.moves[ply + 1]
    after.push_uci(reply)
    return Verdict(
        accepted=True, puzzle_completed=False, opponent_move=reply,
        next_ply=ply + 2, fen=after.fen(), expected_move=None,
    )
