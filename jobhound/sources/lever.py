import html
import random
import re
import time

import httpx

from jobhound.log import get_logger
from jobhound.models import Job
from jobhound.sources.base import BaseSource

log = get_logger("jobhound.sources.lever")

API = "https://api.lever.co/v0/postings/{slug}?mode=json"

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
    cats = item.get("categories") or {}
    loc = cats.get("location", "").lower()
    commitment = cats.get("commitment", "").lower()
    tags = " ".join(item.get("tags") or []).lower()
    combined = f"{loc} {commitment} {tags}"
    return any(h in combined for h in _REMOTE_HINTS)


def _build_description(item: dict) -> str:
    """Concatenate Lever's plain-text description lists."""
    parts = []
    plain = item.get("descriptionPlain", "")
    if plain:
        parts.append(plain)
    for section in item.get("lists") or []:
        text = section.get("content", "")
        if text:
            parts.append(_clean_html(text))
    additional = item.get("additionalPlain", "")
    if additional:
        parts.append(additional)
    return "\n\n".join(parts)


class LeverSource(BaseSource):
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
                    log.warning("Lever %s: HTTP %d", slug, resp.status_code)
                    continue
                items = resp.json()
                if not isinstance(items, list):
                    log.warning("Lever %s: unexpected response shape", slug)
                    continue
                for item in items:
                    url = item.get("hostedUrl", "")
                    if not url:
                        continue
                    cats = item.get("categories") or {}
                    jobs.append(Job(
                        url=url,
                        source="lever",
                        company=slug,
                        title=item.get("text", ""),
                        location=cats.get("location", ""),
                        remote=_is_remote(item),
                        description=_build_description(item),
                        raw=item,
                    ))
                log.info("Lever %s: %d jobs", slug, len(items))
            except httpx.TimeoutException:
                log.warning("Lever %s: timeout", slug)
            except Exception as e:
                log.exception("Lever %s: error: %s", slug, e)
        return jobs
