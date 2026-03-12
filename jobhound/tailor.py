import time
from pathlib import Path

import anthropic

from jobhound.log import get_logger
from jobhound.models import Job

log = get_logger("jobhound.tailor")

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


def _backoff_sleep(attempt: int) -> None:
    """Exponential backoff: 2s, 4s, 8s."""
    delay = 2 ** (attempt + 1)
    log.info("Tailor: retrying in %ds (attempt %d)", delay, attempt + 1)
    time.sleep(delay)


class Tailor:
    def __init__(self, resume_path: Path, sonnet_threshold: int = 70):
        self.resume = resume_path.read_text()
        self.sonnet_threshold = sonnet_threshold
        self.client = anthropic.Anthropic()

    def generate(self, job: Job, retries: int = 3) -> tuple[str, str]:
        """Returns (tailored_cv, cover_letter). Retries on transient errors."""
        model = SONNET if job.score >= self.sonnet_threshold else HAIKU
        prompt = PROMPT.format(
            resume=self.resume,
            company=job.company,
            title=job.title,
            description=job.description[:3000],
        )
        last_err = None
        for attempt in range(retries):
            try:
                msg = self.client.messages.create(
                    model=model,
                    max_tokens=6000,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = msg.content[0].text
                cv, letter = self._parse(raw)
                if not letter:
                    log.warning(
                        "Tailor: response missing cover letter for %s — %s",
                        job.company, job.title,
                    )
                    if attempt < retries - 1:
                        _backoff_sleep(attempt)
                        continue
                log.info(
                    "Tailor: generated for %s — %s (model=%s, cv=%d chars, letter=%d chars)",
                    job.company, job.title, model, len(cv), len(letter),
                )
                return cv, letter
            except anthropic.RateLimitError as e:
                log.warning("Tailor: rate limit hit, backing off: %s", e)
                last_err = e
                _backoff_sleep(attempt)
            except anthropic.APIStatusError as e:
                if e.status_code >= 500:
                    log.warning("Tailor: API server error %d, backing off: %s", e.status_code, e)
                    last_err = e
                    _backoff_sleep(attempt)
                else:
                    log.exception("Tailor: API error (non-retryable): %s", e)
                    raise
            except Exception as e:
                log.exception("Tailor: unexpected error: %s", e)
                raise

        raise RuntimeError(f"Tailor: all {retries} attempts failed for {job.company} — {job.title}: {last_err}")

    def _parse(self, raw: str) -> tuple[str, str]:
        cv = ""
        letter = ""
        if "=== CV ===" in raw and "=== COVER LETTER ===" in raw:
            parts = raw.split("=== COVER LETTER ===")
            cv = parts[0].replace("=== CV ===", "").strip()
            letter = parts[1].strip()
        else:
            log.warning("Tailor: response missing expected format markers")
            letter = raw.strip()
        return cv, letter
