from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class Config:
    resume_path: Path
    skills_path: Path
    db_path: Path
    interval_hours: int
    score_threshold: int
    sonnet_threshold: int
    ashby_slugs: list[str]
    greenhouse_slugs: list[str]
    lever_slugs: list[str]
    remoteok: bool
    hn_hiring: bool
    wellfound_query: str
    wellfound_remote_only: bool
    linkedin_server: str
    blackreach_server: str
    mcp_port: int


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    base = path.parent
    sources = raw.get("sources", {})
    wellfound = sources.get("wellfound", {}) or {}
    return Config(
        resume_path=base / raw["profile"]["resume"],
        skills_path=base / raw["profile"]["skills"],
        db_path=base / raw["daemon"]["db_path"],
        interval_hours=raw["daemon"]["interval_hours"],
        score_threshold=raw["score"]["threshold"],
        sonnet_threshold=raw["score"]["sonnet_threshold"],
        ashby_slugs=sources.get("ashby") or [],
        greenhouse_slugs=sources.get("greenhouse") or [],
        lever_slugs=sources.get("lever") or [],
        remoteok=bool(sources.get("remoteok", False)),
        hn_hiring=bool(sources.get("hn_hiring", False)),
        wellfound_query=wellfound.get("query", "AI engineer"),
        wellfound_remote_only=wellfound.get("remote_only", True),
        linkedin_server=raw["apply"]["linkedin_server"],
        blackreach_server=raw["apply"]["blackreach_server"],
        mcp_port=raw["mcp"]["port"],
    )
