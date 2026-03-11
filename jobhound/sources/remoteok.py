import httpx
from jobhound.sources.base import BaseSource
from jobhound.models import Job

API = "https://remoteok.com/api"
HEADERS = {"User-Agent": "JobHound/0.1 (job search bot)"}


class RemoteOKSource(BaseSource):
    def fetch(self) -> list[Job]:
        try:
            resp = httpx.get(API, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            items = resp.json()
            jobs = []
            for item in items[1:]:  # skip first metadata item
                if not item.get("position"):
                    continue
                jobs.append(Job(
                    url=item.get("url", ""),
                    source="remoteok",
                    company=item.get("company", ""),
                    title=item.get("position", ""),
                    location="Remote",
                    remote=True,
                    description=item.get("description", ""),
                    raw=item,
                ))
            return [j for j in jobs if j.url]
        except Exception:
            return []
