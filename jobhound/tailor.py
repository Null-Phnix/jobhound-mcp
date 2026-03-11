from pathlib import Path
from jobhound.models import Job
import anthropic

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

PROMPT = """You are writing job application materials for Josimar Lee, an AI engineer.

RESUME:
{resume}

JOB:
Company: {company}
Title: {title}
Description: {description}

Write two things:

1. A tailored version of the CV that emphasizes the most relevant projects and skills for this specific role. Keep the same markdown format. Do not invent experience.

2. A cover letter in Josimar's voice: direct, no em dashes, no corporate speak, no filler. Lead with the most relevant project. Own any gaps honestly. 3-5 short paragraphs max.

Format your response EXACTLY like this:
=== CV ===
[tailored CV here]
=== COVER LETTER ===
[cover letter here]"""


class Tailor:
    def __init__(self, resume_path: Path, sonnet_threshold: int = 70):
        self.resume = resume_path.read_text()
        self.sonnet_threshold = sonnet_threshold
        self.client = anthropic.Anthropic()

    def generate(self, job: Job) -> tuple[str, str]:
        """Returns (tailored_cv, cover_letter)."""
        model = SONNET if job.score >= self.sonnet_threshold else HAIKU
        prompt = PROMPT.format(
            resume=self.resume,
            company=job.company,
            title=job.title,
            description=job.description[:3000],
        )
        msg = self.client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
        cv, letter = self._parse(raw)
        return cv, letter

    def _parse(self, raw: str) -> tuple[str, str]:
        cv = ""
        letter = ""
        if "=== CV ===" in raw and "=== COVER LETTER ===" in raw:
            parts = raw.split("=== COVER LETTER ===")
            cv = parts[0].replace("=== CV ===", "").strip()
            letter = parts[1].strip()
        else:
            # Fallback: treat whole thing as cover letter
            letter = raw.strip()
        return cv, letter
