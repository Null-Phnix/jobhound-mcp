import httpx
import re
from jobhound.sources.base import BaseSource
from jobhound.models import Job

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseSource(BaseSource):
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
                    loc = item.get("location", {}).get("name", "")
                    jobs.append(Job(
                        url=item.get("absolute_url", ""),
                        source="greenhouse",
                        company=slug,
                        title=item.get("title", ""),
                        location=loc,
                        remote="remote" in loc.lower(),
                        description=re.sub(r"<[^>]+>", " ", item.get("content", "")),
                        raw=item,
                    ))
            except Exception:
                continue
        return [j for j in jobs if j.url]
