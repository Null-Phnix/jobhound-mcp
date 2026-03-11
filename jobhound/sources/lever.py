import httpx
from jobhound.sources.base import BaseSource
from jobhound.models import Job

API = "https://api.lever.co/v0/postings/{slug}?mode=json"


class LeverSource(BaseSource):
    def __init__(self, slugs: list[str]):
        self.slugs = slugs

    def fetch(self) -> list[Job]:
        jobs = []
        for slug in self.slugs:
            try:
                resp = httpx.get(API.format(slug=slug), timeout=10)
                if resp.status_code != 200:
                    continue
                for item in resp.json():
                    loc = item.get("categories", {}).get("location", "")
                    jobs.append(Job(
                        url=item.get("hostedUrl", ""),
                        source="lever",
                        company=slug,
                        title=item.get("text", ""),
                        location=loc,
                        remote="remote" in loc.lower(),
                        description=item.get("descriptionPlain", ""),
                        raw=item,
                    ))
            except Exception:
                continue
        return [j for j in jobs if j.url]
