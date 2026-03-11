from pathlib import Path
import yaml
from jobhound.models import Job


class Scorer:
    def __init__(self, skills_path: Path):
        raw = yaml.safe_load(skills_path.read_text())
        self.pos = raw["positive"]
        self.neg = raw["negative"]
        self.weights = raw["weights"]

    def score(self, job: Job) -> int:
        score = 0
        text = f"{job.title} {job.description}".lower()
        title = job.title.lower()

        # Positive: title keywords
        for kw in self.pos.get("title_keywords", []):
            if kw.lower() in title:
                score += self.weights["title_keyword"]

        # Positive: body keywords
        for kw in self.pos.get("body_keywords", []):
            if kw.lower() in text:
                score += self.weights["body_keyword"]

        # Positive: remote
        if job.remote:
            score += self.pos.get("remote", 0)

        # Positive: canada or global location (only if explicitly stated, not blank)
        loc = job.location.lower()
        if loc and any(x in loc for x in ["canada", "remote", "worldwide", "global"]):
            score += self.pos.get("canada_or_global", 0)

        # Positive: salary
        if job.salary_min and job.salary_min >= 100_000:
            score += self.pos.get("salary_gte_100k", 0)

        # Negative: required keywords
        for kw in self.neg.get("required_keywords", []):
            if kw.lower() in text:
                score += self.weights["negative_keyword"]

        # Negative: dealbreakers
        for kw in self.neg.get("dealbreakers", []):
            if kw.lower() in text:
                score += self.weights["dealbreaker"]

        # Negative: internship
        if any(x in text for x in ["intern", "co-op", "coop", "internship"]):
            score += self.neg.get("internship", -99)

        return score
