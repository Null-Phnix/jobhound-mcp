import httpx
import time
from dataclasses import dataclass
from typing import Optional
from jobhound.models import Job


@dataclass
class ApplyResult:
    success: bool
    method: Optional[str] = None
    error: Optional[str] = None


class Applier:
    def __init__(self, linkedin_server: str, blackreach_server: str):
        self.linkedin = linkedin_server
        self.blackreach = blackreach_server

    def submit(self, job: Job, cv: str, cover_letter: str) -> ApplyResult:
        """Try apply strategies in order. Returns first success."""
        # 1. LinkedIn MCP for LinkedIn URLs
        if "linkedin.com" in job.url:
            result = self._try_linkedin(job, cover_letter)
            if result:
                return ApplyResult(success=True, method="linkedin_mcp")

        # 2. Direct POST for known ATSs
        result = self._try_direct(job, cv, cover_letter)
        if result:
            return result

        # 3. Blackreach fallback
        result = self._try_blackreach(job, cv, cover_letter)
        if result:
            return ApplyResult(success=True, method="blackreach")

        return ApplyResult(success=False, error="All apply strategies failed")

    def _try_linkedin(self, job: Job, cover_letter: str) -> bool:
        try:
            resp = httpx.post(
                f"{self.linkedin}/apply",
                json={"profile_url": job.url, "message": cover_letter[:300]},
                timeout=10,
            )
            if resp.status_code != 200:
                return False
            job_id = resp.json().get("job_id")
            if not job_id:
                return False
            # Poll for result
            deadline = time.time() + 60
            while time.time() < deadline:
                time.sleep(4)
                r = httpx.get(f"{self.linkedin}/jobs/{job_id}", timeout=10).json()
                if r.get("status") in ("done", "failed"):
                    return r.get("result", {}).get("success", False)
            return False
        except Exception:
            return False

    def _try_direct(self, job: Job, cv: str, cover_letter: str) -> Optional[ApplyResult]:
        """Direct POST for Ashby, Greenhouse, Lever."""
        try:
            if "ashbyhq.com" in job.url:
                parts = job.url.rstrip("/").split("/")
                job_posting_id = parts[-1]
                resp = httpx.post(
                    f"https://api.ashbyhq.com/posting-api/application/{job.company}",
                    json={
                        "jobPostingId": job_posting_id,
                        "resume": cv,
                        "coverLetter": cover_letter,
                    },
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    return ApplyResult(success=True, method="ashby_direct")
            elif "greenhouse.io" in job.url or "boards.greenhouse.io" in job.url:
                # Greenhouse requires PDF, skip direct POST — fall through to Blackreach
                return None
            elif "lever.co" in job.url:
                # Lever direct apply
                parts = job.url.rstrip("/").split("/")
                posting_id = parts[-1]
                resp = httpx.post(
                    f"https://api.lever.co/v0/postings/{job.company}/{posting_id}/apply",
                    json={"resume": cv, "coverLetter": cover_letter},
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    return ApplyResult(success=True, method="lever_direct")
        except Exception:
            pass
        return None

    def _try_blackreach(self, job: Job, cv: str, cover_letter: str) -> Optional[bool]:
        try:
            resp = httpx.post(
                f"{self.blackreach}/browse",
                json={
                    "goal": (
                        f"Apply for the job at {job.url}. "
                        f"Cover letter: {cover_letter[:500]}"
                    )
                },
                timeout=10,
            )
            if resp.status_code != 202:
                return None
            job_id = resp.json().get("job_id")
            deadline = time.time() + 300
            while time.time() < deadline:
                time.sleep(10)
                r = httpx.get(f"{self.blackreach}/jobs/{job_id}", timeout=10).json()
                if r.get("status") == "done":
                    return True
                if r.get("status") == "failed":
                    return None
            return None
        except Exception:
            return None
