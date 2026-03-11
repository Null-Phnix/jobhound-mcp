import httpx
import re
from jobhound.sources.base import BaseSource
from jobhound.models import Job

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()


class AshbySource(BaseSource):
    def __init__(self, slugs: list[str]):
        self.slugs = slugs

    def fetch(self) -> list[Job]:
        jobs = []
        for slug in self.slugs:
            try:
                resp = httpx.get(API.format(slug=slug), timeout=10)
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("jobs", []):
                    jobs.append(Job(
                        url=item.get("jobUrl", ""),
                        source="ashby",
                        company=slug,
                        title=item.get("title", ""),
                        location=item.get("location", {}).get("name", ""),
                        remote=item.get("isRemote", False),
                        description=_strip_html(item.get("descriptionHtml", "")),
                        raw=item,
                    ))
            except Exception:
                continue
        return [j for j in jobs if j.url]
