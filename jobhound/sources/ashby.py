import html
import random
import re
import time

import httpx

from jobhound.log import get_logger
from jobhound.models import Job
from jobhound.sources.base import BaseSource

log = get_logger("jobhound.sources.ashby")

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

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
    if item.get("isRemote"):
        return True
    loc = (item.get("location") or {}).get("name", "").lower()
    workplace = (item.get("workplaceType") or "").lower()
    return any(h in loc or h in workplace for h in _REMOTE_HINTS)


class AshbySource(BaseSource):
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
                    log.warning("Ashby %s: HTTP %d", slug, resp.status_code)
                    continue
                items = resp.json().get("jobs", [])
                for item in items:
                    url = item.get("jobUrl") or item.get("applyUrl", "")
                    if not url:
                        continue
                    jobs.append(Job(
                        url=url,
                        source="ashby",
                        company=slug,
                        title=item.get("title", ""),
                        location=(item.get("location") or {}).get("name", ""),
                        remote=_is_remote(item),
                        description=_clean_html(
                            item.get("descriptionHtml") or item.get("descriptionPlain", "")
                        ),
                        raw=item,
                    ))
                log.info("Ashby %s: %d jobs", slug, len(items))
            except httpx.TimeoutException:
                log.warning("Ashby %s: timeout", slug)
            except Exception as e:
                log.exception("Ashby %s: error: %s", slug, e)
        return jobs
