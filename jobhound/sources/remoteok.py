import html
import re

import httpx

from jobhound.log import get_logger
from jobhound.models import Job
from jobhound.sources.base import BaseSource

log = get_logger("jobhound.sources.remoteok")

API = "https://remoteok.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class RemoteOKSource(BaseSource):
    def fetch(self) -> list[Job]:
        try:
            resp = httpx.get(API, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            items = resp.json()
            jobs = []
            for item in items[1:]:  # skip first metadata element
                if not item.get("position") or not item.get("url"):
                    continue
                jobs.append(Job(
                    url=item["url"],
                    source="remoteok",
                    company=item.get("company", ""),
                    title=item.get("position", ""),
                    location="Remote",
                    remote=True,
                    description=_clean_html(item.get("description", "")),
                    raw=item,
                ))
            log.info("RemoteOK: %d jobs", len(jobs))
            return jobs
        except httpx.TimeoutException:
            log.warning("RemoteOK: timeout")
            return []
        except Exception as e:
            log.exception("RemoteOK: error: %s", e)
            return []
