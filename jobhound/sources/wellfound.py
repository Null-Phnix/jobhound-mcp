import httpx
from jobhound.sources.base import BaseSource
from jobhound.models import Job


class WellfoundSource(BaseSource):
    """
    Wellfound job source via Blackreach browser agent.
    Blackreach handles JS-rendered pages and auth walls.
    """

    def __init__(self, blackreach_server: str, query: str, remote_only: bool = True):
        self.blackreach = blackreach_server
        self.query = query
        self.remote_only = remote_only

    def fetch(self) -> list[Job]:
        try:
            goal = (
                f"Go to wellfound.com and search for '{self.query}'. "
                f"{'Filter by remote only. ' if self.remote_only else ''}"
                "Return a JSON list of job postings with fields: "
                "title, company, url, location, description."
            )
            resp = httpx.post(
                f"{self.blackreach}/browse",
                json={"goal": goal, "structured": True},
                timeout=15,
            )
            if resp.status_code != 202:
                return []

            import time
            job_id = resp.json().get("job_id")
            deadline = time.time() + 120
            while time.time() < deadline:
                time.sleep(8)
                r = httpx.get(f"{self.blackreach}/jobs/{job_id}", timeout=10).json()
                if r.get("status") == "done":
                    items = r.get("result", {}).get("data", [])
                    jobs = []
                    for item in items:
                        if not item.get("url"):
                            continue
                        jobs.append(Job(
                            url=item["url"],
                            source="wellfound",
                            company=item.get("company", ""),
                            title=item.get("title", ""),
                            location=item.get("location", "Remote"),
                            remote=True,
                            description=item.get("description", ""),
                        ))
                    return jobs
                if r.get("status") == "failed":
                    return []
            return []
        except Exception:
            return []
