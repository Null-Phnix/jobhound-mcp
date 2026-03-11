from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Status(str, Enum):
    NEW = "new"
    QUEUED = "queued"   # scored above threshold, waiting for tailoring
    APPLIED = "applied"
    FAILED = "failed"
    INTERVIEWING = "interviewing"
    REJECTED = "rejected"


@dataclass
class Job:
    url: str
    source: str
    company: str
    title: str
    location: str = ""
    remote: bool = False
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    description: str = ""
    score: int = 0
    status: Status = Status.NEW
    applied_at: Optional[str] = None
    method: Optional[str] = None
    cover_letter: Optional[str] = None
    cv_used: Optional[str] = None
    notes: Optional[str] = None
    raw: dict = field(default_factory=dict)
    db_id: Optional[int] = None  # populated when read from SQLite

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d
