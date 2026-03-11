import httpx
import re
from jobhound.sources.base import BaseSource
from jobhound.models import Job

ALGOLIA = "https://hn.algolia.com/api/v1/search?query=Ask+HN+Who+is+Hiring&tags=story&hitsPerPage=1"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


def _parse_comment(text: str) -> Job | None:
    """Parse a raw HN comment into a Job. Returns None if not a job post."""
    if not text or len(text) < 20:
        return None
    # Common format: "Company | Role | Location | Salary | URL"
    clean = re.sub(r"<[^>]+>", " ", text).strip()
    parts = [p.strip() for p in clean.split("|")]
    if len(parts) < 2:
        return None
    company = parts[0][:100]
    title = parts[1][:200] if len(parts) > 1 else "Engineer"
    location = parts[2][:100] if len(parts) > 2 else ""
    remote = "remote" in clean.lower()
    url_match = re.search(r"https?://\S+", clean)
    url = url_match.group(0) if url_match else f"https://news.ycombinator.com/item?text={hash(text)}"
    return Job(
        url=url, source="hn_hiring", company=company, title=title,
        location=location, remote=remote, description=clean[:500],
    )


class HNHiringSource(BaseSource):
    def fetch(self) -> list[Job]:
        try:
            # Find current month's thread
            resp = httpx.get(ALGOLIA, timeout=10)
            hits = resp.json().get("hits", [])
            if not hits:
                return []
            thread_id = hits[0]["objectID"]

            # Get comment IDs
            thread = httpx.get(HN_ITEM.format(id=thread_id), timeout=10).json()
            kids = thread.get("kids", [])[:100]  # limit to first 100 comments

            jobs = []
            for kid in kids:
                try:
                    comment = httpx.get(HN_ITEM.format(id=kid), timeout=5).json()
                    job = _parse_comment(comment.get("text", ""))
                    if job:
                        jobs.append(job)
                except Exception:
                    continue
            return jobs
        except Exception:
            return []
