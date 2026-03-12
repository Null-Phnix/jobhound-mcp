import html
import random
import re
import time

import httpx

from jobhound.log import get_logger
from jobhound.models import Job
from jobhound.sources.base import BaseSource

log = get_logger("jobhound.sources.greenhouse")

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

_UA_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

_REMOTE_HINTS = {"remote", "anywhere", "distributed", "virtual", "worldwide", "global"}


def _clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _is_remote(item: dict) -> bool:
    loc = (item.get("location") or {}).get("name", "").lower()
    # Greenhouse sometimes puts remote in office_locations or metadata
    office_locs = " ".join(
        (o.get("name", "") for o in item.get("office_locations") or [])
    ).lower()
    combined = f"{loc} {office_locs}"
    return any(h in combined for h in _REMOTE_HINTS)


class GreenhouseSource(BaseSource):
    def __init__(self, slugs: list[str]):
        self.slugs = slugs

    def fetch(self) -> list[Job]:
        jobs = []
        for slug in self.slugs:
            try:
                time.sleep(random.uniform(0.3, 0.9))
                resp = httpx.get(
                    API.format(slug=slug),
                    headers={"User-Agent": random.choice(_UA_POOL)},
                    timeout=12,
                )
                if resp.status_code != 200:
                    log.warning("Greenhouse %s: HTTP %d", slug, resp.status_code)
                    continue
                items = resp.json().get("jobs", [])
                for item in items:
                    url = item.get("absolute_url", "")
                    if not url:
                        continue
                    jobs.append(Job(
                        url=url,
                        source="greenhouse",
                        company=slug,
                        title=item.get("title", ""),
                        location=(item.get("location") or {}).get("name", ""),
                        remote=_is_remote(item),
                        description=_clean_html(item.get("content", "")),
                        raw=item,
                    ))
                log.info("Greenhouse %s: %d jobs", slug, len(items))
            except httpx.TimeoutException:
                log.warning("Greenhouse %s: timeout", slug)
            except Exception as e:
                log.exception("Greenhouse %s: error: %s", slug, e)
        return jobs
