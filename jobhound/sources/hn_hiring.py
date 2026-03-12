import html
import random
import re
import time

import httpx

from jobhound.log import get_logger
from jobhound.models import Job
from jobhound.sources.base import BaseSource

log = get_logger("jobhound.sources.hn_hiring")

ALGOLIA = "https://hn.algolia.com/api/v1/search?query=Ask+HN+Who+is+Hiring&tags=story&hitsPerPage=1"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

_REMOTE_HINTS = {"remote", "anywhere", "distributed", "virtual", "worldwide", "global"}


def _clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_comment(text: str) -> Job | None:
    """Parse a raw HN comment into a Job. Returns None if not recognizable."""
    if not text or len(text) < 20:
        return None
    clean = _clean_html(text)
    # Must contain pipe separator (HN job post convention)
    parts = [p.strip() for p in clean.split("|")]
    if len(parts) < 2:
        return None
    company = parts[0][:100].strip()
    title = parts[1][:200].strip() if len(parts) > 1 else "Engineer"
    location = parts[2][:100].strip() if len(parts) > 2 else ""

    # Guard against malformed entries where "company" is a sentence fragment
    if len(company) < 2 or " " in company[:2]:
        return None

    combined = clean.lower()
    remote = any(h in combined for h in _REMOTE_HINTS)

    url_match = re.search(r"https?://[^\s<>\"']+", clean)
    if url_match:
        url = url_match.group(0).rstrip(".,;)")
    else:
        return None  # No URL = not worth applying to

    return Job(
        url=url,
        source="hn_hiring",
        company=company,
        title=title,
        location=location,
        remote=remote,
        description=clean[:600],
    )


def _fetch_with_retry(url: str, retries: int = 3, timeout: float = 8) -> dict:
    """GET with simple retry on failure."""
    for attempt in range(retries):
        try:
            resp = httpx.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(random.uniform(1.0, 2.5))
            else:
                raise e
    return {}


class HNHiringSource(BaseSource):
    def fetch(self) -> list[Job]:
        try:
            resp = httpx.get(ALGOLIA, timeout=10)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            if not hits:
                log.warning("HN Hiring: no thread found via Algolia")
                return []
            thread_id = hits[0]["objectID"]
            log.info("HN Hiring: found thread %s", thread_id)

            thread = _fetch_with_retry(HN_ITEM.format(id=thread_id))
            kids = thread.get("kids", [])[:150]  # top 150 comments

            jobs = []
            errors = 0
            for kid in kids:
                try:
                    time.sleep(random.uniform(0.05, 0.15))  # gentle rate limit
                    comment = _fetch_with_retry(HN_ITEM.format(id=kid), retries=2, timeout=5)
                    job = _parse_comment(comment.get("text", ""))
                    if job:
                        jobs.append(job)
                except Exception as e:
                    errors += 1
                    log.debug("HN Hiring: failed to fetch comment %s: %s", kid, e)

            log.info("HN Hiring: %d jobs parsed, %d comment errors", len(jobs), errors)
            return jobs

        except httpx.TimeoutException:
            log.warning("HN Hiring: timeout fetching thread list")
            return []
        except Exception as e:
            log.exception("HN Hiring: error: %s", e)
            return []
