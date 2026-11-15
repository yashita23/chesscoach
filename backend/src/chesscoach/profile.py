"""API hồ sơ kỹ năng: năng lực chung, năng lực từng kỹ năng và các nhóm kỹ năng cho radar."""

from pydantic import BaseModel

from chesscoach.ability_history import player_ability
from chesscoach.auth import CurrentPlayer, Db, player_api_router
from chesscoach.skills import GROUPS, SKILLS

router = player_api_router()

Z_95 = 1.96


class Interval(BaseModel):
    low: float
    high: float

    @classmethod
    def around(cls, center: float, sigma: float) -> "Interval":
        half = Z_95 * sigma
        return cls(low=round(center - half, 1), high=round(center + half, 1))


class SkillOut(BaseModel):
    id: str
    name: str
    description: str
    group: str
    ability: float
    """Năng lực ở kỹ năng này (θ + θₖ đã co), cùng thang rating bài tập."""
    deviation: float
    """θₖ đã co: lệch bao nhiêu so với năng lực chung."""
    ci: Interval
    """Khoảng tin cậy 95% của năng lực kỹ năng."""
    attempts: int
    enough_data: bool
    """False khi chưa có lần giải nào: giao diện hiện "chưa đủ dữ liệu"."""


class GroupOut(BaseModel):
    id: str
    name: str
    ability: float | None
    """Trung bình năng lực các kỹ năng đã có dữ liệu trong nhóm; None nếu chưa có."""
    skills: list[str]


class ProfileOut(BaseModel):
    theta: float
    ci: Interval
    attempts: int
    skills: list[SkillOut]
    groups: list[GroupOut]


@router.get("/profile")
def get_profile(player: CurrentPlayer, db: Db) -> ProfileOut:
    ability = player_ability(db, player)
    skills = []
    for s in SKILLS:
        state = ability.skill(s.id)
        skill_ability = ability.skill_ability(s.id)
        skills.append(
            SkillOut(
                id=s.id,
                name=s.name,
                description=s.description,
                group=s.group,
                ability=round(skill_ability, 1),
                deviation=round(ability.skill_deviation(s.id), 1),
                ci=Interval.around(skill_ability, ability.skill_sigma(s.id)),
                attempts=state.attempts,
                enough_data=state.attempts > 0,
            )
        )
    groups = []
    for g in GROUPS:
        members = [s for s in skills if s.group == g.id]
        known = [s.ability for s in members if s.enough_data]
        groups.append(
            GroupOut(
                id=g.id,
                name=g.name,
                ability=round(sum(known) / len(known), 1) if known else None,
                skills=[s.id for s in members],
            )
        )
    return ProfileOut(
        theta=round(ability.theta, 1),
        ci=Interval.around(ability.theta, ability.sigma),
        attempts=ability.attempts,
        skills=skills,
        groups=groups,
    )
