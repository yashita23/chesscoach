"""Bản đồ kỹ năng: gán mỗi chủ đề Lichess vào đúng một kỹ năng. Dữ liệu tĩnh, viết tay.

Có ba loại chủ đề:
- chủ đề kỹ năng: thuộc đúng một trong các kỹ năng dưới đây;
- chủ đề mô tả (META_THEMES): độ dài, mức lợi thế, giai đoạn ván, nguồn ván. Đây không phải kỹ năng nên bị bỏ qua;
- chủ đề lạ (Lichess thêm sau này): coi như chủ đề mô tả và ghi cảnh báo một lần.

Bài tập không có chủ đề kỹ năng nào thì thuộc kỹ năng "bỏ lỡ chiến thuật", cũng là kỹ năng hứng các lỗi
trong ván không nhận diện được motif.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass

log = logging.getLogger(__name__)

MISSED_TACTIC = "missed_tactic"


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    """Giải thích bằng lời thường cho người không chơi cờ."""
    group: str
    themes: frozenset[str]


@dataclass(frozen=True)
class SkillGroup:
    id: str
    name: str


GROUPS: tuple[SkillGroup, ...] = (
    SkillGroup("basic_tactics", "Chiến thuật cơ bản"),
    SkillGroup("combinations", "Phối hợp"),
    SkillGroup("mating", "Chiếu hết"),
    SkillGroup("endgame", "Tàn cuộc"),
    SkillGroup("defense", "Phòng thủ"),
)


def _skill(id: str, name: str, description: str, group: str, themes: str) -> Skill:
    return Skill(id, name, description, group, frozenset(themes.split()))


SKILLS: tuple[Skill, ...] = (
    _skill("hanging_piece", "Quân treo", "Ăn quân đối thủ để không ai bảo vệ, hoặc đừng bỏ quân mình như vậy.",
           "basic_tactics", "hangingPiece"),
    _skill("fork", "Fork (đòn đôi)", "Một quân tấn công hai quân cùng lúc; đối thủ chỉ cứu được một.",
           "basic_tactics", "fork"),
    _skill("pin", "Ghim quân", "Quân bị tấn công không dám chạy vì sẽ để lộ quân quý hơn phía sau.",
           "basic_tactics", "pin"),
    _skill("skewer", "Xiên quân", "Tấn công quân quý ở trước; nó chạy đi thì ăn được quân phía sau.",
           "basic_tactics", "skewer xRayAttack"),
    _skill("trapped_piece", "Quân bị nhốt", "Quân không còn ô nào để chạy, chỉ chờ bị ăn.",
           "basic_tactics", "trappedPiece"),
    _skill("discovered_attack", "Tấn công phát hiện", "Đi một quân để mở đường cho quân phía sau tấn công.",
           "combinations", "discoveredAttack discoveredCheck doubleCheck"),
    _skill("deflection", "Làm lệch quân bảo vệ",
           "Kéo hoặc tiêu diệt quân đang bảo vệ, để quân kia mất chỗ dựa.",
           "combinations", "deflection capturingDefender interference"),
    _skill("attraction", "Dụ quân và thí quân", "Hy sinh quân để kéo quân đối thủ vào ô bất lợi hoặc mở đường.",
           "combinations", "attraction sacrifice clearance"),
    _skill("quiet_move", "Nước lặng và nước trung gian",
           "Nước không ăn, không chiếu nhưng tạo đe dọa không chống đỡ nổi, hoặc chen một nước mạnh vào giữa.",
           "combinations", "quietMove intermezzo zugzwang collinearMove"),
    _skill(MISSED_TACTIC, "Bỏ lỡ chiến thuật", "Đòn chiến thuật chung, không thuộc mẫu riêng nào ở trên.",
           "combinations", "enPassant castling"),
    _skill("mate_in_1", "Chiếu hết 1 nước", "Tìm nước chiếu hết ngay lập tức.", "mating", "mateIn1"),
    _skill("mate_in_n", "Chiếu hết nhiều nước", "Tính một chuỗi 2–5 nước để chiếu hết.",
           "mating", "mateIn2 mateIn3 mateIn4 mateIn5"),
    _skill("back_rank_mate", "Chiếu hết hàng cuối", "Vua bị chính tốt nhà mình chắn, bị chiếu hết ở hàng cuối.",
           "mating", "backRankMate"),
    _skill("mate_patterns", "Mẫu chiếu hết", "Các thế chiếu hết kinh điển có tên riêng.",
           "mating",
           "smotheredMate pillsburysMate operaMate epauletteMate hookMate cornerMate swallowstailMate "
           "triangleMate arabianMate anastasiaMate morphysMate blindSwineMate killBoxMate dovetailMate "
           "bodenMate doubleBishopMate vukovicMate balestraMate"),
    _skill("king_attack", "Tấn công vua", "Dồn quân tấn công vua đối thủ khi vua thiếu che chắn.",
           "mating", "kingsideAttack queensideAttack exposedKing attackingF2F7"),
    _skill("promotion", "Tốt phong cấp", "Đẩy tốt lên hàng cuối để thành hậu hoặc quân khác.",
           "endgame", "promotion underPromotion advancedPawn"),
    _skill("pawn_endgame", "Tàn cuộc tốt", "Thế cờ chỉ còn vua và tốt.", "endgame", "pawnEndgame"),
    _skill("rook_endgame", "Tàn cuộc xe", "Thế cờ còn xe và tốt, loại tàn cuộc hay gặp nhất.",
           "endgame", "rookEndgame"),
    _skill("other_endgame", "Tàn cuộc quân nhẹ và hậu", "Tàn cuộc tượng, mã hoặc hậu.",
           "endgame", "bishopEndgame knightEndgame queenEndgame queenRookEndgame"),
    _skill("defense", "Nước phòng thủ", "Tìm nước duy nhất cứu được thế cờ khi bị đe dọa.",
           "defense", "defensiveMove"),
)

META_THEMES = frozenset(
    "short long veryLong oneMove advantage crushing equality mate "
    "opening middlegame endgame master masterVsMaster superGM".split()
)

# Kỹ năng tiên quyết → kỹ năng sau. Tiên quyết chưa vững chỉ làm giảm ưu tiên, không khóa kỹ năng sau.
PREREQUISITES: tuple[tuple[str, str], ...] = (
    ("hanging_piece", "fork"),
    ("hanging_piece", "pin"),
    ("hanging_piece", "trapped_piece"),
    ("hanging_piece", "deflection"),
    ("hanging_piece", "defense"),
    ("pin", "skewer"),
    ("pin", "discovered_attack"),
    ("fork", "discovered_attack"),
    ("fork", "attraction"),
    ("fork", "defense"),
    ("deflection", "attraction"),
    ("deflection", "quiet_move"),
    ("discovered_attack", "quiet_move"),
    ("mate_in_1", "mate_in_n"),
    ("mate_in_1", "back_rank_mate"),
    ("mate_in_1", "mate_patterns"),
    ("mate_in_1", "king_attack"),
    ("mate_in_1", "defense"),
    ("mate_in_n", "mate_patterns"),
    ("mate_in_n", "king_attack"),
    ("promotion", "pawn_endgame"),
    ("pawn_endgame", "rook_endgame"),
    ("pawn_endgame", "other_endgame"),
)

SKILLS_BY_ID = {s.id: s for s in SKILLS}
_SKILL_OF_THEME = {theme: s.id for s in SKILLS for theme in s.themes}
_warned: set[str] = set()


def skills_of(themes: Iterable[str]) -> frozenset[str]:
    """Kỹ năng của một bài tập theo các chủ đề của nó. Luôn có ít nhất một kỹ năng."""
    found: set[str] = set()
    for theme in themes:
        skill = _SKILL_OF_THEME.get(theme)
        if skill is not None:
            found.add(skill)
        elif theme not in META_THEMES and theme not in _warned:
            _warned.add(theme)
            log.warning("Chủ đề Lichess %r chưa có trong bản đồ kỹ năng; tạm bỏ qua", theme)
    return _or_missed_tactic(found)


# Phần mở rộng của bản đồ kỹ năng cho bộ Stanford CS398 (lớp đánh giá 1): chủ đề Chess.com → kỹ năng của app.
# Một số cách gán là phán đoán (ví dụ Sacrifice → attraction, Zwischenzug → quiet_move). None là chủ đề mô tả
# (cấu trúc thế cờ, không phải đòn chiến thuật), giống META_THEMES của Lichess.
CHESSCOM_THEMES: dict[str, str | None] = {
    "Hanging Piece": "hanging_piece",
    "Fork / Double Attack": "fork",
    "Pin": "pin",
    "Skewer": "skewer",
    "X-Ray Attack": "skewer",
    "Trapped Piece": "trapped_piece",
    "Discovered Attack": "discovered_attack",
    "Discovered Check": "discovered_attack",
    "Double Check": "discovered_attack",
    "Windmill": "discovered_attack",
    "Decoy / Deflection": "deflection",
    "Remove the Defender": "deflection",
    "Overloading": "deflection",
    "Interference": "deflection",
    "Sacrifice": "attraction",
    "Queen Sacrifice": "attraction",
    "Exchange Sacrifice": "attraction",
    "Clearance Sacrifice": "attraction",
    "Desperado": "attraction",
    "Zwischenzug": "quiet_move",
    "Zugzwang": "quiet_move",
    "En passant": MISSED_TACTIC,
    "Mate in 1": "mate_in_1",
    "Mate in 2": "mate_in_n",
    "Mate in 3+": "mate_in_n",
    "Back Rank": "back_rank_mate",
    "Smothered Mate": "mate_patterns",
    "Mating Net": "mate_patterns",
    "Basic Checkmates": "mate_patterns",
    "Advanced Checkmates": "mate_patterns",
    "Two Rooks Checkmate": "mate_patterns",
    "Two Bishops Checkmate": "mate_patterns",
    "Scholar's Mate": "mate_patterns",
    "Fastest Checkmate": "mate_patterns",
    "Vulnerable King": "king_attack",
    "Attacking Castled King": "king_attack",
    "Promotion": "promotion",
    "Underpromotion": "promotion",
    "Passed Pawns": None,  # gắn cho gần nửa số bài tập: mô tả thế cờ, không phải đòn
    "Pawn Endgame": "pawn_endgame",
    "Opposition": "pawn_endgame",
    "Rook Endgame": "rook_endgame",
    "Defense": "defense",
    "Perpetual Check": "defense",
    "Stalemate": "defense",
    "Rooks on Seventh": None,
    "Doubled Rook": None,
    "Battery": None,
    "Alekhine's Gun": None,
    "Knight Outpost": None,
    "Bishop Pair": None,
    "Fianchetto": None,
    "Opposite Colored Bishops": None,
    "Simple": None,
    "Simplification": None,
    "Endgame Tactics": None,
}


def skills_of_chesscom(themes: Iterable[str]) -> frozenset[str]:
    """Như `skills_of`, cho chủ đề Chess.com. Chủ đề lạ coi như chủ đề mô tả."""
    found = {skill for t in themes if (skill := CHESSCOM_THEMES.get(t.strip())) is not None}
    return _or_missed_tactic(found)


def _or_missed_tactic(found: set[str]) -> frozenset[str]:
    """Bài tập không có chủ đề kỹ năng nào thuộc kỹ năng "bỏ lỡ chiến thuật"."""
    return frozenset(found) if found else frozenset({MISSED_TACTIC})


def _check() -> None:
    themes = [t for s in SKILLS for t in s.themes]
    assert len(themes) == len(set(themes)), "mỗi chủ đề chỉ thuộc một kỹ năng"
    assert not META_THEMES & set(themes), "chủ đề mô tả không được là chủ đề kỹ năng"
    assert {s.group for s in SKILLS} == {g.id for g in GROUPS}
    assert all(a in SKILLS_BY_ID and b in SKILLS_BY_ID for a, b in PREREQUISITES)
    assert 15 <= len(SKILLS) <= 20
    assert all(s is None or s in SKILLS_BY_ID for s in CHESSCOM_THEMES.values())


_check()
