from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class Config:
    # Applicant personal info
    applicant_name: str
    applicant_email: str
    applicant_phone: str
    applicant_linkedin: str
    # Paths
    resume_path: Path
    skills_path: Path
    db_path: Path
    # Daemon
    interval_hours: int
    score_threshold: int
    sonnet_threshold: int
    # Sources
    ashby_slugs: list[str]
    greenhouse_slugs: list[str]
    lever_slugs: list[str]
    remoteok: bool
    hn_hiring: bool
    wellfound_query: str
    wellfound_remote_only: bool
    # Servers
    linkedin_server: str
    blackreach_server: str
    mcp_port: int


class ConfigError(Exception):
    pass


def load_config(path: Path) -> Config:
    try:
        raw = yaml.safe_load(path.read_text())
    except Exception as e:
        raise ConfigError(f"Cannot read config at {path}: {e}") from e

    base = path.parent

    def _require(d: dict, *keys: str, context: str = ""):
        for key in keys:
            if key not in d or d[key] is None:
                raise ConfigError(
                    f"Missing required config field: "
                    f"{'.' .join(filter(None, [context, key]))}"
                )

    _require(raw, "profile", "daemon", "score", "sources", "apply", "mcp")
    _require(raw["profile"], "resume", "skills", context="profile")
    _require(raw["daemon"], "interval_hours", "db_path", context="daemon")
    _require(raw["score"], "threshold", "sonnet_threshold", context="score")
    _require(raw["apply"], "blackreach_server", context="apply")

    # Applicant info — required for form submission
    applicant = raw.get("applicant", {}) or {}
    name = applicant.get("name", "")
    email = applicant.get("email", "")
    phone = applicant.get("phone", "")
    if not name or not email:
        raise ConfigError(
            "Missing applicant.name and/or applicant.email in config.yaml. "
            "These are required for form submission."
        )

    resume_path = base / raw["profile"]["resume"]
    if not resume_path.exists():
        raise ConfigError(f"Resume not found at: {resume_path}")

    skills_path = base / raw["profile"]["skills"]
    if not skills_path.exists():
        raise ConfigError(f"Skills file not found at: {skills_path}")

    sources = raw.get("sources", {})
    wellfound = sources.get("wellfound", {}) or {}

    return Config(
        applicant_name=name,
        applicant_email=email,
        applicant_phone=phone,
        applicant_linkedin=applicant.get("linkedin", ""),
        resume_path=resume_path,
        skills_path=skills_path,
        db_path=base / raw["daemon"]["db_path"],
        interval_hours=int(raw["daemon"]["interval_hours"]),
        score_threshold=int(raw["score"]["threshold"]),
        sonnet_threshold=int(raw["score"]["sonnet_threshold"]),
        ashby_slugs=sources.get("ashby") or [],
        greenhouse_slugs=sources.get("greenhouse") or [],
        lever_slugs=sources.get("lever") or [],
        remoteok=bool(sources.get("remoteok", False)),
        hn_hiring=bool(sources.get("hn_hiring", False)),
        wellfound_query=wellfound.get("query", "AI engineer"),
        wellfound_remote_only=wellfound.get("remote_only", True),
        linkedin_server=raw["apply"].get("linkedin_server", "http://localhost:7433"),
        blackreach_server=raw["apply"]["blackreach_server"],
        mcp_port=int(raw["mcp"].get("port", 7434)),
    )
